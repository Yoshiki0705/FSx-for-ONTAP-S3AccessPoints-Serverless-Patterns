# 사고 사진 손해 사정·보험금 리포트 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 사고 사진으로부터 손해 사정 및 보험금 청구 보고서 자동 생성 파이프라인을 시연합니다. 이미지 분석을 통한 손해 평가와 AI 보고서 생성으로 사정 프로세스를 효율화합니다.

**데모의 핵심 메시지**: 사고 사진을 AI가 자동 분석하여 손해 정도 평가와 보험금 청구 보고서를 즉시 생성합니다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | 손해 사정 담당 / 클레임 조정자 |
| **일상 업무** | 사고 사진 확인, 손해 평가, 보험금 산정, 보고서 작성 |
| **과제** | 대량의 청구 건을 신속하게 처리해야 함 |
| **기대 성과** | 사정 프로세스의 신속화 및 일관성 확보 |

### Persona: 고바야시 씨(손해 사정 담당)

- 월 100+ 건의 보험금 청구 처리
- 사진으로부터 손해 정도를 판단하고 보고서 작성
- "초기 사정을 자동화하여 복잡한 건에 집중하고 싶다"

---

## Demo Scenario: 자동차 사고 손해 사정

### 워크플로우 전체 구조

```
사고 사진         이미지 분석        손해 평가          청구 보고서
(복수 장)    →   손상 검출    →   정도 판정    →    AI 생성
                 부위 특정        금액 추정
```

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 월 100건 이상의 보험금 청구. 각 건마다 복수의 사고 사진을 확인하고 손해 정도를 평가하여 보고서를 작성합니다. 수동으로는 처리가 따라가지 못합니다.

**Key Visual**: 보험금 청구 건 목록, 사고 사진 샘플

### Section 2: Photo Upload(0:45–1:30)

**내레이션 요지**:
> 사고 사진이 업로드되면 자동 사정 파이프라인이 시작됩니다. 건별로 처리합니다.

**Key Visual**: 사진 업로드 → 워크플로우 자동 시작

### Section 3: Damage Detection(1:30–2:30)

**내레이션 요지**:
> AI가 사진을 분석하여 손상 부위를 검출합니다. 손상 종류(찌그러짐, 긁힘, 파손)와 부위(범퍼, 도어, 펜더 등)를 특정합니다.

**Key Visual**: 손상 검출 결과, 부위 매핑

### Section 4: Assessment(2:30–3:45)

**내레이션 요지**:
> 손상 정도를 평가하고 수리/교체 판단 및 개략 금액을 산출합니다. 과거 유사 건과의 비교도 실시합니다.

**Key Visual**: 손해 평가 결과 테이블, 금액 추정

### Section 5: Claims Report(3:45–5:00)

**내레이션 요지**:
> AI가 보험금 청구 보고서를 자동 생성합니다. 손해 요약, 추정 금액, 권장 대응을 포함합니다. 사정 담당자는 확인·승인만 하면 됩니다.

**Key Visual**: AI 생성 청구 보고서(손해 요약 + 금액 추정)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 청구 건 목록 | Section 1 |
| 2 | 사진 업로드·파이프라인 시작 | Section 2 |
| 3 | 손상 검출 결과 | Section 3 |
| 4 | 손해 평가·금액 추정 | Section 4 |
| 5 | 보험금 청구 보고서 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "월 100건의 청구를 수동 사정하는 것은 한계" |
| Upload | 0:45–1:30 | "사진 업로드로 자동 사정 시작" |
| Detection | 1:30–2:30 | "AI가 손상 부위와 종류를 자동 검출" |
| Assessment | 2:30–3:45 | "손해 정도와 수리 금액을 자동 추정" |
| Report | 3:45–5:00 | "청구 보고서를 자동 생성, 확인·승인만" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 경미한 손상 사진(5건) | 기본 사정 데모 |
| 2 | 중간 정도 손상 사진(3건) | 평가 정확도 데모 |
| 3 | 중대한 손상 사진(2건) | 전손 판정 데모 |

---

## Timeline

### 1주일 이내 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 사진 데이터 준비 | 2시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 획득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 동영상으로부터 손상 검출
- 수리 공장 견적과의 자동 대조
- 부정 청구 탐지

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Image Analyzer) | Bedrock/Rekognition을 통한 손상 검출 |
| Lambda (Damage Assessor) | 손해 정도 평가·금액 추정 |
| Lambda (Report Generator) | Bedrock을 통한 청구 보고서 생성 |
| Amazon Athena | 과거 건 데이터 참조·비교 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| 이미지 분석 정확도 부족 | 사전 분석 완료 결과 사용 |
| Bedrock 지연 | 사전 생성 보고서 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상 제작 가이드입니다.*

---

## 검증 완료된 UI/UX 스크린샷(2026-05-10 AWS 검증)

Phase 7과 동일한 방침으로 **보험 사정 담당자가 일상 업무에서 실제로 사용하는 UI/UX 화면**을 촬영.
기술자용 화면(Step Functions 그래프 등)은 제외.

### 출력 대상 선택: 표준 S3 vs FSxN S3AP

UC14는 2026-05-10 업데이트에서 `OutputDestination` 파라미터를 지원합니다.
**동일 FSx 볼륨에 AI 산출물을 다시 쓰기**함으로써 청구 처리 담당자가
청구 케이스 디렉터리 구조 내에서 손해 평가 JSON·OCR 결과·청구 보고서를 열람할 수 있습니다
("no data movement" 패턴, PII 보호 관점에서도 유리).

```bash
# STANDARD_S3 모드(기본값, 기존과 동일)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP 모드(AI 산출물을 FSx ONTAP 볼륨에 다시 쓰기)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 사양상 제약 및 회피 방법은 [프로젝트 README의 "AWS 사양상 제약 및 회피 방법"
섹션](../../README.md#aws-仕様上の制約と回避策) 참조.

### 1. 보험금 청구 보고서 — 사정 담당자용 요약

사고 사진 Rekognition 분석 + 견적서 Textract OCR + 사정 권장 판정을 통합한 보고서.
판정 `MANUAL_REVIEW` + 신뢰도 75%로 자동화할 수 없는 항목을 담당자가 검토.

<!-- SCREENSHOT: uc14-claims-report.png
     내용: 보험금 청구 보고서(청구 ID, 손해 요약, 견적 상관, 권장 판정)
            + Rekognition 검출 레이블 목록 + Textract OCR 결과
     마스크: 계정 ID, 버킷 이름 -->
![UC14: 보험금 청구 보고서](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. S3 출력 버킷 — 사정 아티팩트 개요

사정 담당자가 청구 케이스별 아티팩트를 확인하는 화면.
`assessments/` (Rekognition 분석) + `estimates/` (Textract OCR) + `reports/` (통합 보고서).

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     내용: S3 콘솔에서 assessments/, estimates/, reports/ 프리픽스
     마스크: 계정 ID -->
![UC14: S3 출력 버킷](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### 실측값(2026-05-10 AWS 배포 검증)

- **Step Functions 실행**: SUCCEEDED
- **Rekognition**: 사고 사진에서 `Maroon` 90.79%, `Business Card` 84.51% 등 검출
- **Textract**: cross-region us-east-1 경유로 견적서 PDF에서 `Total: 1270.00 USD` 등 OCR
- **생성 아티팩트**: assessments/*.json, estimates/*.json, reports/*.txt
- **실제 스택**: `fsxn-insurance-claims-demo`(ap-northeast-1, 2026-05-10 검증 시)
