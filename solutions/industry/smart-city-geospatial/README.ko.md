# UC17: 스마트시티 — 지리공간 데이터 분석·도시 계획

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **문서**: [아키텍처](docs/architecture.md) | [데모 스크립트](docs/demo-guide.md) | [문제 해결](../docs/phase7-troubleshooting.md)

## 개요

FSx for ONTAP S3 Access Points 를 활용한 지리공간 데이터(GIS)의
자동 분석 파이프라인. 도시 계획, 인프라 모니터링, 재난 대응을 위한
위성 이미지·LiDAR·IoT 센서 데이터를 통합 처리한다.

## 유스케이스

지방자치단체·도시 계획 기관이 여러 소스의 지리공간 데이터를 통합하여,
도시 인프라 상태 모니터링, 변화 감지, 재난 위험 평가를 자동화한다.

### 처리 흐름

```
FSx for ONTAP (GIS 데이터 저장 — 부서별 접근 제어)
  → S3 Access Point
    → Step Functions 워크플로
      → Discovery: 신규 데이터 감지 (GeoTIFF, Shapefile, GeoJSON, LAS)
      → Preprocessing: 좌표계 변환·정규화 (EPSG 통일, EPSG:4326)
      → LandUseClassification: 토지 이용 분류 (ML 추론)
      → ChangeDetection: 시계열 변화 감지 (건물 신축, 녹지 감소)
      → InfraAssessment: 인프라 열화 평가 (도로, 교량, LAS 점군)
      → RiskMapping: 재난 위험 지도 생성 (홍수, 지진, 산사태)
      → ReportGeneration: 도시 계획 보고서 생성 (Bedrock Nova Lite)
```

### 대상 데이터

| 데이터 형식 | 설명 | 일반적 크기 |
|-----------|------|-----------|
| GeoTIFF | 항공사진·위성 이미지 | 100 MB – 10 GB |
| Shapefile (.shp) | 벡터 데이터(도로, 건물, 구획) | 1 – 500 MB |
| GeoJSON | 경량 벡터 데이터 | 1 KB – 100 MB |
| LAS / LAZ | LiDAR 점군(지형·건물 3D) | 100 MB – 5 GB |
| GeoPackage (.gpkg) | OGC 표준 GIS 데이터베이스 | 10 MB – 2 GB |

### AWS 서비스

| 서비스 | 용도 |
|---------|------|
| FSx for ONTAP | GIS 데이터의 영구 스토리지(부서별 NTFS ACL) |
| S3 Access Points | 서버리스에서의 데이터 접근 |
| Step Functions | 워크플로 오케스트레이션 |
| Lambda | 전처리, 좌표 변환, 메타데이터 추출 |
| SageMaker (Batch Transform) | 토지 이용 분류, 변화 감지 ML 추론(옵션) |
| Amazon Rekognition | 항공사진에서 객체 감지(건물, 차량) |
| Amazon Bedrock Nova Lite | 일본어 도시 계획 보고서 생성 |
| DynamoDB | 시계열 토지 이용 이력, 변화 감지 |
| SNS | 이상 감지 알림 |
| CloudWatch | 관측성 |

### Public Sector 적합성

- **INSPIRE 지침 대응**(EU 지리공간 데이터 기반)
- **OGC 표준 준수**: WMS, WFS, WCS, GeoPackage
- **오픈 데이터**: 처리 결과를 시민용 포털에 공개 가능
- **재난 대응**: 실시간 피해 상황 매핑
- **데이터 주권**: 자치단체 데이터는 리전 내에서 완결

### 활용 시나리오

| 시나리오 | 입력 데이터 | 출력 |
|---------|-----------|------|
| 도시 녹화 모니터링 | 위성 이미지(시계열) | 녹지 면적 변화 보고서 |
| 불법 투기 감지 | 드론 이미지 | 알림 + 위치 정보 |
| 도로 열화 평가 | 차량 탑재 카메라 이미지 | 보수 우선순위 지도 |
| 홍수 위험 평가 | LiDAR + 강우 데이터 | 침수 예측 지도 |
| 건축 확인 지원 | 항공사진 + 건축 신청 | 차이 감지 보고서 |

## 검증된 화면(스크린샷)

### 1. GIS 데이터 저장(S3 Access Point 경유)

자치단체 GIS 담당자 관점에서 본, 분석 대상 데이터의 배치 확인 화면.
`gis/YYYY/MM/` 프리픽스 아래에 GeoTIFF / Shapefile / LAS 를 배치.

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     내용: S3 AP 의 gis/ 프리픽스 목록, 파일 형식이 혼재
     마스크: 계정 ID, S3 AP ARN, 실제 좌표에서 유래한 파일명 -->
![UC17: GIS 데이터 저장 확인](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Bedrock 생성 도시 계획 보고서(Markdown 표시)

**UC17 의 핵심 기능**: 토지 이용 분포·변화 감지·위험 평가를 통합하여,
Bedrock Nova Lite 가 자치단체 담당자용으로 일본어 보고서를 자동 생성한다.

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     내용: S3 콘솔에서 reports/*.md 를 렌더링 표시
     실제 샘플 내용:
       ### 자치단체 담당자용 소견 보고서
       #### 도시 계획상의 주목점
       GIS 데이터에 따르면, 시내의 토지 이용 분포는 안정적이며...
       #### 우선해야 할 대책안
       1. 홍수 대책 강화 ... 2. 지진 대책 강화 ... 3. 사면 붕괴 대책 강화 ...
     마스크: 계정 ID, 자치단체명(샘플명만 표시) -->
![UC17: Bedrock 생성 보고서](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. 재난 위험 지도 JSON

홍수·지진·산사태 3 종류의 위험 점수를 CRITICAL / HIGH / MEDIUM / LOW
4 단계로 판정.

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     내용: risk-maps/*.json 의 정형 뷰(flood, earthquake, landslide 의 level 강조)
     마스크: 계정 ID -->
![UC17: 재난 위험 지도](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. 토지 이용 분포(JSON)

Rekognition / SageMaker 추론 결과에서 도출된 토지 이용 클래스 분포.
residential / commercial / forest / water / road 등의 비율.

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     내용: landuse/*.json 의 내용(residential: 0.5, forest: 0.3 등)
     마스크: 계정 ID -->
![UC17: 토지 이용 분포](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. 시계열 변화 시각화(DynamoDB Explorer)

`fsxn-uc17-demo-landuse-history` 테이블. area_id 별로 과거의 토지 이용 분포와
현재 값을 비교하여 change_magnitude 를 계산.

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     내용: DynamoDB Explorer 에서 landuse-history 테이블의 시계열 항목
     마스크: 계정 ID, area_id -->
![UC17: 시계열 변화 테이블](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
지리공간 분석(CRS 정규화·토지 이용 분류·재난 위험 매핑)의 자동화를 통해 도시 계획의 의사결정을 지원한다.

### Metrics
| 메트릭 | 목표값(예) |
|-----------|------------|
| 처리 완료 데이터셋 수 / 실행 | > 100 files |
| CRS 정규화 성공률 | > 95% |
| 토지 이용 분류 정확도 | > 80% |
| 위험 지도 생성 시간 | < 10 분 |
| 비용 / 실행 | < $10 |
| Human Review 대상 비율 | < 20%(분류 불확실 영역) |

### Measurement Method
Step Functions 실행 이력, Bedrock 분석 보고서, Rekognition 감지 결과, S3 출력 GeoJSON, CloudWatch Metrics.

## 배포

### 사전 검증

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 원샷 배포

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### 수동 배포

```bash
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=apac.amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**중요**: Bedrock 콘솔에서 `apac.amazon.nova-lite-v1:0` 의 모델 접근을 활성화하세요.

## 디렉터리 구성

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS 정규화 (EPSG:4326)
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ 점군 분석
│   ├── risk_mapping/handler.py           # 홍수/지진/산사태 위험
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## AWS 문서 링크

| 서비스 | 문서 |
|---------|------------|
| FSx for ONTAP | [사용자 가이드](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [개발자 가이드](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [개발자 가이드](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [개발자 가이드](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [사용자 가이드](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework 대응

| 기둥 | 대응 |
|----|------|
| 운영 우수성 | X-Ray, EMF, 토지 이용 변화 추적, resilience 테스트 |
| 보안 | 최소 권한 IAM, KMS, 부서별 NTFS ACL, INSPIRE 준수 |
| 신뢰성 | Step Functions Retry/Catch, CRS 정규화, resilience 테스트 |
| 성능 효율성 | GeoTIFF 타일링, SageMaker Batch Transform |
| 비용 최적화 | 서버리스, SageMaker 스팟, DynamoDB 시계열 |
| 지속 가능성 | 차분 변화 감지, OGC 표준 준수 |





---

## 비용 견적(월간 개략)

> **참고**: 아래는 ap-northeast-1 리전의 개략치이며, 실제 비용은 사용량에 따라 다릅니다. 최신 요금은 [AWS Pricing Calculator](https://calculator.aws/) 에서 확인하세요.

### 서버리스 컴포넌트(종량제)

| 서비스 | 단가 | 예상 사용량 | 월간 개략 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 함수 × 20 datasets/일 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/일 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/일 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/실행 | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/쿼리 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/일 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/월 | ~$0.76 |

### 고정 비용(FSx for ONTAP — 기존 환경 전제)

| 컴포넌트 | 월간 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (기존 환경 공유) |
| S3 Access Point | 추가 요금 없음(S3 API 요금만) |

### 합계 개략

| 구성 | 월간 개략 |
|------|---------|
| 최소 구성(일 1 회 실행) | ~$5-15 |
| 표준 구성(시간별 실행) | ~$15-50 |
| 대규모 구성(고빈도 + 알람) | ~$50-150 |

> **Governance Caveat**: 비용 견적은 개략치이며 보증값이 아닙니다. 실제 청구액은 사용 패턴, 데이터 양, 리전에 따라 다릅니다.

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
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
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

지리공간 데이터 분석 파이프라인의 출력 예:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **참고**: 위는 샘플 출력이며, 실제 값은 환경·입력 데이터에 따라 다릅니다. 벤치마크 수치는 sizing reference 이며 service limit 이 아닙니다.

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 조직은 적격한 전문가와 상담하세요.

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP 의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) 를 참조하세요.
