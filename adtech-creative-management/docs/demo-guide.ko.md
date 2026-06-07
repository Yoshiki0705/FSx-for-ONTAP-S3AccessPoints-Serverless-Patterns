# 크리에이티브 자산 관리 — 자산 카탈로그화 및 브랜드 준수 검사 데모 가이드

🌐 **Language / 언어**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 요약

본 데모에서는 광고 크리에이티브 자산의 자동 카탈로그화 및 브랜드 준수 검사 파이프라인을 시연합니다. Rekognition 비주얼 분석과 Bedrock 브랜드 가이드라인 준수 검사를 통해 광고 제작의 품질 관리를 자동화합니다.

**핵심 메시지**: AI가 크리에이티브 자산을 자동 분석하고, 브랜드 가이드라인 준수를 검증하며, 자산 카탈로그를 자동 생성합니다.

**예상 시간**: 3~5분

---

## 단계별 배포·검증 절차

### Step 1: 사전 조건 확인

```bash
aws --version          # AWS CLI v2 필수
sam --version          # SAM CLI 1.x 이상
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: 리포지토리 클론

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/adtech-creative-management
```

### Step 3: SAM 빌드 및 배포

```bash
sam build

sam deploy \
  --stack-name fsxn-adtech-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    BrandGuidelinesS3Key=brand-guidelines.json \
    ModerationConfidenceThreshold=80 \
    MaxTagsPerAsset=50 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 4: 워크플로우 수동 실행

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 5: 출력 결과 확인

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## 검증 체크리스트

| 확인 항목 | 확인 방법 | 기대 결과 |
|----------|----------|----------|
| 미디어 파일 감지 | Step Functions 실행 로그 | Discovery 단계가 자산 파일 수를 반환 |
| 라벨 추출 | `asset-catalog.json` 확인 | 각 자산에 최대 50 태그가 부여됨 |
| 모더레이션 검사 | `flagged-assets.json` 확인 | 문제 콘텐츠가 플래그 지정되어 나열됨 |
| 브랜드 준수 검사 | compliance_status 필드 확인 | compliant / non-compliant가 올바르게 판정됨 |
| SNS 알림 | 이메일 수신 확인 | 모더레이션 위반 시에만 알림 수신 |

---

---

## 스크린샷

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc19-demo/step-functions-graph-view.png)


## 정리

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
