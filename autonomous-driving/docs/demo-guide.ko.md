# 자율주행 데이터 전처리 파이프라인 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 자율주행 센서 데이터의 전처리 및 어노테이션 파이프라인을 시연합니다. 대용량 주행 데이터를 자동으로 분류하고 학습용 데이터셋을 생성합니다.

**핵심 메시지**: 대용량 주행 센서 데이터를 자동 전처리하여 AI 학습에 즉시 활용 가능한 어노테이션 데이터셋을 생성합니다.

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
센서 데이터 수집 → 포맷 변환 → 프레임 분류 → 어노테이션 생성 → 데이터셋 리포트
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 대용량 주행 데이터의 수동 전처리는 병목 구간

### Section 2 (0:45–1:30)
> 데이터 업로드: 센서 로그 파일 배치로 파이프라인 시작

### Section 3 (1:30–2:30)
> 전처리 및 분류: 자동 포맷 변환과 AI 기반 프레임 분류

### Section 4 (2:30–3:45)
> 어노테이션 결과: 생성된 라벨 데이터와 품질 통계 확인

### Section 5 (3:45–5:00)
> 데이터셋 리포트: 학습 준비 완료 보고서 및 품질 메트릭

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (Python 3.13) | 센서 데이터 품질 검증, 씬 분류, 카탈로그 생성 |
| Lambda SnapStart | 콜드 스타트 감소 (`EnableSnapStart=true` 옵트인) |
| SageMaker (4-way routing) | 추론 (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | 진정한 scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | 씬 분류 / 어노테이션 제안 |
| Amazon Athena | 메타데이터 검색 및 집계 |
| CloudFormation Guard Hooks | 배포 시 보안 정책 적용 |

### 로컬 테스트 (Phase 6A)

```bash
# SAM CLI로 로컬 테스트
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

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

- S3 출력 버킷 (keyframes/, annotations/, qc/)
- Rekognition 키프레임 객체 감지 결과
- LiDAR 포인트 클라우드 품질 검사 요약
- COCO 호환 어노테이션 JSON

### 촬영 가이드

1. **사전 준비**: `bash scripts/verify_phase7_prerequisites.sh`로 전제 조건 확인
2. **샘플 데이터**: S3 AP Alias를 통해 샘플 파일 업로드 후 Step Functions 워크플로우 시작
3. **촬영** (CloudShell/터미널 닫기, 브라우저 우측 상단 사용자 이름 마스킹)
4. **마스크**: `python3 scripts/mask_uc_demos.py <uc-dir>`로 자동 OCR 마스킹
5. **정리**: `bash scripts/cleanup_generic_ucs.sh <UC>`로 스택 삭제
