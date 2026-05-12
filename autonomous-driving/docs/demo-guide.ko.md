# 주행 데이터 전처리·어노테이션 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 자율주행 개발에서의 주행 데이터 전처리 및 어노테이션 파이프라인을 실연합니다. 대량의 센서 데이터를 자동 분류·품질 체크하여 학습 데이터셋을 효율적으로 구축합니다.

**데모의 핵심 메시지**: 주행 데이터의 품질 검증과 메타데이터 부여를 자동화하여 AI 학습용 데이터셋 구축을 가속화합니다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 상세 |
|------|------|
| **직책** | 데이터 엔지니어 / ML 엔지니어 |
| **일상 업무** | 주행 데이터 관리, 어노테이션, 학습 데이터셋 구축 |
| **과제** | 대량의 주행 데이터에서 유용한 장면을 효율적으로 추출할 수 없음 |
| **기대하는 성과** | 데이터 품질의 자동 검증과 장면 분류의 효율화 |

### Persona: 이토 씨(데이터 엔지니어)

- 매일 TB 단위의 주행 데이터가 축적
- 카메라·LiDAR·레이더의 동기화 확인이 수동
- "품질이 좋은 데이터만 자동으로 학습 파이프라인에 보내고 싶다"

---

## Demo Scenario: 주행 데이터 배치 전처리

### 워크플로우 전체 구조

```
주행 데이터        데이터 검증       장면 분류        데이터셋
(ROS bag 등)  →   품질 체크    →  메타데이터   →   카탈로그 생성
                  동기화 확인      부여 (AI)
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 매일 TB 단위로 축적되는 주행 데이터. 품질이 나쁜 데이터(센서 결손, 동기화 오류)가 혼재되어 있어 수동 선별은 비현실적입니다.

**Key Visual**: 주행 데이터 폴더 구조, 데이터 양의 시각화

### Section 2: Pipeline Trigger(0:45–1:30)

**내레이션 요지**:
> 신규 주행 데이터가 업로드되면 전처리 파이프라인이 자동 시작됩니다.

**Key Visual**: 데이터 업로드 → 워크플로우 자동 시작

### Section 3: Quality Validation(1:30–2:30)

**내레이션 요지**:
> 센서 데이터의 완전성 체크: 프레임 결손, 타임스탬프 동기화, 데이터 손상을 자동 감지합니다.

**Key Visual**: 품질 체크 결과 — 센서별 건전성 스코어

### Section 4: Scene Classification(2:30–3:45)

**내레이션 요지**:
> AI가 장면을 자동 분류: 교차로, 고속도로, 악천후, 야간 등. 메타데이터로 부여합니다.

**Key Visual**: 장면 분류 결과 테이블, 카테고리별 분포

### Section 5: Dataset Catalog(3:45–5:00)

**내레이션 요지**:
> 품질 검증 완료 데이터의 카탈로그를 자동 생성. 장면 조건으로 검색 가능한 데이터셋으로 활용 가능합니다.

**Key Visual**: 데이터셋 카탈로그, 검색 인터페이스

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 주행 데이터 폴더 구조 | Section 1 |
| 2 | 파이프라인 시작 화면 | Section 2 |
| 3 | 품질 체크 결과 | Section 3 |
| 4 | 장면 분류 결과 | Section 4 |
| 5 | 데이터셋 카탈로그 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "TB 단위의 데이터에서 유용한 장면을 수동 선별은 불가능" |
| Trigger | 0:45–1:30 | "업로드로 자동으로 전처리 시작" |
| Validation | 1:30–2:30 | "센서 결손·동기화 오류를 자동 감지" |
| Classification | 2:30–3:45 | "AI가 장면을 자동 분류하고 메타데이터 부여" |
| Catalog | 3:45–5:00 | "검색 가능한 데이터셋 카탈로그를 자동 생성" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 정상 주행 데이터(5 세션) | 베이스라인 |
| 2 | 프레임 결손 데이터(2건) | 품질 체크 데모 |
| 3 | 다양한 장면 데이터(교차로, 고속, 야간) | 분류 데모 |

---

## Timeline

### 1주일 이내에 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 주행 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 3D 어노테이션 자동 생성
- 액티브 러닝에 의한 데이터 선택
- 데이터 버저닝 통합

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Python 3.13) | 센서 데이터 품질 검증, 장면 분류, 카탈로그 생성 |
| Lambda SnapStart | 콜드 스타트 감소(`EnableSnapStart=true`로 옵트인) |
| SageMaker (4-way routing) | 추론(Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | 진정한 scale-to-zero(`EnableInferenceComponents=true`) |
| Amazon Bedrock | 장면 분류·어노테이션 제안 |
| Amazon Athena | 메타데이터 검색·집계 |
| CloudFormation Guard Hooks | 배포 시 보안 정책 강제 |

### 로컬 테스트 (Phase 6A)

```bash
# SAM CLI로 로컬 테스트
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### 폴백

| 시나리오 | 대응 |
|---------|------|
| 대용량 데이터 처리 지연 | 서브셋으로 실행 |
| 분류 정확도 부족 | 사전 분류 완료 결과를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대해: OutputDestination으로 선택 가능 (Pattern B)

UC9 autonomous-driving은 2026-05-10 업데이트로 `OutputDestination` 파라미터를 지원합니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: ADAS / 자율주행 데이터(프레임 추출, 점군 QC, 어노테이션, 추론)

**2가지 모드**:

### STANDARD_S3(기본값, 기존과 동일)
새로운 S3 버킷(`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고,
AI 산출물을 거기에 기록합니다.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP("no data movement" 패턴)
AI 산출물을 FSxN S3 Access Point 경유로 원본 데이터와**동일한 FSx ONTAP 볼륨**에
다시 기록합니다. SMB/NFS 사용자가 업무에서 사용하는 디렉터리 구조 내에서 AI 산출물을
직접 열람할 수 있습니다. 표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (기타 필수 파라미터)
```

**주의사항**:

- `S3AccessPointName` 지정을 강력히 권장(Alias 형식과 ARN 형식 모두 IAM 허가)
- 5GB 초과 객체는 FSxN S3AP에서 불가(AWS 사양), 멀티파트 업로드 필수
- AWS 사양상의 제약은
  [프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
  및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 합니다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약합니다.

### 이 유스케이스의 검증 상태

- ⚠️ **E2E 검증**: 일부 기능만(프로덕션 환경에서는 추가 검증 권장)
- 📸 **UI/UX 촬영**: ✅ SFN Graph 완료(Phase 8 Theme D, commit 081cc66)

### 기존 스크린샷(Phase 1-6에서 해당분)

![UC9 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(keyframes/, annotations/, qc/)
- Rekognition 키프레임 객체 감지 결과
- LiDAR 점군 품질 체크 요약
- COCO 호환 어노테이션 JSON

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=autonomous-driving bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC9`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `footage/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-autonomous-driving-demo-workflow`를 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자 이름은 검은색 처리):
   - S3 출력 버킷 `fsxn-autonomous-driving-demo-output-<account>`의 전체 보기
   - AI/ML 출력 JSON의 미리보기(`build/preview_*.html` 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py autonomous-driving-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC9`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
