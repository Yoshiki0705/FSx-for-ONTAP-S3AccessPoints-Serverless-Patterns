# 사고 사진 손해 평가 및 청구 보고서 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 사고 사진 기반 손해 평가 및 자동 청구 보고서 생성 파이프라인을 시연합니다. AI가 사진에서 손상 정도를 분석하고 청구 보고서를 자동 작성합니다.

**핵심 메시지**: 사고 사진에서 AI가 손상을 자동 분석하여 청구 보고서를 즉시 생성하고 처리 시간을 단축합니다.

**예상 시간**: 3–5 min

---

## 출력 대상: OutputDestination으로 선택 가능 (Pattern B)

이 UC는 `OutputDestination` 파라미터를 지원합니다 (2026-05-10 업데이트,
`docs/output-destination-patterns.md` 참조).

**두 가지 모드**:

- **STANDARD_S3** (기본값): AI 아티팩트가 새 S3 버킷으로 이동
- **FSXN_S3AP** ("no data movement"): AI 아티팩트가 S3 Access Point를 통해
  동일한 FSx ONTAP 볼륨으로 돌아가며, SMB/NFS 사용자가 기존 디렉토리 구조 내에서
  볼 수 있음

```bash
# FSXN_S3AP 모드
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 사양 제약과 해결 방법은
[README.ko.md — AWS 사양상의 제약](../../README.ko.md#aws-사양상의-제약-및-해결-방법) 참조.

---
## Workflow

```
사고 사진 업로드 → 손상 영역 검출 → 심각도 평가 → 비용 추정 → 청구 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 사고 사진 기반 손해 평가의 수동 처리는 시간이 오래 걸림

### Section 2 (0:45–1:30)
> 사진 업로드: 사고 현장 사진 배치로 평가 시작

### Section 3 (1:30–2:30)
> AI 손상 분석: 손상 영역 자동 검출 및 심각도 분류

### Section 4 (2:30–3:45)
> 평가 결과: 손상 부위별 비용 추정과 종합 평가

### Section 5 (3:45–5:00)
> 청구 리포트: 자동 생성된 청구 보고서와 처리 권고

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Damage Detector) | AI 기반 손상 영역 검출 |
| Lambda (Severity Assessor) | 손상 심각도 평가 |
| Lambda (Cost Estimator) | 수리 비용 추정 |
| Amazon Athena | 청구 이력 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
