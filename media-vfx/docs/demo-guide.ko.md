# VFX 렌더링 품질 검사 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 VFX 렌더링 출력의 품질 검사 파이프라인을 시연합니다. 렌더링 프레임의 자동 검증으로 아티팩트와 오류 프레임을 조기 감지합니다.

**핵심 메시지**: 대량의 렌더링 프레임을 자동 검증하여 품질 문제를 즉시 감지하고 재렌더링 판단을 신속화합니다.

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
렌더링 출력(EXR/PNG) -> 프레임 분석/메타데이터 추출 -> 품질 판정/이상 감지 -> QC 보고서(샷별)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 문제 제기: 수천 프레임의 육안 확인은 비현실적

### Section 2 (0:45-1:30)
> 파이프라인 트리거: 렌더링 완료로 자동 QC 시작

### Section 3 (1:30-2:30)
> 프레임 분석: 픽셀 통계로 프레임 품질 정량 평가

### Section 4 (2:30-3:45)
> 품질 평가: 문제 프레임 자동 분류 및 특정

### Section 5 (3:45-5:00)
> QC 보고서: 재렌더링 판단을 즉시 지원

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Frame Analyzer) | 프레임 메타데이터/픽셀 통계 추출 |
| Lambda (Quality Checker) | 통계적 품질 판정 |
| Lambda (Report Generator) | Bedrock QC 보고서 생성 |
| Amazon Athena | 프레임 통계 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
