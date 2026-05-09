# BIM 모델 변경 감지 및 안전 준수 검사 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 BIM 모델의 변경 감지 및 안전 규정 준수 자동 검사 파이프라인을 시연합니다. 설계 변경 시 안전 기준 위반을 자동으로 검출합니다.

**핵심 메시지**: BIM 모델 변경 시 안전 규정 위반을 자동 검출하여 설계 단계에서 리스크를 사전에 제거합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
BIM 파일 업로드 → 변경 감지 → 안전 규정 매칭 → 위반 검출 → 준수 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 설계 변경마다 수동 안전 검토는 비효율적

### Section 2 (0:45–1:30)
> BIM 업로드: 변경된 모델 파일 배치로 검사 시작

### Section 3 (1:30–2:30)
> 변경 감지 및 규정 매칭: 자동 diff 분석과 안전 기준 대조

### Section 4 (2:30–3:45)
> 위반 사항 확인: 검출된 안전 규정 위반 목록과 심각도

### Section 5 (3:45–5:00)
> 준수 리포트: 시정 조치 권고 포함 종합 보고서 생성

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Change Detector) | BIM 모델 변경 감지 |
| Lambda (Rule Matcher) | 안전 규정 매칭 엔진 |
| Lambda (Report Generator) | 준수 리포트 생성 |
| Amazon Athena | 위반 이력 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
