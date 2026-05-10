# 배송 전표 OCR 및 재고 분석 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 배송 전표의 OCR 처리 및 재고 분석 파이프라인을 시연합니다. 종이 전표를 자동 디지털화하여 재고 현황을 실시간으로 파악합니다.

**핵심 메시지**: 배송 전표를 자동 OCR 처리하여 재고 데이터를 실시간으로 업데이트하고 물류 효율을 향상시킵니다.

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
전표 스캔 업로드 → OCR 텍스트 추출 → 필드 파싱 → 재고 업데이트 → 분석 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 종이 전표의 수동 입력은 오류가 많고 시간 소모적

### Section 2 (0:45–1:30)
> 전표 업로드: 스캔된 전표 이미지 배치로 처리 시작

### Section 3 (1:30–2:30)
> OCR 및 파싱: 텍스트 추출과 구조화 데이터 변환

### Section 4 (2:30–3:45)
> 재고 업데이트: 추출 데이터 기반 실시간 재고 반영

### Section 5 (3:45–5:00)
> 분석 리포트: 물류 현황 대시보드 및 이상 감지 알림

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (OCR Engine) | 전표 텍스트 추출 |
| Lambda (Field Parser) | 구조화 데이터 파싱 |
| Lambda (Inventory Updater) | 재고 데이터 업데이트 |
| Amazon Athena | 물류 통계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
