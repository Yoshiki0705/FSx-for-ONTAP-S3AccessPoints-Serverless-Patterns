# 검층 이상 감지 및 규정 준수 보고 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 검층(Well Log) 데이터의 이상 감지 및 규정 준수 보고 파이프라인을 시연합니다. 센서 데이터에서 이상 패턴을 자동 검출하고 규정 보고서를 생성합니다.

**핵심 메시지**: 검층 데이터에서 이상 패턴을 자동 감지하여 규정 준수 보고서를 즉시 생성합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
검층 데이터 수집 → 신호 전처리 → 이상 감지 → 규정 매칭 → 준수 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 대량의 검층 데이터에서 이상을 수동으로 찾는 것은 비효율적

### Section 2 (0:45–1:30)
> 데이터 업로드: 검층 로그 파일 배치로 분석 시작

### Section 3 (1:30–2:30)
> 이상 감지: AI 기반 패턴 분석으로 이상 구간 자동 검출

### Section 4 (2:30–3:45)
> 결과 확인: 검출된 이상 목록과 심각도 분류

### Section 5 (3:45–5:00)
> 규정 준수 리포트: 규정 기준 대조 결과 및 시정 조치 권고

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Signal Processor) | 검층 신호 전처리 |
| Lambda (Anomaly Detector) | AI 기반 이상 감지 |
| Lambda (Compliance Checker) | 규정 기준 대조 |
| Amazon Athena | 이상 이력 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
