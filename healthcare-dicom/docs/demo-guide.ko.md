# DICOM 익명화 워크플로우 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 의료 영상(DICOM) 파일의 자동 익명화 파이프라인을 시연합니다. 환자 식별 정보를 제거하여 연구 데이터 공유를 안전하게 수행합니다.

**핵심 메시지**: DICOM 파일에서 환자 정보를 자동 제거하여 규정을 준수하면서 연구 데이터를 안전하게 공유합니다.

**예상 시간**: 3–5 min

---

## Workflow

```
DICOM 업로드 → 메타데이터 추출 → PHI 검출 → 익명화 처리 → 검증 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 연구 데이터 공유 시 환자 개인정보 보호 규정 준수가 필수

### Section 2 (0:45–1:30)
> 파일 업로드: DICOM 파일 배치로 자동 처리 시작

### Section 3 (1:30–2:30)
> PHI 검출 및 익명화: AI 기반 개인정보 검출 및 자동 마스킹 처리

### Section 4 (2:30–3:45)
> 결과 확인: 익명화 완료 파일과 처리 통계 확인

### Section 5 (3:45–5:00)
> 검증 리포트: 규정 준수 검증 보고서 생성 및 데이터 공유 승인

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (DICOM Parser) | DICOM 메타데이터 추출 |
| Lambda (PHI Detector) | AI 기반 개인정보 검출 |
| Lambda (Anonymizer) | 익명화 처리 실행 |
| Amazon Athena | 처리 결과 집계 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
