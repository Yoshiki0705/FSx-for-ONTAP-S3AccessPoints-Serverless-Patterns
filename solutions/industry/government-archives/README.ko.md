# UC16: 정부 기관 — 공문서 디지털 아카이브·FOIA 대응

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **문서**: [아키텍처](docs/architecture.md) | [데모 스크립트](docs/demo-guide.md) | [문제 해결](../docs/phase7-troubleshooting.md)

## 개요

FSx for ONTAP S3 Access Points 를 활용한 정부 기관의 공문서
디지털 아카이브 및 정보공개청구(FOIA: Freedom of Information Act)
대응 자동화 파이프라인입니다.

## 유스케이스

정부 기관이 보유한 대량의 공문서(PDF, 스캔 이미지, 이메일)를
자동으로 디지털화·분류·마스킹(리댁션)하여 정보공개청구에
신속하게 대응합니다.

### 처리 흐름

```
FSx for ONTAP (공문서 저장 — 부서별 NTFS ACL)
  → S3 Access Point
    → Step Functions 워크플로
      → Discovery: 신규 문서 검출(PDF, TIFF, EML, MSG)
      → OCR: Textract 를 이용한 문서 디지털화(ap-northeast-1 미지원으로 크로스 리전)
      → Classification: Comprehend 를 이용한 문서 분류(기밀 수준 판정)
      → EntityExtraction: PII 검출(이름, 주소, SSN, 전화번호)
      → Redaction: 기밀 정보 자동 마스킹(리댁션)
      → IndexGeneration: 전문 검색 인덱스 생성(OpenSearch, 비활성화 가능)
      → ComplianceCheck: 보존 기간·폐기 일정 확인(NARA GRS)
```

### 대상 데이터

| 데이터 형식 | 설명 | 일반 크기 |
|-----------|------|-----------|
| PDF | 공문서, 보고서, 계약서 | 100 KB – 50 MB |
| TIFF | 스캔 문서 | 1 – 100 MB |
| EML / MSG | 이메일 아카이브 | 10 KB – 10 MB |
| DOCX / XLSX | Office 문서 | 50 KB – 20 MB |

### AWS 서비스

| 서비스 | 용도 |
|---------|------|
| FSx for ONTAP | 공문서 영구 스토리지(부서별 NTFS ACL) |
| S3 Access Points | 서버리스에서의 문서 액세스 |
| Step Functions | 워크플로 오케스트레이션 |
| Lambda | 문서 분류, PII 검출, 마스킹 처리 |
| Amazon Textract ⚠️ | 문서 OCR(us-east-1 경유 크로스 리전) |
| Amazon Comprehend | 엔티티 추출, 문서 분류, PII 검출 |
| Amazon Bedrock | 문서 요약, FOIA 답변 초안 생성 |
| Amazon Macie | 기밀 데이터 자동 검출 |
| DynamoDB | 문서 메타데이터, 처리 상태 관리 |
| OpenSearch Serverless | 전문 검색 인덱스(옵션, 기본 비활성화) |
| SNS | FOIA 기한 알림 |

### Public Sector 적합성

- **NARA(국립문서기록관리청) 준수**: 전자 기록 관리 요건 대응
- **FOIA 대응**: 20 영업일 이내 답변 기한을 자동 추적
- **FedRAMP High**: AWS GovCloud 에서 준수
- **Section 508**: 접근성 대응(OCR + 대체 텍스트 생성)
- **Records Management**: 보존 기간·폐기 일정 자동 관리

### FOIA 대응 흐름

```
FOIA 청구 접수
  → 대상 문서 검색(OpenSearch)
  → 해당 문서의 기밀 수준 판정
  → 자동 마스킹(PII, 국가안보 정보)
  → 검토 담당자에게 통지
  → 답변 기한 추적(20 영업일)
  → 공개 문서 패키지 생성
```

## 검증된 화면(스크린샷)

### 1. 공문서 저장(S3 Access Point 경유)

정보공개청구 접수 후, 대상 문서가 `archives/YYYY/MM/` 프리픽스 하위에 저장됩니다.

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     내용: S3 AP 의 archives/ 프리픽스에서 PDF 문서 목록
     마스크: 계정 ID, S3 AP ARN, 문서명 -->
![UC16: 공문서 저장 확인](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. 마스킹된 문서 열람

처리 완료 후 `redacted/` 프리픽스에 저장된 텍스트로, PII 가
`[REDACTED]` 마커로 치환되어 있습니다. **일반 직원이 공개 전에 검토하는 화면입니다.**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     내용: S3 콘솔에서의 redacted 텍스트 미리보기, [REDACTED] 마커 표시
     마스크: 계정 ID, 마스킹 대상 문서명(샘플명만 표시) -->
![UC16: 마스킹된 문서 미리보기](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. 마스킹 메타데이터(sidecar JSON)

감사용 sidecar 데이터입니다. 원문 PII 는 저장하지 않고 SHA-256 해시만 저장합니다.
오프셋, 엔티티 유형(NAME / EMAIL / SSN 등), 신뢰도가 기록됩니다.

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     내용: redaction-metadata/*.json 의 정형 뷰
     마스크: 계정 ID, 원본 문서명 -->
![UC16: 마스킹 메타데이터 JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA 기한 리마인더(SNS 이메일 통지)

FOIA 담당자가 기한 3 영업일 전에 수신하는 리마인더 이메일입니다.
기한 초과 시에는 severity=HIGH 의 OVERDUE 통지가 발송됩니다.

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     내용: 이메일 클라이언트에서 FOIA_DEADLINE_APPROACHING 이메일 표시
     마스크: 수신자·발신자 이메일, request_id(샘플 ID만 표시) -->
![UC16: FOIA 기한 리마인더 이메일](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA GRS 보존 일정(DynamoDB Explorer)

`fsxn-uc16-demo-retention` 테이블입니다. 문서별로 NARA GRS 코드
(GRS 2.1 / 2.2 / 1.1)와 보존 연수(3 / 7 / 30 년), 폐기 예정일이 기록됩니다.

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     내용: DynamoDB Explorer 에서 retention 테이블의 항목 목록
     마스크: 계정 ID, document_key(샘플명만) -->
![UC16: 보존 일정 테이블](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
공문서 아카이브·FOIA 대응(OCR·분류·마스킹·보존 기한 관리) 자동화로 정보공개청구 대응을 신속화합니다.

### Metrics
| 메트릭 | 목표값(예) |
|-----------|------------|
| 처리된 문서 수 / 실행 | > 500 documents |
| OCR 텍스트 추출 성공률 | > 95% |
| PII 검출 정확도 | > 95% |
| 마스킹 처리 시간 / 문서 | < 30 초 |
| FOIA 대응 시간 단축 | > 50% |
| Human Review 필수율 | 100%(마스킹 결과는 전건 인간 확인 필수) |

> **100% Human Review 의 이유**: 마스킹 누락이 정보공개·개인정보 보호에 직접 영향을 미치므로, 전건 인간 확인을 필수로 합니다.

### Measurement Method
Step Functions 실행 이력, Comprehend PII 검출 결과, 마스킹 전후 diff, DynamoDB 보존 기한 이력, CloudWatch Metrics. 검토 결과는 DynamoDB 에 기록하여 감사 시 "누가·언제·무엇을 확인·승인했는지"를 추적 가능하게 합니다.

### Sample Run Results (실측 예)

**환경**: FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| 지표 | Before (수동) | After (S3AP 자동화) |
|------|-------------|-------------------|
| FOIA 대응 시간 | 며칠~몇 주 | 389 ms (10 docs, sequential) |
| 문서 검출 | 수동 검색 | 32 ms (10 documents) |
| 파일 읽기 | 개별 액세스 | avg 36 ms / document |
| 마스킹 품질 | 담당자 의존, 불일치 존재 | Comprehend PII 검출 + 자동 마스킹 |
| Human Review | 없음 or 비정기 | 100%(전건 인간 확인 필수) |
| 감사 증적 | 개인 기록 | DynamoDB (who/when/what) + S3 Object Lock |
| 보존 기한 관리 | 수동 | 자동 추적 + 알림 |

> **주기**: UC16 의 sample run 은 합성 또는 비민감 샘플 문서를 이용한 검증이며, 실제 행정 문서나 프로덕션 데이터를 나타내지 않습니다. 본 sample run 은 처리 경로의 검증만을 수행합니다. 마스킹 품질, Human Review 의 완전성, 감사 증적 평가는 고객 고유의 PoC 에서 별도로 실시해 주십시오.

## 배포

### 사전 검증

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 원샷 배포

```bash
bash scripts/deploy_phase7.sh government-archives
```

### 수동 배포

```bash
# 전제: AWS SAM CLI 가 필요합니다. sam build 가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### OpenSearch 모드

| 모드 | 용도 | 월간 비용(시산) |
|--------|------|-------------------|
| `none` | 검증·저비용 운영(기본값) | $0 |
| `serverless` | 가변 워크로드, 종량 과금 | $350 – $700 |
| `managed` | 고정 워크로드, 저렴 | $35 – $100 |

## 디렉터리 구성

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # 크로스 리전 Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA GRS 보존 기간
│   └── foia_deadline_reminder/handler.py  # 20 영업일 추적
├── tests/                            # 52 pytest (Hypothesis 포함)
└── README.md
```


---

## AWS 문서 링크

| 서비스 | 문서 |
|---------|------------|
| FSx for ONTAP | [사용자 가이드](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [개발자 가이드](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [개발자 가이드](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [개발자 가이드](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [사용자 가이드](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [개발자 가이드](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Well-Architected Framework 대응

| 기둥 | 대응 |
|----|------|
| 운영 우수성 | X-Ray, EMF, FOIA 데드라인 추적, 52+ 테스트 |
| 보안 | PII 리댁션, SHA-256 감사 사이드카, Macie, 100% Human Review |
| 신뢰성 | Step Functions Retry/Catch, 크로스 리전 OCR, resilience 테스트 |
| 성능 효율성 | 병렬 PII 검출, OpenSearch 인덱스, 배치 처리 |
| 비용 최적화 | 서버리스, OpenSearch Serverless, 조건부 인덱싱 |
| 지속 가능성 | NARA GRS 준수, 보존 기간 관리, 자동 폐기 일정 |





---

## 비용 견적(월간 개산)

> **주기**: 아래는 ap-northeast-1 리전의 개산이며, 실제 비용은 사용량에 따라 달라집니다. 최신 요금은 [AWS Pricing Calculator](https://calculator.aws/) 에서 확인해 주십시오.

### 서버리스 구성 요소(종량 과금)

| 서비스 | 단가 | 예상 사용량 | 월간 개산 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 함수 × 100 docs/일 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/일 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/일 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/실행 | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/쿼리 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/일 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/월 | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### 고정 비용(FSx for ONTAP — 기존 환경 전제)

| 구성 요소 | 월간 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (기존 환경 공유) |
| S3 Access Point | 추가 요금 없음(S3 API 요금만) |

### 합계 개산

| 구성 | 월간 개산 |
|------|---------|
| 최소 구성(일 1회 실행) | ~$5-15 |
| 표준 구성(시간별 실행) | ~$15-50 |
| 대규모 구성(고빈도 + 알람) | ~$50-150 |

> **Governance Caveat**: 비용 견적은 개산이며 보증값이 아닙니다. 실제 청구액은 사용 패턴, 데이터 양, 리전에 따라 달라집니다.

---

## 로컬 테스트

### Prerequisites 확인

```bash
# 전제 조건 확인
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 용)
aws sts get-caller-identity  # AWS 자격 증명
```

### sam local invoke

```bash
# 빌드
# 전제: AWS SAM CLI 가 필요합니다. sam build 가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

# Discovery Lambda 의 로컬 실행
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 환경 변수 오버라이드 포함
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 유닛 테스트

```bash
python3 -m pytest tests/ -v
```

자세한 내용은 [로컬 테스트 퀵 스타트](../docs/local-testing-quick-start.md) 를 참조해 주십시오.

---

## 출력 샘플 (Output Sample)

공문서 아카이브·FOIA 처리의 출력 예:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **주기**: 위는 샘플 출력이며, 실제 값은 환경·입력 데이터에 따라 달라집니다. 벤치마크 수치는 sizing reference 이며 service limit 이 아닙니다.

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 조직은 적격한 전문가와 상담해 주십시오.

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP 의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) 를 참조해 주십시오.
