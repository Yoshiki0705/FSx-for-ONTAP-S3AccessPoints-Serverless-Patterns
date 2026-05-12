# VFX 렌더링 품질 체크 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 VFX 렌더링 출력의 품질 체크 파이프라인을 실연합니다. 렌더링 프레임의 자동 검증을 통해 아티팩트나 오류 프레임을 조기 검출합니다.

**데모의 핵심 메시지**: 대량의 렌더링 프레임을 자동 검증하고, 품질 문제를 즉시 검출. 재렌더링 판단을 신속화합니다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | VFX 슈퍼바이저 / 렌더링 TD |
| **일상 업무** | 렌더링 작업 관리, 품질 확인, 샷 승인 |
| **과제** | 수천 프레임의 육안 확인에 막대한 시간 소요 |
| **기대 성과** | 문제 프레임의 자동 검출과 재렌더링 판단의 신속화 |

### Persona: 나카무라 씨(VFX 슈퍼바이저)

- 1개 프로젝트에서 50개 이상 샷, 각 샷당 100~500 프레임
- 렌더링 완료 후 품질 확인이 병목 현상
- "블랙 프레임, 과도한 노이즈, 텍스처 누락을 자동으로 검출하고 싶다"

---

## Demo Scenario: 렌더링 배치 품질 검증

### 워크플로우 전체 구조

```
렌더링 출력     프레임 분석      품질 판정          QC 리포트
(EXR/PNG)     →   메타데이터    →   이상 검출    →    샷별
                   추출             (통계 분석)        요약
```

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 렌더링 팜에서 출력된 수천 프레임. 블랙 프레임, 노이즈, 텍스처 누락 등의 문제를 육안으로 확인하는 것은 비현실적입니다.

**Key Visual**: 렌더링 출력 폴더(대량의 EXR 파일)

### Section 2: Pipeline Trigger(0:45–1:30)

**내레이션 요지**:
> 렌더링 작업 완료 후, 품질 체크 파이프라인이 자동 시작. 샷 단위로 병렬 처리합니다.

**Key Visual**: 워크플로우 시작, 샷 목록

### Section 3: Frame Analysis(1:30–2:30)

**내레이션 요지**:
> 각 프레임의 픽셀 통계(평균 휘도, 분산, 히스토그램)를 산출. 프레임 간 일관성도 체크합니다.

**Key Visual**: 프레임 분석 처리 중, 픽셀 통계 그래프

### Section 4: Quality Assessment(2:30–3:45)

**내레이션 요지**:
> 통계적 이상치를 검출하여 문제 프레임을 특정. 블랙 프레임(휘도 제로), 과도한 노이즈(분산 이상) 등을 분류합니다.

**Key Visual**: 문제 프레임 목록, 카테고리별 분류

### Section 5: QC Report(3:45–5:00)

**내레이션 요지**:
> 샷별 QC 리포트를 생성. 재렌더링이 필요한 프레임 범위와 추정 원인을 제시합니다.

**Key Visual**: AI 생성 QC 리포트(샷별 요약 + 권장 대응)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 렌더링 출력 폴더 | Section 1 |
| 2 | 파이프라인 시작 화면 | Section 2 |
| 3 | 프레임 분석 진행 상황 | Section 3 |
| 4 | 문제 프레임 검출 결과 | Section 4 |
| 5 | QC 리포트 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "수천 프레임의 육안 확인은 비현실적" |
| Trigger | 0:45–1:30 | "렌더링 완료 시 자동으로 QC 시작" |
| Analysis | 1:30–2:30 | "픽셀 통계로 프레임 품질을 정량 평가" |
| Assessment | 2:30–3:45 | "문제 프레임을 자동 분류·특정" |
| Report | 3:45–5:00 | "재렌더링 판단을 즉시 지원" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 정상 프레임(100장) | 베이스라인 |
| 2 | 블랙 프레임(3장) | 이상 검출 데모 |
| 3 | 과도한 노이즈 프레임(5장) | 품질 판정 데모 |
| 4 | 텍스처 누락 프레임(2장) | 분류 데모 |

---

## Timeline

### 1주일 이내 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 프레임 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 딥러닝 기반 아티팩트 검출
- 렌더링 팜 연계(자동 재렌더링)
- 샷 트래킹 시스템 통합

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Frame Analyzer) | 프레임 메타데이터·픽셀 통계 추출 |
| Lambda (Quality Checker) | 통계적 품질 판정 |
| Lambda (Report Generator) | Bedrock을 통한 QC 리포트 생성 |
| Amazon Athena | 프레임 통계 집계 분석 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| 대용량 프레임 처리 지연 | 썸네일 분석으로 전환 |
| Bedrock 지연 | 사전 생성 리포트 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대하여: FSxN S3 Access Point (Pattern A)

UC4 media-vfx는 **Pattern A: Native S3AP Output**으로 분류됩니다
(`docs/output-destination-patterns.md` 참조).

**설계**: 렌더링 메타데이터, 프레임 품질 평가는 모두 FSxN S3 Access Point 경유로
원본 렌더링 애셋과 **동일한 FSx ONTAP 볼륨**에 기록됩니다. 표준 S3 버킷은
생성되지 않습니다("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력 데이터 읽기용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력 쓰기용 S3 AP Alias(입력과 동일해도 가능)

**배포 예시**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (기타 필수 파라미터)
```

**SMB/NFS 사용자 관점**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # 원본 렌더 프레임
  └── qc/shot_001/                     # 프레임 품질 평가(동일 볼륨 내)
      └── frame_0001_qc.json
```

AWS 사양상의 제약 사항에 대해서는
[프로젝트 README의 "AWS 사양상의 제약과 회피 방법" 섹션](../../README.md#aws-仕様上の制約と回避策)
및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조하십시오.

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17 및 UC6/11/14 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 합니다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약됩니다.

### 본 유스케이스의 검증 상태

- ⚠️ **E2E 검증**: 일부 기능만(프로덕션 환경에서는 추가 검증 권장)
- 📸 **UI/UX 촬영**: ✅ SFN Graph 완료(Phase 8 Theme D, commit 3c90042)

### 기존 스크린샷(Phase 1-6에서 해당 분)

![UC4 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![UC4 Step Functions Graph(확대 표시 — 각 단계 상세)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- (재검증 시 정의)

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인(공통 VPC/S3 AP 유무)
   - `UC=media-vfx bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC4`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `renders/` 프리픽스에 샘플 파일 업로드
   - Step Functions `fsxn-media-vfx-demo-workflow` 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단 사용자 이름은 마스킹):
   - S3 출력 버킷 `fsxn-media-vfx-demo-output-<account>`의 전체 뷰
   - AI/ML 출력 JSON 미리보기(`build/preview_*.html` 형식 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py media-vfx-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요 시)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC4`로 삭제
   - VPC Lambda ENI 해제에 15-30분 소요(AWS 사양)
