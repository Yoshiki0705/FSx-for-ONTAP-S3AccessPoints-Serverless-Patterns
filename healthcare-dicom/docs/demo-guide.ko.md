# DICOM 익명화 워크플로우 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 의료 영상(DICOM) 파일의 자동 익명화 파이프라인을 시연합니다. 환자 식별 정보를 제거하여 연구 데이터 공유를 안전하게 수행합니다.

**핵심 메시지**: DICOM 파일에서 환자 정보를 자동 제거하여 규정을 준수하면서 연구 데이터를 안전하게 공유합니다.

**예상 시간**: 3–5 min

---

## 출력 대상: FSxN S3 Access Point (Pattern A)

이 UC는 **Pattern A: Native S3AP Output**에 해당합니다
(`docs/output-destination-patterns.md` 참조).

**설계**: 모든 AI/ML 아티팩트는 FSxN S3 Access Point를 통해 소스 데이터와 **동일한
FSx ONTAP 볼륨**에 다시 씁니다. 별도의 표준 S3 버킷은 생성되지 않습니다
("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력용 S3 AP Alias (입력과 동일 가능)

AWS 사양 제약과 해결 방법은
[README.ko.md — AWS 사양상의 제약](../../README.ko.md#aws-사양상의-제약-및-해결-방법) 참조.

---
## Workflow

```
DICOM 업로드 → 메타데이터 추출 → PHI 검출 → 익명화 처리 → 검증 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 연구 데이터 공유 시 환자 개인정보 보호 규정 준수가 필수

### Section 2 (0:45–1:30)
> 파일 업로드: DICOM 파일 배치로 자동 처리 시작

### Section 3 (1:30–2:30)
> PHI 검출 및 익명화: AI 기반 개인정보 검출 및 자동 마스킹 처리

### Section 4 (2:30–3:45)
> 결과 확인: 익명화 완료 파일과 처리 통계 확인

### Section 5 (3:45–5:00)
> 검증 리포트: 규정 준수 검증 보고서 생성 및 데이터 공유 승인

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (DICOM Parser) | DICOM 메타데이터 추출 |
| Lambda (PHI Detector) | AI 기반 개인정보 검출 |
| Lambda (Anonymizer) | 익명화 처리 실행 |
| Amazon Athena | 처리 결과 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17 및 UC6/11/14 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서
실제로 보는 UI/UX 화면**을 대상으로 합니다.
기술자용 뷰(Step Functions 그래프, CloudFormation 스택 이벤트 등)는
`docs/verification-results-*.md`에 통합되어 있습니다.

### 이 유스케이스의 검증 상태

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **UI/UX 촬영**: ✅ SFN Graph 완료 (Phase 8 Theme D, commit c66084f)

### 기존 스크린샷 (Phase 1-6에서 해당분)

![UC5 Step Functions 그래프 뷰 (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![UC5 Step Functions 그래프 (확대 — 단계별 상세)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면 (권장 촬영 목록)

- S3 출력 버킷 (dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical 엔티티 감지 결과 (Cross-Region)
- 비식별화된 DICOM 메타데이터 JSON

### 촬영 가이드

1. **사전 준비**: `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인
2. **샘플 데이터**: S3 AP Alias를 통해 샘플 파일 업로드 후 Step Functions 워크플로우 시작
3. **촬영** (CloudShell/터미널 닫기, 브라우저 우측 상단 사용자 이름 마스킹)
4. **마스크**: `python3 scripts/mask_uc_demos.py <uc-dir>`로 자동 OCR 마스킹
5. **정리**: `bash scripts/cleanup_generic_ucs.sh <UC>`로 스택 삭제
