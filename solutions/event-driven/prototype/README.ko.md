🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

# Event-Driven Prototype (이벤트 기반 프로토타입)

## 개요

본 프로토타입은 FSx for ONTAP S3 Access Points(FSx for ONTAP S3 AP)의
향후 네이티브 알림 기능을 염두에 둔 이벤트 기반 파일 처리 파이프라인의
레퍼런스 구현이다.

일반 S3 버킷의 Event Notifications를 사용하여
향후 FSx for ONTAP S3 AP 네이티브 알림 동작을 시뮬레이션한다.

## 아키텍처

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge 활성화)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (이미지 태그 지정 + 메타데이터 생성)
          → Latency Reporter Lambda (EMF 메트릭 출력)
```

## FSx for ONTAP S3 AP 향후 지원으로의 매핑

| 현재 프로토타입 | 향후 FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| `aws.s3` 이벤트 소스 | `aws.fsx` 이벤트 소스(예정) |
| S3 버킷 이름으로 필터링 | S3 AP 별칭으로 필터링 |
| S3 GetObject로 읽기 | S3 AP 경유로 읽기 |

## 필요한 변경 사항(네이티브 알림 지원 시)

FSx for ONTAP S3 AP가 네이티브 알림을 지원할 때 필요한 변경 사항:

### 1. 템플릿 변경

```yaml
# 변경 전(프로토타입)
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# 변경 후(FSx for ONTAP S3 AP)
# S3 Bucket 리소스를 삭제하고 기존 FSx for ONTAP S3 AP를 참조
# EventBridge Rule의 소스 필터를 업데이트
```

### 2. EventBridge 규칙 변경

```json
// 변경 전
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// 변경 후(예정)
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Lambda 환경 변수 변경

```yaml
# 변경 전
SOURCE_BUCKET: !Ref SourceBucket

# 변경 후
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Lambda 코드 변경

```python
# 변경 전(프로토타입)
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# 변경 후(FSx for ONTAP S3 AP)
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## 배포 절차

### 전제 조건

- AWS CLI 설정 완료
- Python 3.12
- Lambda 배포 패키지용 S3 버킷

### 배포

```bash
# 1. Lambda 패키지 빌드 및 업로드
# (생략: CI/CD 파이프라인에서 자동화)

# 2. SAM 스택 배포
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. 테스트 파일 업로드
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### 테스트 실행

```bash
# 단위 테스트
pytest event-driven-prototype/tests/ -v

# 레이턴시 비교 테스트(배포 후)
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## 디렉터리 구성

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation 템플릿
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # 이벤트 처리 Lambda (UC11 호환)
│   └── latency_reporter/
│       └── handler.py            # 레이턴시 측정 Lambda
├── tests/
│   ├── test_event_processor.py   # 이벤트 처리 단위 테스트
│   ├── test_latency_reporter.py  # 레이턴시 측정 단위 테스트
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # 본 문서
```

## 메트릭

CloudWatch EMF 형식으로 다음 메트릭을 출력:

| 메트릭 이름 | 단위 | 설명 |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | 이벤트 발생 → 처리 시작 |
| `EndToEndDuration` | Milliseconds | 이벤트 발생 → 처리 완료 |
| `ProcessingDuration` | Milliseconds | 처리 실행 시간 |
| `EventVolumePerMinute` | Count | 분당 이벤트 처리 수 |

## 관련 문서

- [이벤트 기반 아키텍처 설계](../docs/event-driven/architecture-design.md)
- [마이그레이션 가이드](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
