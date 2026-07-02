# UC15: 국방 / 우주 — 위성 이미지 분석 파이프라인

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 스크립트](docs/demo-guide.ko.md) | [문제 해결](../docs/phase7-troubleshooting.md)

## 개요

Amazon FSx for NetApp ONTAP S3 Access Points 를 활용한 위성 이미지(SAR / 광학)의
자동 분석 파이프라인. 대용량 위성 이미지 데이터를 FSx for ONTAP 에 저장하고,
S3 Access Points 를 통해 서버리스 처리를 실행한다.

## 유스케이스

국방·정보 기관 및 우주 관련 조직이 위성에서 취득한 지구 관측 데이터
(Earth Observation)를 자동으로 처리·분석한다.

### 처리 흐름

```
FSx for ONTAP (위성 이미지 저장)
  → S3 Access Point
    → Step Functions 워크플로
      → Discovery: 신규 이미지 감지 (GeoTIFF, NITF, HDF5)
      → Tiling: 대형 이미지를 타일로 분할 (Cloud Optimized GeoTIFF 변환)
      → ObjectDetection: Rekognition / SageMaker 로 물체 감지
      → ChangeDetection: 시계열 비교를 통한 변화 감지
      → GeoEnrichment: 메타데이터 부여 (좌표, 촬영 일시, 해상도)
      → AlertGeneration: 이상 감지 시 경보 생성
```

### 대상 데이터

| 데이터 형식 | 설명 | 대표 크기 |
|-----------|------|-----------|
| GeoTIFF | 광학 위성 이미지 | 100 MB – 10 GB |
| NITF | 군사 표준 이미지 형식 | 500 MB – 50 GB |
| HDF5 | SAR 데이터 (Sentinel-1 등) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | 타일화 완료 이미지 | 10 – 500 MB |

### AWS 서비스

| 서비스 | 용도 |
|---------|------|
| FSx for ONTAP | 위성 이미지의 영구 스토리지 (NTFS ACL 로 액세스 제어) |
| S3 Access Points | 서버리스에서의 이미지 액세스 |
| Step Functions | 워크플로 오케스트레이션 |
| Lambda | 타일 분할, 메타데이터 추출, 경보 생성 |
| SageMaker (Batch Transform) | 물체 감지·변화 감지 ML 추론 |
| Amazon Rekognition | 레이블 감지 (차량, 건물, 선박) |
| Amazon Bedrock | 이미지 캡션 생성, 보고서 요약 |
| DynamoDB | 처리 상태 관리, 감지 결과 인덱스 |
| SNS | 경보 알림 |
| CloudWatch | 관측성 |

### Public Sector 적합성

- **DoD CC SRG**: FSx for ONTAP 는 Impact Level 2/4/5 인증 완료 (GovCloud)
- **CSfC**: NetApp ONTAP 는 Commercial Solutions for Classified 인증 완료
- **FedRAMP**: AWS GovCloud 에서 FedRAMP High 준수
- **데이터 주권**: 리전 내에서 데이터 완결 (ap-northeast-1 / us-gov-west-1)

## 검증된 화면 (스크린샷)

2026-05-10 에 ap-northeast-1 에서 실제로 가동을 확인했을 때의,
**일반 직원이 일상적으로 조작하는 UI** 를 중심으로 게시한다. 기술자용 콘솔 화면
(Step Functions 그래프 등)은
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md) 를 참조.

### 1. 위성 이미지 저장 (FSx for ONTAP / S3 Access Point 경유)

파일 서버 관리자 관점에서 본, 분석 대상 위성 이미지의 배치 확인 화면.
`satellite/YYYY/MM/` 프리픽스 아래에 신규 이미지를 배치하기만 하면,
정기적인 Step Functions 워크플로가 자동으로 픽업한다.

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     내용: S3 AP 경유로 satellite/2026/05/*.tif 를 목록 표시 (오브젝트명, 크기, 갱신 일시)
     마스크: 계정 ID, Access Point ARN, 실제 위성 이미지명 -->
![UC15: 위성 이미지 배치](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. 분석 결과 열람 (S3 출력 버킷)

감지 결과(`detections/*.json`), 지리 메타데이터(`enriched/*.json`),
타일 정보(`tiles/*/metadata.json`)가 정리되어 저장된다.

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     내용: S3 콘솔에서 detections/, enriched/, tiles/ 의 3개 프리픽스를 조감
     마스크: 계정 ID, 버킷명 프리픽스 -->
![UC15: S3 출력 버킷](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. 변화 감지 경보 (SNS 이메일 알림)

일반 직원(운영 담당자)이 수신하는 SNS 경보 이메일.
변화 면적이 임계값(기본 1 km²)을 초과한 경우 자동 전송된다.

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     내용: 이메일 클라이언트(Gmail/Outlook)에서 alert_type=SATELLITE_CHANGE_DETECTED 표시
     마스크: 수신자 이메일 주소, 발신자 주소, 실제 좌표, tile_id -->
![UC15: SNS 경보 알림 이메일](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. 감지 결과 JSON 의 내용

감지 결과(레이블, 신뢰도, bbox)의 깔끔한 JSON 뷰어.

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     내용: S3 콘솔에서 오브젝트 미리보기, detections JSON 의 내용
     마스크: 계정 ID -->
![UC15: 감지 결과 JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
위성 이미지 분석(물체 감지·변화 감지·경보)의 자동화를 통해 정보 분석의 신속화를 실현한다.

### Metrics
| 메트릭 | 목표값 (예) |
|-----------|------------|
| 처리 완료 이미지 수 / 실행 | > 50 images |
| 물체 감지 정확도 | > 80% |
| 변화 감지 성공률 | > 85% |
| 경보 생성 시간 | < 5 분 |
| 비용 / 실행 | < $15 |
| Human Review 필수율 | 100% (경보 발보 전에 인간 승인 필수) |

> **100% Human Review 의 이유**: 경보의 오발보·누락이 미치는 업무 영향이 매우 크기 때문에 전건의 인간 승인을 필수로 합니다.

### Measurement Method
Step Functions 실행 이력, Rekognition 감지 결과, Bedrock 분석 보고서, SNS 알림 로그, CloudWatch Metrics. 승인 기록은 DynamoDB 에 저장하여 감사 시 "누가·언제·무엇을 승인했는가" 를 추적할 수 있도록 한다.

## 배포

### 사전 검증

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 원샷 배포

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### 수동 배포

```bash
# 전제: AWS SAM CLI 가 필요합니다. sam build 가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**중요**: `S3AccessPointName` 은 S3 AP 의 IAM 권한 부여에 필수입니다.
자세한 내용은 [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md) 를 참조하세요.

## 디렉터리 구성

```
defense-satellite/
├── template.yaml              # SAM 템플릿 (개발용)
├── template-deploy.yaml       # CloudFormation 템플릿 (배포용)
├── functions/
│   ├── discovery/handler.py   # 신규 위성 이미지 감지
│   ├── tiling/handler.py      # 타일 분할 + COG 변환
│   ├── object_detection/handler.py  # 물체 감지 (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # 시계열 변화 감지
│   ├── geo_enrichment/handler.py    # 지리 메타데이터 부여
│   └── alert_generation/handler.py  # 경보 생성
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## AWS 문서 링크

| 서비스 | 문서 |
|---------|------------|
| FSx for ONTAP | [사용자 가이드](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [개발자 가이드](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [개발자 가이드](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [개발자 가이드](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [사용자 가이드](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Well-Architected Framework 대응

| 기둥 | 대응 |
|----|------|
| 운영 우수성 | X-Ray, EMF, 경보 생성, 100% Human Review |
| 보안 | DoD CC SRG, FedRAMP, 최소 권한 IAM, KMS, VPC 분리 |
| 신뢰성 | Step Functions Retry/Catch, resilience 테스트, 폴백 |
| 성능 효율성 | COG 타일링, 병렬 물체 감지, SageMaker Batch |
| 비용 최적화 | 서버리스, SageMaker 스팟, 타일 단위 처리 |
| 지속 가능성 | 온디맨드 실행, 차분 변화 감지 |





---

## 비용 견적 (월액 개산)

> **주의**: 다음은 ap-northeast-1 리전의 개산이며, 실제 비용은 사용량에 따라 다릅니다. 최신 요금은 [AWS Pricing Calculator](https://calculator.aws/) 에서 확인하세요.

### 서버리스 컴포넌트 (종량 과금)

| 서비스 | 단가 | 상정 사용량 | 월액 개산 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 함수 × 10 scenes/일 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/일 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/일 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/실행 | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/쿼리 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/일 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/월 | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### 고정 비용 (FSx for ONTAP — 기존 환경 전제)

| 컴포넌트 | 월액 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (기존 환경 공유) |
| S3 Access Point | 추가 요금 없음 (S3 API 요금만) |

### 합계 개산

| 구성 | 월액 개산 |
|------|---------|
| 최소 구성 (일 1회 실행) | ~$5-15 |
| 표준 구성 (시간별 실행) | ~$15-50 |
| 대규모 구성 (고빈도 + 알람) | ~$50-150 |

> **Governance Caveat**: 비용 견적은 개산이며 보증값이 아닙니다. 실제 청구액은 사용 패턴, 데이터 양, 리전에 따라 다릅니다.

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

자세한 내용은 [로컬 테스트 퀵 스타트](../docs/local-testing-quick-start.md) 를 참조하세요.

---

## 출력 샘플 (Output Sample)

위성 이미지 분석 파이프라인의 출력 예 (Human Review 필수):

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **주의**: 위 내용은 샘플 출력이며, 실제 값은 환경·입력 데이터에 따라 다릅니다. 벤치마크 수치는 sizing reference 이며 service limit 이 아닙니다.

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 조직은 적격한 전문가에게 상담해야 합니다.

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP 의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) 를 참조하세요.
