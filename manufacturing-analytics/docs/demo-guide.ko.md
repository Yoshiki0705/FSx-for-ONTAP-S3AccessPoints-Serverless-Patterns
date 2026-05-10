# IoT 센서 이상 감지 및 품질 검사 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 제조 라인의 IoT 센서 데이터에서 이상을 자동 감지하고 품질 검사 보고서를 생성하는 워크플로우를 시연합니다.

**핵심 메시지**: 센서 데이터의 이상 패턴을 자동 감지하여 품질 문제의 조기 발견과 예방 보전을 실현합니다.

**예상 시간**: 3-5 min

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
센서 데이터(CSV/Parquet) -> 전처리/정규화 -> 이상 감지/통계 분석 -> 품질 보고서(AI)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 문제 제기: 임계값 알림으로는 진정한 이상을 놓침

### Section 2 (0:45-1:30)
> 데이터 수집: 데이터 축적으로 자동 분석 시작

### Section 3 (1:30-2:30)
> 이상 감지: 통계적 방법으로 유의미한 이상만 감지

### Section 4 (2:30-3:45)
> 품질 검사: 라인/공정 수준에서 문제 영역 특정

### Section 5 (3:45-5:00)
> 보고서 및 조치: AI가 근본 원인 후보와 대응책 제시

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Data Preprocessor) | 센서 데이터 정규화 |
| Lambda (Anomaly Detector) | 통계적 이상 감지 |
| Lambda (Report Generator) | Bedrock 품질 보고서 생성 |
| Amazon Athena | 이상 데이터 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
