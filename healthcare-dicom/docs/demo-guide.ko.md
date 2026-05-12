# DICOM 익명화 워크플로우 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 의료 영상(DICOM)의 익명화 워크플로를 실연한다. 연구 데이터 공유를 위해 환자 개인정보를 자동 제거하고, 익명화 품질을 검증하는 프로세스를 보여준다.

**데모의 핵심 메시지**: DICOM 파일에서 환자 식별 정보를 자동 제거하고, 연구 활용 가능한 익명화 데이터셋을 안전하게 생성한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | 의료정보관리자 / 임상연구 데이터 매니저 |
| **일상 업무** | 의료 영상 관리, 연구 데이터 제공, 프라이버시 보호 |
| **과제** | 대량의 DICOM 파일의 수동 익명화는 시간이 걸리고 실수의 위험이 있다 |
| **기대하는 성과** | 안전하고 확실한 익명화와 감사 추적의 자동화 |

### Persona: 다카하시 씨(임상연구 데이터 매니저)

- 다기관 공동연구에서 10,000+ DICOM 파일의 익명화가 필요
- 환자명, ID, 생년월일 등의 확실한 제거가 요구됨
- "익명화 누락 제로를 보장하면서, 영상 품질은 유지하고 싶다"

---

## Demo Scenario: 연구 데이터 공유를 위한 DICOM 익명화

### 워크플로 전체 구조

```
DICOM 파일     태그 분석        익명화 처리        품질 검증
(환자정보 포함) →  메타데이터   →   개인정보 제거  →   익명화 확인
                  추출            해시화        레포트 생성
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 다기관 공동연구를 위해 10,000건의 DICOM 파일을 익명화해야 한다. 수동 처리는 실수의 위험이 있으며, 개인정보 유출은 허용되지 않는다.

**Key Visual**: DICOM 파일 목록, 환자정보 태그 하이라이트

### Section 2: Workflow Trigger(0:45–1:30)

**내레이션 요지**:
> 익명화 대상 데이터셋을 지정하고, 익명화 워크플로를 시작. 익명화 규칙(제거·해시화·일반화)을 설정.

**Key Visual**: 워크플로 시작, 익명화 규칙 설정 화면

### Section 3: De-identification(1:30–2:30)

**내레이션 요지**:
> 각 DICOM 파일의 개인정보 태그를 자동 처리. 환자명→해시, 생년월일→연령 범위, 기관명→익명 코드. 영상 픽셀 데이터는 보존.

**Key Visual**: 익명화 처리 진행, 태그 변환의 before/after

### Section 4: Quality Verification(2:30–3:45)

**내레이션 요지**:
> 익명화 후 파일을 자동 검증. 잔존하는 개인정보가 없는지 전체 태그를 스캔. 영상의 무결성도 확인.

**Key Visual**: 검증 결과 — 익명화 성공률, 잔존 위험 태그 목록

### Section 5: Audit Report(3:45–5:00)

**내레이션 요지**:
> 익명화 처리의 감사 레포트를 자동 생성. 처리 건수, 제거 태그 수, 검증 결과를 기록. 연구윤리위원회 제출 자료로 활용 가능.

**Key Visual**: 감사 레포트(처리 요약 + 컴플라이언스 추적)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | DICOM 파일 목록(익명화 전) | Section 1 |
| 2 | 워크플로 시작·규칙 설정 | Section 2 |
| 3 | 익명화 처리 진행 | Section 3 |
| 4 | 품질 검증 결과 | Section 4 |
| 5 | 감사 레포트 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "대량 DICOM의 익명화 누락은 허용되지 않는다" |
| Trigger | 0:45–1:30 | "익명화 규칙을 설정하고 워크플로 시작" |
| Processing | 1:30–2:30 | "개인정보 태그를 자동 제거, 영상 품질은 유지" |
| Verification | 2:30–3:45 | "전체 태그 스캔으로 익명화 누락 제로 확인" |
| Report | 3:45–5:00 | "감사 추적을 자동 생성, 윤리위원회에 제출 가능" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 테스트 DICOM 파일(20건) | 메인 처리 대상 |
| 2 | 복잡한 태그 구조의 DICOM(5건) | 엣지 케이스 |
| 3 | 프라이빗 태그 포함 DICOM(3건) | 고위험 검증 |

---

## Timeline

### 1주일 이내 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 테스트 DICOM 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 영상 내 텍스트(번인)의 자동 검출·제거
- FHIR 연계를 통한 익명화 매핑 관리
- 차분 익명화(추가 데이터의 증분 처리)

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로 오케스트레이션 |
| Lambda (Tag Parser) | DICOM 태그 분석·개인정보 검출 |
| Lambda (De-identifier) | 태그 익명화 처리 |
| Lambda (Verifier) | 익명화 품질 검증 |
| Lambda (Report Generator) | 감사 레포트 생성 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| DICOM 파싱 실패 | 사전 처리된 데이터 사용 |
| 검증 오류 | 수동 확인 플로로 전환 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대하여: FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom은 **Pattern A: Native S3AP Output**으로 분류됩니다
(`docs/output-destination-patterns.md` 참조).

**설계**: DICOM 메타데이터, 익명화 결과, PII 검출 로그는 모두 FSxN S3 Access Point 경유로
원본 DICOM 의료 영상과 **동일한 FSx ONTAP 볼륨**에 기록됩니다. 표준 S3 버킷은
생성되지 않습니다("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력 데이터 읽기용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력 쓰기용 S3 AP Alias(입력과 동일해도 가능)

**배포 예시**:
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (기타 필수 파라미터)
```

**SMB/NFS 사용자 관점**:
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # 원본 DICOM
  └── metadata/patient_001/             # AI 익명화 결과(동일 볼륨 내)
      └── study_A_anonymized.json
```

AWS 사양상의 제약에 대해서는
[프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조하십시오.

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 합니다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약됩니다.

### 이 유스케이스의 검증 상태

- ⚠️ **E2E 검증**: 일부 기능만(프로덕션 환경에서는 추가 검증 권장)
- 📸 **UI/UX 촬영**: ✅ SFN Graph 완료(Phase 8 Theme D, commit c66084f)

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC5 Step Functions Graph view(SUCCEEDED)

![UC5 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색상으로 시각화하는 최종 사용자 최중요 화면입니다.

### 기존 스크린샷(Phase 1-6에서 해당분)

![UC5 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![UC5 Step Functions Graph(줌 표시 — 각 단계 상세)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical 엔티티 검출 결과(Cross-Region)
- DICOM 익명화된 메타데이터 JSON

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=healthcare-dicom bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC5`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `dicom/` 프리픽스에 샘플 파일 업로드
   - Step Functions `fsxn-healthcare-dicom-demo-workflow` 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단 사용자명은 마스킹):
   - S3 출력 버킷 `fsxn-healthcare-dicom-demo-output-<account>`의 전체 뷰
   - AI/ML 출력 JSON 미리보기(`build/preview_*.html` 형식 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py healthcare-dicom-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요시)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC5`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
