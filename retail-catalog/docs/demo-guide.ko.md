# 상품 이미지 태깅 및 카탈로그 메타데이터 생성 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 상품 이미지의 자동 태깅 및 카탈로그 메타데이터 생성 파이프라인을 시연합니다. AI가 상품 사진을 분석하여 속성 태그와 설명을 자동 생성합니다.

**핵심 메시지**: 상품 이미지에서 AI가 속성을 자동 추출하여 카탈로그 메타데이터를 즉시 생성하고 상품 등록을 가속화합니다.

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
