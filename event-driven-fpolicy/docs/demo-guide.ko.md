🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 이벤트 기반 FPolicy — 데모 가이드

## 개요

본 데모에서는 NFS를 통한 파일 생성 작업이 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 경로로 실시간 이벤트화되는 과정을 시연합니다.

**예상 시간**: 10~15분 (배포 완료 환경의 경우 3~5분)

---

## 사전 요구사항

| 항목 | 요건 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 이상, FPolicy 지원 |
| VPC | FSxN과 동일 VPC에 프라이빗 서브넷 |
| NFS 마운트 | 클라이언트에서 FSxN 볼륨에 NFS 마운트 완료 |
| AWS CLI | v2 이상, 적절한 IAM 권한 |
| Docker | 컨테이너 이미지 빌드용 |
| ECR | 리포지토리 생성 완료 |

---

## Step 1: 스택 배포

### 1.1 컨테이너 이미지 빌드

```bash
cd event-driven-fpolicy/

# ECR 로그인
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# 빌드 & 푸시
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 CloudFormation 배포

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

### 1.3 Fargate 태스크 IP 확인

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy 설정

FSxN SVM에 SSH로 접속하여 다음 명령을 실행합니다.

### 2.1 External Engine 생성

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Event 생성

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Policy 생성

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Scope 설정

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Policy 활성화

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 연결 확인

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# Status: connected 확인
```

---

## Step 3: 테스트 파일 생성

NFS 마운트된 클라이언트에서 파일을 생성합니다.

```bash
# NFS 마운트 (미실시인 경우)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# 테스트 파일 생성
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: SQS 메시지 확인

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# 메시지 수신 (확인용)
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**예상 출력**:

```json
{
  "Messages": [
    {
      "Body": "{\"event_id\":\"...\",\"operation_type\":\"create\",\"file_path\":\"test-fpolicy-event.txt\",\"volume_name\":\"vol1\",\"svm_name\":\"FSxN_OnPre\",\"timestamp\":\"...\",\"file_size\":0}"
    }
  ]
}
```

---

## Step 5: EventBridge 이벤트 확인

CloudWatch Logs에서 이벤트를 확인합니다.

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# 최신 로그 스트림 가져오기
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# 로그 이벤트 가져오기
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**예상 출력**:

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "operation_type": "create",
    "file_path": "test-fpolicy-event.txt",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-01-15T10:30:00+00:00",
    "file_size": 0
  }
}
```

---

## Step 6: IP 자동 업데이트 확인 (옵션)

Fargate 태스크를 강제 재시작하여 IP 자동 업데이트를 확인합니다.

```bash
# 태스크 강제 중지 (새 태스크가 자동 시작됨)
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# 30초 대기 후 새 태스크 IP 확인
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# ONTAP engine의 IP가 업데이트되었는지 확인
# SSH로 FSxN SVM에 접속
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: 정리

```bash
# 1. ONTAP FPolicy 비활성화
# SSH로 FSxN SVM에 접속
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. CloudFormation 스택 삭제
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. 테스트 파일 삭제
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## 문제 해결

### FPolicy Server에 연결할 수 없음

1. Security Group에서 TCP 9898이 허용되어 있는지 확인
2. Fargate 태스크가 RUNNING 상태인지 확인
3. ONTAP external-engine의 IP가 올바른지 확인
4. SQS VPC Endpoint가 존재하는지 확인

### SQS에 메시지가 도착하지 않음

1. FPolicy Server 로그 확인: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. SQS VPC Endpoint가 존재하는지 확인
3. 태스크 역할에 `sqs:SendMessage` 권한이 있는지 확인

### EventBridge에 이벤트가 도착하지 않음

1. Bridge Lambda 로그 확인
2. SQS Event Source Mapping이 활성화되어 있는지 확인
3. EventBridge 커스텀 버스 이름이 올바른지 확인

### NFSv4.2에서 이벤트가 감지되지 않음

NFSv4.2는 ONTAP FPolicy monitoring에 미지원입니다. `mount -o vers=4.1`을 명시적으로 지정하세요.
