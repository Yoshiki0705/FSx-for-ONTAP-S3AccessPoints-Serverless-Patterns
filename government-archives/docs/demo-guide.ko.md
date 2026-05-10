# UC16 데모 스크립트 (30분 세션)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## 전제

- AWS 계정, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `government-archives/template-deploy.yaml` 배포 (`OpenSearchMode=none`으로 비용 절감)

## 타임라인

### 0:00 - 0:05 인트로 (5분)

- 유스케이스: 지방자치단체·행정의 공문서 관리 디지털화
- FOIA / 정보공개청구의 법정 기한 (20 영업일)의 부하
- 과제: PII 탐지·편집은 수동으로 수 시간 소요

### 0:05 - 0:10 아키텍처 (5분)

- Textract + Comprehend + Bedrock 조합
- OpenSearch의 3가지 모드 (none / serverless / managed)
- NARA GRS 보존 기간 자동 관리

### 0:10 - 0:15 배포 (5분)

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 처리 실행 (7분)

```bash
# 샘플 PDF (기밀정보 포함) 업로드
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 실행
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

결과 확인:
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt` (원본 텍스트)
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json` (분류 결과)
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json` (PII 탐지)
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt` (편집 버전)
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json` (sidecar)

### 0:22 - 0:27 FOIA 기한 추적 (5분)

```bash
# FOIA 청구 등록
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 수동 실행
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

SNS 알림 이메일 확인.

### 0:27 - 0:30 마무리 (3분)

- OpenSearch 활성화 (`serverless`로 본격 검색) 경로
- GovCloud 마이그레이션 (FedRAMP High 요구사항)
- 다음 단계: Bedrock 에이전트로 대화형 FOIA 답변 생성

## 자주 묻는 질문과 답변

**Q. 일본의 정보공개법 (30일)에 대응 가능?**  
A. `REMINDER_DAYS_BEFORE`와 20 영업일 하드코딩을 수정하면 대응 가능 (미국 연방 공휴일 → 일본 공휴일로).

**Q. 원문 PII는 어디에 저장되나요?**  
A. 어디에도 저장하지 않습니다. `pii-entities/*.json`은 SHA-256 hash만, `redaction-metadata/*.json`도 hash + offset만 저장합니다. 복원은 원문에서 재실행이 필요합니다.

**Q. OpenSearch Serverless 비용 절감 방법?**  
A. 최소 2 OCU = 월 $350 정도. 프로덕션 외에는 중지 권장.
A. `OpenSearchMode=none`으로 skip, 또는 `OpenSearchMode=managed` + `t3.small.search × 1`로 ~$25/월로 절감.

---

## 출력 대상에 대해: OutputDestination으로 선택 가능 (Pattern B)

UC16 government-archives는 2026-05-11 업데이트에서 `OutputDestination` 파라미터를 지원합니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: OCR 텍스트 / 문서 분류 / PII 탐지 / 편집 / OpenSearch 전단 문서

**2가지 모드**:

### STANDARD_S3 (기본값, 기존 방식)
새로운 S3 버킷 (`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고,
AI 산출물을 그곳에 작성합니다. Discovery Lambda의 manifest만 S3 Access Point
에 작성됩니다 (기존 방식).

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP ("no data movement" 패턴)
OCR 텍스트, 분류 결과, PII 탐지 결과, 편집 완료 문서, 편집 메타데이터를 FSxN S3 Access Point
경유로 원본 문서와 **동일한 FSx ONTAP 볼륨**에 다시 작성합니다.
공문서 담당자가 SMB/NFS의 기존 디렉터리 구조 내에서 AI 산출물을 직접 참조할 수 있습니다.
표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (기타 필수 파라미터)
```

**체인 구조의 읽기**:

UC16은 전단 산출물을 후단 Lambda가 읽어오는 체인 구조 (OCR → Classification →
EntityExtraction → Redaction → IndexGeneration)이므로, `shared/output_writer.py`의
`get_bytes/get_text/get_json`에서 작성 대상과 동일한 destination에서 읽어옵니다.
이를 통해 `OutputDestination=FSXN_S3AP` 시에도 FSxN S3 Access Point에서의
읽기가 성립하며, 체인 전체가 일관된 destination으로 동작합니다.

**주의사항**:

- `S3AccessPointName` 지정을 강력히 권장 (Alias 형식과 ARN 형식 모두 IAM 허용)
- 5GB 초과 객체는 FSxN S3AP에서 불가 (AWS 사양), 멀티파트 업로드 필수
- ComplianceCheck Lambda는 DynamoDB만 사용하므로 `OutputDestination`의 영향을 받지 않습니다
- FoiaDeadlineReminder Lambda는 DynamoDB + SNS만 사용하므로 영향을 받지 않습니다
- OpenSearch 인덱스는 `OpenSearchMode` 파라미터로 별도 관리됩니다 (`OutputDestination`과 독립적)
- AWS 사양상 제약은
  [프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
  및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조
