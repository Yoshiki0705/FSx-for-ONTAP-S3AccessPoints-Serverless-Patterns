# BIM 모델 변경 감지 및 안전 컴플라이언스 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 BIM 모델의 변경 감지 및 안전 컴플라이언스 체크 파이프라인을 실연한다. 설계 변경을 자동 감지하고 건축 기준 적합성을 검증한다.

**데모의 핵심 메시지**: BIM 모델의 변경을 자동 추적하고 안전 기준 위반을 즉시 감지. 설계 리뷰 사이클을 단축한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 상세 |
|------|------|
| **직책** | BIM 매니저 / 구조 설계 엔지니어 |
| **일상 업무** | BIM 모델 관리, 설계 변경 리뷰, 컴플라이언스 확인 |
| **과제** | 여러 팀의 설계 변경을 추적하고 기준 적합성을 확인하는 것이 어려움 |
| **기대하는 성과** | 변경의 자동 감지와 안전 기준 체크의 효율화 |

### Persona: 김씨(BIM 매니저)

- 대규모 건설 프로젝트에서 20개 이상의 설계 팀이 병렬 작업
- 일일 설계 변경이 안전 기준에 영향을 미치지 않는지 확인 필요
- "변경이 있으면 자동으로 안전 체크를 실행하고 싶다"

---

## Demo Scenario: 설계 변경의 자동 감지 및 안전 검증

### 워크플로우 전체 구조

```
BIM 모델 업데이트     변경 감지        컴플라이언스     리뷰 레포트
(IFC/RVT)    →   차분 분석    →   규칙 대조     →    AI 생성
                  요소 비교        안전 기준 체크
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 대규모 프로젝트에서 20개 팀이 병렬로 BIM 모델을 업데이트. 변경이 안전 기준을 위반하지 않는지 수동 확인으로는 따라잡을 수 없다.

**Key Visual**: BIM 모델 파일 목록, 여러 팀의 업데이트 이력

### Section 2: Change Detection(0:45–1:30)

**내레이션 요지**:
> 모델 파일의 업데이트를 감지하고 이전 버전과의 차이를 자동 분석. 변경된 요소(구조 부재, 설비 배치 등)를 특정.

**Key Visual**: 변경 감지 트리거, 차분 분석 시작

### Section 3: Compliance Check(1:30–2:30)

**내레이션 요지**:
> 변경된 요소에 대해 안전 기준 규칙을 자동 대조. 내진 기준, 방화 구획, 피난 경로 등의 적합성을 검증.

**Key Visual**: 규칙 대조 처리 중, 체크 항목 목록

### Section 4: Results Analysis(2:30–3:45)

**내레이션 요지**:
> 검증 결과를 확인. 위반 항목, 영향 범위, 중요도를 일람 표시.

**Key Visual**: 위반 감지 결과 테이블, 중요도별 분류

### Section 5: Review Report(3:45–5:00)

**내레이션 요지**:
> AI가 설계 리뷰 레포트를 생성. 위반의 상세 내용, 시정안, 영향을 받는 다른 설계 요소를 제시.

**Key Visual**: AI 생성 리뷰 레포트

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | BIM 모델 파일 목록 | Section 1 |
| 2 | 변경 감지·차분 표시 | Section 2 |
| 3 | 컴플라이언스 체크 진행 | Section 3 |
| 4 | 위반 감지 결과 | Section 4 |
| 5 | AI 리뷰 레포트 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "병렬 작업의 변경 추적과 안전 확인이 따라잡을 수 없다" |
| Detection | 0:45–1:30 | "모델 업데이트를 자동 감지하고 차이를 분석" |
| Compliance | 1:30–2:30 | "안전 기준 규칙을 자동 대조" |
| Results | 2:30–3:45 | "위반 항목과 영향 범위를 즉시 파악" |
| Report | 3:45–5:00 | "시정안과 영향 분석을 AI가 제시" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 베이스 BIM 모델(IFC 형식) | 비교 원본 |
| 2 | 변경 후 모델(구조 변경 있음) | 차분 감지 데모 |
| 3 | 안전 기준 위반 모델(3건) | 컴플라이언스 데모 |

---

## Timeline

### 1주일 이내에 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 BIM 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 3D 비주얼라이제이션 연계
- 실시간 변경 알림
- 시공 단계와의 정합성 체크

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Change Detector) | BIM 모델 차분 분석 |
| Lambda (Compliance Checker) | 안전 기준 규칙 대조 |
| Lambda (Report Generator) | Bedrock에 의한 리뷰 레포트 생성 |
| Amazon Athena | 변경 이력·위반 데이터 집계 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| IFC 파싱 실패 | 사전 분석 완료 데이터 사용 |
| 규칙 대조 지연 | 사전 검증 완료 결과 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대해: OutputDestination으로 선택 가능 (Pattern B)

UC10 construction-bim은 2026-05-10 업데이트에서 `OutputDestination` 파라미터를 지원했습니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: 건설 BIM / 도면 OCR / 안전 컴플라이언스 체크

**2가지 모드**:

### STANDARD_S3(기본값, 기존과 동일)
새로운 S3 버킷(`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고
AI 산출물을 거기에 기록합니다.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP("no data movement" 패턴)
AI 산출물을 FSxN S3 Access Point 경유로 원본 데이터와 **동일한 FSx ONTAP 볼륨**에
다시 기록합니다. SMB/NFS 사용자가 업무에서 사용하는 디렉터리 구조 내에서 AI 산출물을
직접 열람할 수 있습니다. 표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
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
보는 UI/UX 화면**을 대상으로 한다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ✅ **E2E 실행**: Phase 1-6에서 확인 완료(루트 README 참조)
- 📸 **UI/UX 재촬영**: ✅ 2026-05-10 재배포 검증에서 촬영 완료 (UC10 Step Functions 그래프, Lambda 실행 성공 확인)
- 🔄 **재현 방법**: 본 문서 말미의 "촬영 가이드" 참조

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC10 Step Functions Graph view(SUCCEEDED)

![UC10 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색으로 시각화하는 최종 사용자 최중요 화면.

### 기존 스크린샷(Phase 1-6에서 해당 분)

![UC10 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph(줌 표시 — 각 단계 상세)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(drawings-ocr/, bim-metadata/, safety-reports/)
- Textract 도면 OCR 결과(Cross-Region)
- BIM 버전 차분 레포트
- Bedrock 안전 컴플라이언스 체크

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=construction-bim bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC10`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `drawings/` 프리픽스에 샘플 파일 업로드
   - Step Functions `fsxn-construction-bim-demo-workflow` 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자 이름은 검은색 칠)
   - S3 출력 버킷 `fsxn-construction-bim-demo-output-<account>`의 조감
   - AI/ML 출력 JSON 미리보기(`build/preview_*.html` 형식 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py construction-bim-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC10`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
