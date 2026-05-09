# 시퀀싱 QC 및 변이 집계 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 유전체 시퀀싱 데이터의 품질 관리(QC) 및 변이 집계 파이프라인을 시연합니다. 대량의 시퀀싱 결과를 자동으로 검증하고 변이 통계를 생성합니다.

**핵심 메시지**: 시퀀싱 데이터의 품질을 자동 검증하고 변이를 집계하여 연구자가 분석에 집중할 수 있게 합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
FASTQ 업로드 → QC 검증 → 변이 호출 → 통계 집계 → QC 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 대량 시퀀싱 데이터의 수동 QC는 시간 소모적

### Section 2 (0:45–1:30)
> 데이터 업로드: FASTQ 파일 배치로 파이프라인 시작

### Section 3 (1:30–2:30)
> QC 및 변이 분석: 자동 품질 검증과 변이 호출 실행

### Section 4 (2:30–3:45)
> 결과 확인: QC 메트릭과 변이 통계 확인

### Section 5 (3:45–5:00)
> QC 리포트: 종합 품질 보고서 및 후속 분석 권고

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (QC Validator) | 시퀀싱 품질 검증 |
| Lambda (Variant Caller) | 변이 호출 실행 |
| Lambda (Stats Aggregator) | 변이 통계 집계 |
| Amazon Athena | QC 메트릭 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
