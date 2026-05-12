# 상품 이미지 태그 지정 및 카탈로그 메타데이터 생성 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 상품 이미지의 자동 태그 부여 및 카탈로그 메타데이터 생성 파이프라인을 실연합니다. AI 기반 이미지 분석으로 상품 속성을 자동 추출하여 검색 가능한 카탈로그를 구축합니다.

**데모의 핵심 메시지**: 상품 이미지에서 속성(색상, 소재, 카테고리 등)을 AI가 자동 추출하여 카탈로그 메타데이터를 즉시 생성합니다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | EC 사이트 운영자 / 카탈로그 관리자 / MD 담당 |
| **일상 업무** | 상품 등록, 이미지 관리, 카탈로그 업데이트 |
| **과제** | 신상품의 속성 입력과 태그 부여에 시간이 소요됨 |
| **기대 성과** | 상품 등록 자동화 및 검색성 향상 |

### Persona: 요시다 씨(EC 카탈로그 관리자)

- 주당 200개 이상의 신상품 등록
- 각 상품에 10개 이상의 속성 태그를 수동 입력
- "상품 이미지를 업로드하는 것만으로 태그를 자동 생성하고 싶다"

---

## Demo Scenario: 신상품 배치 등록

### 워크플로우 전체 구조

```
상품 이미지          이미지 분석        속성 추출          카탈로그 업데이트
(JPEG/PNG)   →   AI 분석    →   태그 생성    →    메타데이터
                  객체 검출        카테고리 분류      등록
```

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 주당 200개 이상의 신상품. 각 상품에 색상, 소재, 카테고리, 스타일 등의 태그를 수동 입력하는 것은 방대한 작업. 입력 오류나 불일치도 발생.

**Key Visual**: 상품 이미지 폴더, 수동 태그 입력 화면

### Section 2: Image Upload(0:45–1:30)

**내레이션 요지**:
> 상품 이미지를 폴더에 배치하는 것만으로 자동 태그 부여 파이프라인이 시작됩니다.

**Key Visual**: 이미지 업로드 → 워크플로우 자동 시작

### Section 3: AI Analysis(1:30–2:30)

**내레이션 요지**:
> AI가 각 이미지를 분석하여 상품 카테고리, 색상, 소재, 패턴, 스타일을 자동 판정. 여러 속성을 동시에 추출.

**Key Visual**: 이미지 분석 처리 중, 속성 추출 결과

### Section 4: Tag Generation(2:30–3:45)

**내레이션 요지**:
> 추출된 속성을 표준화된 태그로 변환. 기존 태그 체계와의 일관성을 확보.

**Key Visual**: 생성 태그 목록, 카테고리별 분포

### Section 5: Catalog Update(3:45–5:00)

**내레이션 요지**:
> 메타데이터를 카탈로그에 자동 등록. 검색성 향상과 상품 추천 정확도 개선에 기여. 처리 요약 보고서를 생성.

**Key Visual**: 카탈로그 업데이트 결과, AI 요약 보고서

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 상품 이미지 폴더 | Section 1 |
| 2 | 파이프라인 시작 화면 | Section 2 |
| 3 | AI 이미지 분석 결과 | Section 3 |
| 4 | 태그 생성 결과 목록 | Section 4 |
| 5 | 카탈로그 업데이트 요약 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "주당 200개의 수동 태그 부여는 방대한 작업" |
| Upload | 0:45–1:30 | "이미지 배치만으로 자동 태그 부여 시작" |
| Analysis | 1:30–2:30 | "AI가 색상·소재·카테고리를 자동 판정" |
| Tags | 2:30–3:45 | "표준화 태그를 자동 생성" |
| Catalog | 3:45–5:00 | "카탈로그에 자동 등록, 검색성 향상" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 의류 상품 이미지(10장) | 메인 처리 대상 |
| 2 | 가구 상품 이미지(5장) | 카테고리 분류 데모 |
| 3 | 액세서리 이미지(5장) | 다속성 추출 데모 |
| 4 | 기존 태그 체계 마스터 | 표준화 데모 |

---

## Timeline

### 1주일 이내 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 상품 이미지 준비 | 2시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 획득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 유사 상품 검색
- 자동 상품 설명문 생성
- 트렌드 분석 연계

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Image Analyzer) | Bedrock/Rekognition을 통한 이미지 분석 |
| Lambda (Tag Generator) | 속성 태그 생성·표준화 |
| Lambda (Catalog Updater) | 카탈로그 메타데이터 등록 |
| Lambda (Report Generator) | 처리 요약 보고서 생성 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| 이미지 분석 정확도 부족 | 사전 분석 완료 결과 사용 |
| Bedrock 지연 | 사전 생성 태그 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상 제작 가이드입니다.*

---

## 검증 완료된 UI/UX 스크린샷(2026-05-10 AWS 검증)

Phase 7과 동일한 방침으로 **EC 담당자가 일상 업무에서 실제로 사용하는 UI/UX 화면**을 촬영.
기술자용 화면(Step Functions 그래프 등)은 제외.

### 출력 대상 선택: 표준 S3 vs FSxN S3AP

UC11은 2026-05-10 업데이트에서 `OutputDestination` 파라미터를 지원합니다.
**동일 FSx 볼륨에 AI 산출물을 다시 쓰기**함으로써 SMB/NFS 사용자가
상품 이미지의 디렉터리 구조 내에서 자동 생성 태그 JSON을 열람할 수 있습니다
("no data movement" 패턴).

```bash
# STANDARD_S3 모드(기본값, 기존과 동일)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP 모드(AI 산출물을 FSx ONTAP 볼륨에 다시 쓰기)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 사양상의 제약 및 회피 방법은 [프로젝트 README의 "AWS 사양상의 제약 및 회피 방법"
섹션](../../README.md#aws-仕様上の制約と回避策) 참조.

### 1. 상품 이미지의 자동 태그 부여 결과

EC 관리자가 신상품 등록 시 받는 AI 분석 결과. Rekognition이 실제 이미지에서 7개 레이블을
검출(`Oval` 99.93%, `Food`, `Furniture`, `Table`, `Sweets`, `Cocoa`, `Dessert`).

<!-- SCREENSHOT: uc11-product-tags.png
     내용: 상품 이미지 + AI 검출 태그 목록(신뢰도 포함)
     마스크: 계정 ID, 버킷 이름 -->
![UC11: 상품 태그](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. S3 출력 버킷 — 태그·품질 검사 결과 개요

EC 운영 담당자가 배치 처리 결과를 확인하는 화면.
`tags/`와 `quality/` 2개 프리픽스로 상품별 JSON이 생성됩니다.

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     내용: S3 콘솔에서 tags/, quality/ 프리픽스
     마스크: 계정 ID -->
![UC11: S3 출력 버킷](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### 실측값(2026-05-10 AWS 배포 검증)

- **Step Functions 실행**: SUCCEEDED, 4개 상품 이미지를 병렬 처리
- **Rekognition**: 실제 이미지에서 7개 레이블 검출(최고 신뢰도 99.93%)
- **생성 JSON**: tags/*.json (~750 bytes), quality/*.json (~420 bytes)
- **실제 스택**: `fsxn-retail-catalog-demo`(ap-northeast-1, 2026-05-10 검증 시)
