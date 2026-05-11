# 계약서·청구서 자동 처리 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 계약서·청구서의 자동 처리 파이프라인을 시연합니다. OCR 텍스트 추출과 엔티티 추출을 결합하여 비정형 문서에서 구조화 데이터를 자동 생성합니다.

**핵심 메시지**: 종이 기반 계약서·청구서를 자동 디지털화하여 금액·날짜·거래처 등 핵심 정보를 즉시 추출·구조화합니다.

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



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 월 200건 이상의 청구서를 수동 처리하는 것은 한계

### Section 2 (0:45–1:30)
> 문서 업로드: 파일 배치만으로 자동 처리 시작

### Section 3 (1:30–2:30)
> OCR 및 추출: OCR + AI로 문서 분류 및 필드 추출

### Section 4 (2:30–3:45)
> 구조화 출력: 구조화 데이터로 즉시 활용 가능

### Section 5 (3:45–5:00)
> 검증 및 보고서: 신뢰도 평가로 수동 확인 필요 항목 명시

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (OCR Processor) | Textract 문서 텍스트 추출 |
| Lambda (Entity Extractor) | Bedrock 엔티티 추출 |
| Lambda (Classifier) | 문서 유형 분류 |
| Amazon Athena | 추출 데이터 집계 분석 |

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
- 📸 **UI/UX**: Not yet captured

### 기존 스크린샷 (Phase 1-6에서 해당분)

*(해당 없음. 재검증 시 새로 촬영해 주세요.)*

### 재검증 시 UI/UX 대상 화면 (권장 촬영 목록)

- S3 출력 버킷 (textract-results/, comprehend-entities/, reports/)
- Textract OCR 결과 JSON (계약서/청구서에서 추출된 필드)
- Comprehend 엔티티 감지 결과 (조직명, 날짜, 금액)
- Bedrock 생성 요약 보고서

### 촬영 가이드

1. **사전 준비**: `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인
2. **샘플 데이터**: S3 AP Alias를 통해 샘플 파일 업로드 후 Step Functions 워크플로우 시작
3. **촬영** (CloudShell/터미널 닫기, 브라우저 우측 상단 사용자 이름 마스킹)
4. **마스크**: `python3 scripts/mask_uc_demos.py <uc-dir>`로 자동 OCR 마스킹
5. **정리**: `bash scripts/cleanup_generic_ucs.sh <UC>`로 스택 삭제
