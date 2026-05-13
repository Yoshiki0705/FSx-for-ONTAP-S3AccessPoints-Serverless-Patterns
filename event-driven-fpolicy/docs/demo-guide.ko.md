🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 이벤트 기반 FPolicy — 데모 가이드

## 개요

이 데모에서는 NFS를 통한 파일 생성 작업이 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 경로를 통해 실시간으로 이벤트화되는 과정을 시연합니다.

**예상 시간**: 10~15분 (배포 완료 환경에서 3~5분)

---

## 전제 조건

| 항목 | 요건 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 이상, FPolicy 지원 |
| VPC | FSxN과 동일 VPC에 프라이빗 서브넷 |
| NFS 마운트 | 클라이언트에서 FSxN 볼륨에 NFS 마운트 완료 |
| AWS CLI | v2 이상, 적절한 IAM 권한 |

---

## Step 1: 스택 배포

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-fpolicy-demo \
  --parameter-overrides \
    VpcId=vpc-xxxxxxxxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    FsxnSvmSecurityGroupId=sg-xxxxxxxxx \
    ContainerImage=<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
    FsxnMgmtIp=10.0.3.72 \
    FsxnSvmUuid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
    FsxnCredentialsSecret=fsxn-admin-credentials \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

---

## Step 2: ONTAP FPolicy 설정

FSxN SVM에 SSH 접속 후 실행:

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename

vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false

vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

---

## Step 3: 테스트 파일 생성

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: SQS 메시지 확인

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

---

## Step 5: EventBridge 이벤트 확인

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"
aws logs tail $LOG_GROUP --since 5m
```

---

## Step 6: 정리

```bash
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1
```

---

## 문제 해결

- **FPolicy Server 연결 불가**: Security Group TCP 9898 허용 확인, Fargate 태스크 RUNNING 상태 확인
- **SQS 메시지 없음**: SQS VPC Endpoint 존재 확인, 태스크 롤 권한 확인
- **NFSv4.2 이벤트 미감지**: `mount -o vers=4.1`을 명시적으로 지정
