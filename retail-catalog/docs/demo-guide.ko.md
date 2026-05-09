# 상품 이미지 태깅 및 카탈로그 메타데이터 생성 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 상품 이미지의 자동 태깅 및 카탈로그 메타데이터 생성 파이프라인을 시연합니다. AI가 상품 사진을 분석하여 속성 태그와 설명을 자동 생성합니다.

**핵심 메시지**: 상품 이미지에서 AI가 속성을 자동 추출하여 카탈로그 메타데이터를 즉시 생성하고 상품 등록을 가속화합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
상품 이미지 업로드 → 시각 분석 → 속성 태깅 → 설명 생성 → 카탈로그 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 수천 개 상품의 수동 태깅과 설명 작성은 병목 구간

### Section 2 (0:45–1:30)
> 이미지 업로드: 상품 사진 배치로 처리 시작

### Section 3 (1:30–2:30)
> AI 분석 및 태깅: 시각 AI로 색상, 소재, 카테고리 등 자동 추출

### Section 4 (2:30–3:45)
> 메타데이터 생성: 상품 설명과 검색 키워드 자동 생성

### Section 5 (3:45–5:00)
> 카탈로그 리포트: 처리 완료 통계 및 품질 검증 결과

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Image Analyzer) | AI 기반 시각 분석 |
| Lambda (Tag Generator) | 속성 태그 생성 |
| Lambda (Description Writer) | 상품 설명 자동 작성 |
| Amazon Athena | 카탈로그 통계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
