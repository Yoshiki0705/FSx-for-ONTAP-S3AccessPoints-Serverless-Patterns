# 통신 네트워크 분석 — CDR/네트워크 로그 이상 탐지 데모 가이드

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 개요

본 데모에서는 CDR(통화 상세 기록)과 네트워크 장비 로그의 자동 분석 파이프라인을 시연합니다. Athena 기반 트래픽 통계와 Bedrock 기반 이상 탐지를 통해 네트워크 장애 조기 발견과 컴플라이언스 보고를 자동화합니다.

**핵심 메시지**: AI가 CDR/네트워크 로그를 자동 분석하여 이상을 실시간으로 탐지하고 일별 보고서를 자동 생성합니다.

**예상 시간**: 3~5분

---

## 단계별 배포 및 검증 절차

### Step 1: 사전 요구 사항 확인

```bash
aws --version          # v2.x 필수
sam --version          # 1.x 이상
python3 --version      # 3.9 이상
aws sts get-caller-identity
```

### Step 2: 리포지토리 클론

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Step 3: 샘플 데이터 준비

FSx for ONTAP 볼륨에 샘플 데이터를 배치합니다.

### Step 4: 배포

```bash
sam build

sam deploy \
  --stack-name fsxn-telecom-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    CdrSuffixFilter=".csv,.asn1,.parquet" \
    AnomalyThresholdStdDev=3 \
    CapacityThresholdPercent=80 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: 배포 확인

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Step 6: 워크플로 수동 실행

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### Step 7: 출력 결과 확인

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/ --region ap-northeast-1
```

---

## 검증 체크리스트

| 확인 항목 | 확인 방법 | 기대 결과 |
|----------|---------|----------|
| CDR 파일 탐지 | Step Functions 실행 로그 | Discovery 단계에서 CDR 파일 수를 반환 |
| Athena 트래픽 통계 | S3 출력 버킷 | `cdr-stats.json` 생성됨 |
| 이상 탐지 | `anomalies.json` 확인 | 이상 플래그 레코드 포함 |
| 일별 보고서 | S3 버킷 | `network-health.json` 존재 |
| SNS 알림 | 이메일 수신 확인 | 중대 이상 존재 시 알림 이메일 수신 |

---

---

## 스크린샷

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## 정리 (Cleanup)

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
