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

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17 및 UC6/11/14 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서
실제로 보는 UI/UX 화면**을 대상으로 합니다.
기술자용 뷰(Step Functions 그래프, CloudFormation 스택 이벤트 등)는
`docs/verification-results-*.md`에 통합되어 있습니다.

### 이 유스케이스의 검증 상태

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **UI/UX**: Not yet captured

### 기존 스크린샷 (Phase 1-6에서 해당분)

*(해당 없음. 재검증 시 새로 촬영해 주세요.)*

### 재검증 시 UI/UX 대상 화면 (권장 촬영 목록)

- S3 출력 버킷 (segy-metadata/, anomalies/, reports/)
- Athena 쿼리 결과 (SEG-Y 메타데이터 통계)
- Rekognition 검층 로그 이미지 라벨
- 이상 감지 보고서

### 촬영 가이드

1. **사전 준비**: `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인
2. **샘플 데이터**: S3 AP Alias를 통해 샘플 파일 업로드 후 Step Functions 워크플로우 시작
3. **촬영** (CloudShell/터미널 닫기, 브라우저 우측 상단 사용자 이름 마스킹)
4. **마스크**: `python3 scripts/mask_uc_demos.py <uc-dir>`로 자동 OCR 마스킹
5. **정리**: `bash scripts/cleanup_generic_ucs.sh <UC>`로 스택 삭제
