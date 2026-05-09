# 자율주행 데이터 전처리 파이프라인 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 자율주행 센서 데이터의 전처리 및 어노테이션 파이프라인을 시연합니다. 대용량 주행 데이터를 자동으로 분류하고 학습용 데이터셋을 생성합니다.

**핵심 메시지**: 대용량 주행 센서 데이터를 자동 전처리하여 AI 학습에 즉시 활용 가능한 어노테이션 데이터셋을 생성합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
센서 데이터 수집 → 포맷 변환 → 프레임 분류 → 어노테이션 생성 → 데이터셋 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 대용량 주행 데이터의 수동 전처리는 병목 구간

### Section 2 (0:45–1:30)
> 데이터 업로드: 센서 로그 파일 배치로 파이프라인 시작

### Section 3 (1:30–2:30)
> 전처리 및 분류: 자동 포맷 변환과 AI 기반 프레임 분류

### Section 4 (2:30–3:45)
> 어노테이션 결과: 생성된 라벨 데이터와 품질 통계 확인

### Section 5 (3:45–5:00)
> 데이터셋 리포트: 학습 준비 완료 보고서 및 품질 메트릭

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Format Converter) | 센서 데이터 포맷 변환 |
| Lambda (Frame Classifier) | AI 기반 프레임 분류 |
| Lambda (Annotation Generator) | 어노테이션 자동 생성 |
| Amazon Athena | 데이터셋 통계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
