# 로그 데이터 이상 탐지 및 컴플라이언스 보고서 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 시추공 검층 데이터의 이상 탐지 및 컴플라이언스 보고서 생성 파이프라인을 시연한다. 검층 데이터의 품질 문제를 자동 탐지하고 규제 보고서를 효율적으로 작성한다.

**데모의 핵심 메시지**: 검층 데이터의 이상을 자동 탐지하고 규제 요건에 준수하는 컴플라이언스 보고서를 즉시 생성한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | 지질 엔지니어 / 데이터 분석가 / 컴플라이언스 담당자 |
| **일상 업무** | 검층 데이터 분석, 시추공 평가, 규제 보고서 작성 |
| **과제** | 대량의 검층 데이터에서 이상을 수동으로 탐지하는 것은 시간이 많이 소요됨 |
| **기대 성과** | 데이터 품질의 자동 검증 및 규제 보고서의 효율화 |

### Persona: 마츠모토 씨(지질 엔지니어)

- 50개 이상 시추공의 검층 데이터를 관리
- 규제 당국에 정기 보고가 필요
- "데이터 이상을 자동 탐지하고 보고서 작성을 효율화하고 싶다"

---

## Demo Scenario: 검층 데이터 배치 분석

### 워크플로우 전체 구조

```
검층 데이터        데이터 검증       이상 탐지          컴플라이언스
(LAS/DLIS)   →   품질 체크    →  통계 분석    →    보고서 생성
                  포맷           이상값 탐지
```

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 50개 시추공의 검층 데이터를 정기적으로 품질 검증하고 규제 당국에 보고해야 한다. 수동 분석은 누락 위험이 높다.

**Key Visual**: 검층 데이터 파일 목록(LAS/DLIS 형식)

### Section 2: Data Ingestion(0:45–1:30)

**내레이션 요지**:
> 검층 데이터 파일을 업로드하고 품질 검증 파이프라인을 시작. 포맷 검증부터 시작.

**Key Visual**: 워크플로우 시작, 데이터 포맷 검증

### Section 3: Anomaly Detection(1:30–2:30)

**내레이션 요지**:
> 각 검층 커브(GR, SP, Resistivity 등)에 대해 통계적 이상 탐지를 실행. 심도 구간별 이상값을 탐지.

**Key Visual**: 이상 탐지 처리 중, 검층 커브의 이상 하이라이트

### Section 4: Results Review(2:30–3:45)

**내레이션 요지**:
> 탐지된 이상을 시추공별·커브별로 확인. 이상 유형(스파이크, 결측, 범위 이탈)을 분류.

**Key Visual**: 이상 탐지 결과 테이블, 시추공별 요약

### Section 5: Compliance Report(3:45–5:00)

**내레이션 요지**:
> AI가 규제 요건에 준수하는 컴플라이언스 보고서를 자동 생성. 데이터 품질 요약, 이상 대응 기록, 권장 조치를 포함.

**Key Visual**: 컴플라이언스 보고서(규제 포맷 준수)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 검층 데이터 파일 목록 | Section 1 |
| 2 | 파이프라인 시작·포맷 검증 | Section 2 |
| 3 | 이상 탐지 처리 결과 | Section 3 |
| 4 | 시추공별 이상 요약 | Section 4 |
| 5 | 컴플라이언스 보고서 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "50개 시추공의 검층 데이터 품질 검증을 수동으로 수행하는 것은 한계" |
| Ingestion | 0:45–1:30 | "데이터 업로드로 자동으로 검증 시작" |
| Detection | 1:30–2:30 | "통계적 기법으로 각 커브의 이상을 탐지" |
| Results | 2:30–3:45 | "시추공별·커브별로 이상을 분류·확인" |
| Report | 3:45–5:00 | "규제 준수 보고서를 AI가 자동 생성" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 정상 검층 데이터(LAS 형식, 10개 시추공) | 베이스라인 |
| 2 | 스파이크 이상 데이터(3건) | 이상 탐지 데모 |
| 3 | 결측 구간 데이터(2건) | 품질 체크 데모 |
| 4 | 범위 이탈 데이터(2건) | 분류 데모 |

---

## Timeline

### 1주일 이내 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 검층 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 획득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 실시간 시추 데이터 모니터링
- 지층 대비의 자동화
- 3D 지질 모델 연계

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (LAS Parser) | 검층 데이터 포맷 분석 |
| Lambda (Anomaly Detector) | 통계적 이상 탐지 |
| Lambda (Report Generator) | Bedrock에 의한 컴플라이언스 보고서 생성 |
| Amazon Athena | 검층 데이터의 집계 분석 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| LAS 파싱 실패 | 사전 분석된 데이터를 사용 |
| Bedrock 지연 | 사전 생성 보고서를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 한다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ✅ **E2E 실행**: Phase 1-6에서 확인 완료(루트 README 참조)
- 📸 **UI/UX 재촬영**: ✅ 2026-05-10 재배포 검증에서 촬영 완료 (UC8 Step Functions 그래프, Lambda 실행 성공 확인)
- 🔄 **재현 방법**: 본 문서 말미의 "촬영 가이드"를 참조

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC8 Step Functions Graph view(SUCCEEDED)

![UC8 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/uc8-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색으로 시각화하는 최종 사용자 최중요 화면.

### 기존 스크린샷(Phase 1-6에서 해당분)

#### UC8 Step Functions Graph(SUCCEEDED — Phase 8 IAM 수정 후 재촬영)

![UC8 Step Functions Graph(SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

IAM S3AP 수정 후 재배포. 모든 스텝 SUCCEEDED(2:59).

#### UC8 Step Functions Graph(줌 표시 — 각 스텝 상세)

![UC8 Step Functions Graph(줌 표시)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(segy-metadata/, anomalies/, reports/)
- Athena 쿼리 결과(SEG-Y 메타데이터 통계)
- Rekognition 시추공 로그 이미지 레이블
- 이상 탐지 보고서

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=energy-seismic bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC8`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `seismic/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-energy-seismic-demo-workflow`를 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자 이름은 검은색 처리):
   - S3 출력 버킷 `fsxn-energy-seismic-demo-output-<account>`의 전체 보기
   - AI/ML 출력 JSON의 미리보기(`build/preview_*.html` 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py energy-seismic-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC8`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
