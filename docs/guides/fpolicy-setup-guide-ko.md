# FPolicy 설정 가이드

**Phase 10 — ONTAP FPolicy Event-Driven Integration**

## Overview

이 가이드는 ONTAP FPolicy를 사용하여 파일 작업 이벤트를 AWS 서비스(SQS → EventBridge → Step Functions)로 전달하는 설정 절차를 설명합니다.

> ⚠️ **중요: vers=4.1 또는 vers=3으로 마운트하세요. vers=4는 NFSv4.2로 네고시에이트되어 FPolicy 비지원입니다.**

> ⚠️ **중요: ONTAP FPolicy 프로토콜은 NLB TCP 패스스루를 통해 작동하지 않습니다. Fargate 태스크의 직접 Private IP를 사용하세요.**

## AWS 전제 조건

- `shared/cfn/fpolicy-server-fargate.yaml` stack deployed
- `shared/cfn/fpolicy-ingestion.yaml` stack deployed
- SQS VPC Endpoint available
- ECR/STS/S3/Logs VPC Endpoints available

## ONTAP 전제 조건

- FSx for NetApp ONTAP file system running
- SVM configured with NFS enabled
- Admin access to ONTAP REST API or CLI

## Architecture

```
NFS Client (NFSv3 mount)
  → FSx ONTAP Volume (file create/write/delete/rename)
    → ONTAP FPolicy (async, external engine)
      → ECS Fargate TCP Server (port 9898, direct IP)
        → SQS Ingestion Queue
          → EventBridge Custom Bus
            → Step Functions (per-UC)
```

## Quick Setup

```bash
# 1. Deploy FPolicy Server
./scripts/deploy_fpolicy_server.sh <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>

# 2. Deploy E2E Demo (bastion + SQS VPC Endpoint)
aws cloudformation deploy \
  --template-file shared/cfn/fpolicy-e2e-demo.yaml \
  --stack-name fsxn-fpolicy-e2e-demo \
  --parameter-overrides VpcId=<VPC> SubnetId=<PUBLIC_SUBNET> \
    PrivateSubnetIds=<PRIV_1>,<PRIV_2> \
    VpcEndpointSecurityGroupId=<SG> KeyPairName=<KEY> \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Get Fargate Task IP
TASK_IP=$(aws ecs describe-tasks --cluster <CLUSTER> \
  --tasks $(aws ecs list-tasks --cluster <CLUSTER> --desired-status RUNNING \
  --query 'taskArns[0]' --output text) \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)

# 4. Configure ONTAP FPolicy (via REST API from bastion)
# Engine
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines' \
  -H 'Content-Type: application/json' \
  -d '{"name":"fpolicy_aws_engine","type":"asynchronous","primary_servers":["'$TASK_IP'"],"port":9898}'

# Event (NFSv3 only!)
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/events' \
  -H 'Content-Type: application/json' \
  -d '{"name":"nfsv3_file_events","protocol":"nfsv3","file_operations":{"create":true,"write":true,"delete":true,"rename":true}}'

# Policy + Scope + Enable
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/policies' \
  -H 'Content-Type: application/json' \
  -d '{"name":"fpolicy_aws","mandatory":false,"engine":{"name":"fpolicy_aws_engine"},"events":[{"name":"nfsv3_file_events"}],"scope":{"include_volumes":["<VOLUME>"]},"priority":1}'

# 5. Test (from bastion, NFSv3 mount)
mount -t nfs -o vers=4.1 <SVM_IP>:/<VOL_PATH> /mnt/fsxn
echo "test" | sudo tee /mnt/fsxn/fpolicy-test.txt

# 6. Verify SQS
aws sqs receive-message --queue-url <QUEUE_URL> --max-number-of-messages 5
```

## 관련 문서

- [Event-Driven README (Quickstart)](../event-driven/README.md)
- [FPolicy Configuration Reference](../event-driven/fpolicy-configuration-reference.md)
- [FPolicy E2E Verification Report](../event-driven/fpolicy-e2e-verification-report.md)
- [FPolicy Server Deployment Architecture](../event-driven/fpolicy-server-deployment-architecture.md)
- [NetApp ONTAP FPolicy Docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)

## SMB (CIFS) 설정 (Active Directory 필요)

### 전제 조건
- AWS Managed Microsoft AD 또는 Self-Managed AD
- AD 참가 설정으로 생성된 FSxN SVM
- 볼륨에 CIFS 공유 생성 완료

### 단계

```bash
# 1. AWS Managed Microsoft AD 생성
aws ds create-microsoft-ad --name fpolicy.local --short-name FPOLICY \
  --password '<AD_PASSWORD>' --vpc-settings VpcId=<VPC>,SubnetIds=<SUBNET1>,<SUBNET2> --edition Standard

# 2. AD 참가 포함 FSxN SVM 생성 (중요: 생성 시 AD 설정 필수)
aws fsx create-storage-virtual-machine --file-system-id <FS_ID> --name FPolicySMB \
  --active-directory-configuration 'NetBiosName=FPOLSMB,SelfManagedActiveDirectoryConfiguration={...}' \
  --root-volume-security-style NTFS

# 3-7. NFSv3와 동일한 절차 (이벤트 프로토콜을 cifs로 변경)
```

### 중요 사항
- SVM은 AD 설정과 함께 생성해야 함 — FSxN에서 기존 NFS 전용 SVM에 CIFS 추가 불가
- AWS Managed AD의 경우 `OU=Computers,OU=<domain>,DC=<domain>,DC=local` 사용
