# UC15 데모 스크립트 (30분 세션)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## 전제 조건

- AWS 계정, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `defense-satellite/template-deploy.yaml` 배포 완료(`EnableSageMaker=false`)

## 타임라인

### 0:00 - 0:05 인트로(5분)

- 유스케이스 배경: 위성 이미지 데이터 증가(Sentinel, Landsat, 상용 SAR)
- 기존 NAS의 과제: 복사 기반 워크플로로 인한 시간 및 비용 소요
- FSxN S3AP의 장점: zero-copy, NTFS ACL 연동, 서버리스 처리

### 0:05 - 0:10 아키텍처 설명(5분)

- Mermaid 다이어그램으로 Step Functions 워크플로 소개
- 이미지 크기에 따른 Rekognition / SageMaker 전환 로직
- geohash를 통한 변화 감지 메커니즘

### 0:10 - 0:15 라이브 배포(5분)

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-uc15-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:20 샘플 이미지 처리(5분)

```bash
# 샘플 GeoTIFF 업로드
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Step Functions 실행
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- AWS 콘솔에서 Step Functions 그래프 표시(Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration)
- SUCCEEDED까지의 실행 시간 확인(일반적으로 2-3분)

### 0:20 - 0:25 결과 확인(5분)

- S3 출력 버킷의 계층 구조 표시:
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- CloudWatch Logs에서 EMF 메트릭 확인
- DynamoDB `change-history` 테이블에서 변화 감지 이력 확인

### 0:25 - 0:30 Q&A + 마무리(5분)

- Public Sector 규제 대응(DoD CC SRG, CSfC, FedRAMP)
- GovCloud 마이그레이션 경로(동일한 템플릿으로 `ap-northeast-1` → `us-gov-west-1`)
- 비용 최적화(SageMaker Endpoint는 실제 운영 시에만 활성화)
- 다음 단계: 다중 위성 프로바이더 통합, Sentinel-1/2 Hub 연계

## 자주 묻는 질문과 답변

**Q. SAR 데이터(Sentinel-1의 HDF5)는 어떻게 처리하나요?**  
A. Discovery Lambda에서 `image_type=sar`로 분류, Tiling은 HDF5 파서 구현 가능(rasterio 또는 h5py). Object Detection은 전용 SAR 분석 모델(SageMaker) 필수.

**Q. 이미지 크기 임계값(5MB)의 근거는?**  
A. Rekognition DetectLabels API의 Bytes 파라미터 상한. S3 경유 시 15MB까지 가능. 프로토타입은 Bytes 경로 채택.

**Q. 변화 감지의 정확도는?**  
A. 현재 구현은 bbox 면적 기반의 간단한 비교. 본격 운영에서는 SageMaker의 시맨틱 세그멘테이션 권장.

---

## 출력 대상 정보: OutputDestination으로 선택 가능 (Pattern B)

UC15 defense-satellite은 2026-05-11 업데이트에서 `OutputDestination` 파라미터를 지원합니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: 위성 이미지 타일링 / 객체 감지 / Geo enrichment

**2가지 모드**:

### STANDARD_S3(기본값, 기존 방식)
새로운 S3 버킷(`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고,
AI 산출물을 해당 버킷에 작성합니다. Discovery Lambda의 manifest만 S3 Access Point
에 작성됩니다(기존 방식 유지).

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP("no data movement" 패턴)
타일링 metadata, 객체 감지 JSON, Geo enrichment 완료 감지 결과를 FSxN S3 Access Point
경유로 원본 위성 이미지와 **동일한 FSx ONTAP 볼륨**에 다시 작성합니다.
분석 담당자가 SMB/NFS의 기존 디렉터리 구조 내에서 AI 산출물을 직접 참조할 수 있습니다.
표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (기타 필수 파라미터)
```

**주의사항**:

- `S3AccessPointName` 지정을 강력히 권장(Alias 형식과 ARN 형식 모두 IAM 허용)
- 5GB 초과 객체는 FSxN S3AP에서 불가(AWS 사양), 멀티파트 업로드 필수
- ChangeDetection Lambda는 DynamoDB만 사용하므로 `OutputDestination`의 영향을 받지 않습니다
- AlertGeneration Lambda는 SNS만 사용하므로 `OutputDestination`의 영향을 받지 않습니다
- AWS 사양상의 제약은
  [프로젝트 README의 "AWS 사양상의 제약과 해결 방법" 섹션](../../README.md#aws-仕様上の制約と回避策)
  및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17 및 UC6/11/14 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서
실제로 보는 UI/UX 화면**을 대상으로 합니다.
기술자용 뷰(Step Functions 그래프, CloudFormation 스택 이벤트 등)는
`docs/verification-results-*.md`에 통합되어 있습니다.

### 이 유스케이스의 검증 상태

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX**: Not yet captured

### 기존 스크린샷

![UC15 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc15-demo/uc15-stepfunctions-graph.png)

### 재검증 시 UI/UX 대상 화면 (권장 촬영 목록)

- S3 출력 버킷 (detections/, geo-enriched/, alerts/)
- Rekognition 위성 이미지 객체 감지 결과 JSON
- GeoEnrichment 좌표 태그 감지 결과
- SNS 알림 이메일
- FSx ONTAP 볼륨 AI 산출물 (FSXN_S3AP 모드)

### 촬영 가이드

1. **사전 준비**: `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인
2. **샘플 데이터**: S3 AP Alias를 통해 샘플 파일 업로드 후 Step Functions 워크플로우 시작
3. **촬영** (CloudShell/터미널 닫기, 브라우저 우측 상단 사용자 이름 마스킹)
4. **마스크**: `python3 scripts/mask_uc_demos.py <uc-dir>`로 자동 OCR 마스킹
5. **정리**: `bash scripts/cleanup_generic_ucs.sh <UC>`로 스택 삭제
