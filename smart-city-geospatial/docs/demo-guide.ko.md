# UC17 데모 스크립트 (30분 세션)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## 전제 조건

- AWS 계정, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Bedrock Nova Lite v1:0 모델 활성화

## 타임라인

### 0:00 - 0:05 인트로 (5분)

- 지자체의 과제: 도시 계획, 재해 대응, 인프라 보전에서 GIS 데이터 활용 증가
- 기존 과제: GIS 분석은 ArcGIS / QGIS의 전문 소프트웨어 중심
- 제안: FSxN S3AP + 서버리스로 자동화

### 0:05 - 0:10 아키텍처 (5분)

- CRS 정규화의 중요성 (혼재하는 데이터 소스)
- Bedrock에 의한 도시 계획 보고서 생성
- 리스크 모델 (홍수·지진·산사태)의 계산식

### 0:10 - 0:15 배포 (5분)

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-uc17-demo \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### 0:15 - 0:22 처리 실행 (7분)

```bash
# 샘플 항공 사진 업로드 (센다이시 일부)
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# Step Functions 실행
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

결과 확인:
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json` (CRS 정보)
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json` (토지 이용 분포)
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json` (재해 리스크 점수)
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md` (Bedrock 생성 보고서)

### 0:22 - 0:27 리스크 맵 해설 (5분)

- DynamoDB `landuse-history` 테이블에서 시계열 변화 확인
- Bedrock 생성 보고서의 마크다운 표시
- 홍수·지진·산사태 리스크 점수의 시각화

### 0:27 - 0:30 Wrap-up (3분)

- Amazon Location Service와의 연계 가능성
- 본격 운영 시 점군 처리 (LAS Layer 배포)
- 다음 단계: MapServer 연계, 시민 대상 포털

## 자주 묻는 질문과 답변

**Q. CRS 변환은 실제로 수행되나요?**  
A. rasterio / pyproj Layer 배치 시에만. `PYPROJ_AVAILABLE` 체크로 폴백.

**Q. Bedrock 모델의 선택 기준은?**  
A. Nova Lite는 비용/정확도 균형이 우수. 장문이 필요하면 Claude Sonnet 권장.
A. Nova Lite는 일본어 보고서 생성에서 비용 효율이 높음. Claude 3 Haiku는 정확도 우선 시 대안.

---

## 출력 대상에 대해: OutputDestination으로 선택 가능 (Pattern B)

UC17 smart-city-geospatial은 2026-05-11 업데이트에서 `OutputDestination` 파라미터를 지원합니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: CRS 정규화 메타데이터 / 토지 이용 분류 / 인프라 평가 / 리스크 맵 / Bedrock 생성 보고서

**2가지 모드**:

### STANDARD_S3 (기본값, 기존 방식)
새로운 S3 버킷 (`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고,
AI 산출물을 거기에 기록합니다. Discovery Lambda의 manifest만 S3 Access Point
에 기록됩니다 (기존 방식).

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP ("no data movement" 패턴)
CRS 정규화 메타데이터, 토지 이용 분류 결과, 인프라 평가, 리스크 맵, Bedrock이 생성하는
도시 계획 보고서 (Markdown)를 FSxN S3 Access Point 경유로 원본 GIS 데이터와
**동일한 FSx ONTAP 볼륨**에 다시 기록합니다.
도시 계획 담당자가 SMB/NFS의 기존 디렉터리 구조 내에서 AI 산출물을 직접 참조할 수 있습니다.
표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (기타 필수 파라미터)
```

**주의사항**:

- `S3AccessPointName` 지정을 강력히 권장 (Alias 형식과 ARN 형식 모두 IAM 허가)
- 5GB 초과 객체는 FSxN S3AP에서 불가 (AWS 사양), 멀티파트 업로드 필수
- ChangeDetection Lambda는 DynamoDB만 사용하므로 `OutputDestination`의 영향을 받지 않음
- Bedrock 보고서는 Markdown (`text/markdown; charset=utf-8`)으로 기록되므로 SMB/NFS
  클라이언트의 텍스트 에디터에서 직접 열람 가능
- AWS 사양상의 제약은
  [프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
  및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 합니다. 기술자 대상 뷰 (Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ✅ **E2E 검증**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX 촬영**: ✅ 완료 (Phase 8 Theme D, commit d7ebabd)

### 기존 스크린샷 (Phase 7 검증 시)

![Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc17-demo/step-functions-graph-succeeded.png)

![S3 출력 버킷](../../docs/screenshots/masked/uc17-demo/s3-output-bucket.png)

![DynamoDB landuse_history 테이블](../../docs/screenshots/masked/uc17-demo/dynamodb-landuse-history-table.png)
### 재검증 시 UI/UX 대상 화면 (권장 촬영 목록)

- S3 출력 버킷 (tiles/, land-use/, change-detection/, risk-maps/, reports/)
- Bedrock 생성 도시 계획 보고서 (Markdown 미리보기)
- DynamoDB landuse_history 테이블 (토지 이용 분류 이력)
- 리스크 맵 JSON 미리보기 (CRITICAL/HIGH/MEDIUM/LOW 분류)
- FSx ONTAP 볼륨 상의 AI 산출물 (FSXN_S3AP 모드 시 — SMB/NFS로 열람 가능한 Markdown 보고서)

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인 (공통 VPC/S3 AP 유무)
   - `UC=smart-city-geospatial bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC17`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `gis/` 프리픽스에 샘플 GeoTIFF 업로드
   - Step Functions `fsxn-smart-city-geospatial-demo-workflow` 시작 (입력 `{}`)

3. **촬영** (CloudShell·터미널은 닫기, 브라우저 우측 상단 사용자 이름은 마스킹):
   - S3 출력 버킷 `fsxn-smart-city-geospatial-demo-output-<account>`의 전체 보기
   - Bedrock 보고서 Markdown의 브라우저 미리보기
   - DynamoDB landuse_history 테이블의 항목 목록
   - 리스크 맵 JSON의 구조 확인

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py smart-city-geospatial-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크 (필요 시)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC17`로 삭제
   - VPC Lambda ENI 해제에 15-30분 (AWS 사양)
