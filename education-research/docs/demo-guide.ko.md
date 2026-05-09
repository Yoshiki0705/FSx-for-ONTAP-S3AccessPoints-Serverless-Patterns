# 논문 분류 및 인용 네트워크 분석 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 학술 논문의 자동 분류 및 인용 네트워크 분석 파이프라인을 시연합니다. 대량의 논문을 주제별로 분류하고 인용 관계를 시각화합니다.

**핵심 메시지**: 대량의 학술 논문을 AI로 자동 분류하고 인용 네트워크를 분석하여 연구 동향을 즉시 파악합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
논문 업로드 → 메타데이터 추출 → AI 주제 분류 → 인용 네트워크 구축 → 분석 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 수천 편의 논문을 수동으로 분류하고 관계를 파악하는 것은 비현실적

### Section 2 (0:45–1:30)
> 논문 업로드: PDF 파일 배치로 분석 파이프라인 시작

### Section 3 (1:30–2:30)
> AI 분류 및 네트워크 구축: 주제 자동 분류와 인용 관계 추출

### Section 4 (2:30–3:45)
> 분석 결과: 주제별 클러스터와 핵심 논문 식별

### Section 5 (3:45–5:00)
> 연구 동향 리포트: 분야별 트렌드 분석 및 추천 논문 목록

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (PDF Parser) | 논문 메타데이터 추출 |
| Lambda (Topic Classifier) | AI 기반 주제 분류 |
| Lambda (Citation Analyzer) | 인용 네트워크 구축 |
| Amazon Athena | 연구 동향 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
