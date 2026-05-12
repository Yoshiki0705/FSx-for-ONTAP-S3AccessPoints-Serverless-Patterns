# 배송 전표 OCR・재고 분석 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 배송 전표의 OCR 처리와 재고 분석 파이프라인을 실연한다. 종이 전표를 디지털화하고, 입출고 데이터를 자동 집계·분석한다.

**데모의 핵심 메시지**: 배송 전표를 자동으로 디지털화하여 재고 상황의 실시간 파악과 수요 예측을 지원한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 상세 |
|------|------|
| **직책** | 물류 매니저 / 창고 관리자 |
| **일상 업무** | 입출고 관리, 재고 확인, 배송 수배 |
| **과제** | 종이 전표의 수동 입력으로 인한 지연과 오류 |
| **기대하는 성과** | 전표 처리의 자동화와 재고 가시화 |

### Persona: 사이토 씨(물류 매니저)

- 1일 500+ 장의 배송 전표를 처리
- 수동 입력의 타임 래그로 재고 정보가 항상 지연됨
- "전표를 스캔하는 것만으로 재고에 반영시키고 싶다"

---

## Demo Scenario: 배송 전표 배치 처리

### 워크플로우 전체 구조

```
배송 전표          OCR 처리       데이터 구조화       재고 분석
(스캔 이미지) →  텍스트 추출 →  필드       →   집계 레포트
                               매핑          수요 예측
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 1일 500장 이상의 배송 전표. 수동 입력으로는 재고 정보의 업데이트가 지연되어 결품이나 과잉 재고의 리스크가 높아진다.

**Key Visual**: 대량의 전표 스캔 이미지, 수동 입력의 지연 이미지

### Section 2: Scan & Upload(0:45–1:30)

**내레이션 요지**:
> 스캔한 전표 이미지를 폴더에 배치하는 것만으로 OCR 파이프라인이 자동 기동.

**Key Visual**: 전표 이미지 업로드 → 워크플로우 기동

### Section 3: OCR Processing(1:30–2:30)

**내레이션 요지**:
> OCR로 전표의 텍스트를 추출하고, AI가 품명, 수량, 수신처, 날짜 등의 필드를 자동 매핑.

**Key Visual**: OCR 처리 중, 필드 추출 결과

### Section 4: Inventory Analysis(2:30–3:45)

**내레이션 요지**:
> 추출 데이터를 재고 데이터베이스와 대조. 입출고를 자동 집계하고 재고 상황을 업데이트.

**Key Visual**: 재고 집계 결과, 품목별 입출고 추이

### Section 5: Demand Report(3:45–5:00)

**내레이션 요지**:
> AI가 재고 분석 레포트를 생성. 재고 회전율, 결품 리스크 품목, 발주 권장을 제시.

**Key Visual**: AI 생성 재고 레포트(재고 서머리 + 발주 권장)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 전표 스캔 이미지 목록 | Section 1 |
| 2 | 업로드·파이프라인 기동 | Section 2 |
| 3 | OCR 추출 결과 | Section 3 |
| 4 | 재고 집계 대시보드 | Section 4 |
| 5 | AI 재고 분석 레포트 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 키 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "수동 입력의 지연으로 재고 정보가 항상 오래됨" |
| Upload | 0:45–1:30 | "스캔 배치만으로 자동 처리 시작" |
| OCR | 1:30–2:30 | "AI가 전표 필드를 자동 인식·구조화" |
| Analysis | 2:30–3:45 | "입출고를 자동 집계하고 재고를 즉시 업데이트" |
| Report | 3:45–5:00 | "결품 리스크와 발주 권장을 AI가 제시" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 입고 전표 이미지(10장) | OCR 처리 데모 |
| 2 | 출고 전표 이미지(10장) | 재고 감산 데모 |
| 3 | 수기 전표(3장) | OCR 정확도 데모 |
| 4 | 재고 마스터 데이터 | 대조 데모 |

---

## Timeline

### 1주일 이내에 달성 가능

| 태스크 | 소요 시간 |
|--------|---------|
| 샘플 전표 이미지 준비 | 2시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 실시간 전표 처리(카메라 연계)
- WMS 시스템 연계
- 수요 예측 모델 통합

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (OCR Processor) | Textract에 의한 전표 텍스트 추출 |
| Lambda (Field Mapper) | Bedrock에 의한 필드 매핑 |
| Lambda (Inventory Updater) | 재고 데이터 업데이트·집계 |
| Lambda (Report Generator) | 재고 분석 레포트 생성 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| OCR 정확도 저하 | 사전 처리된 데이터를 사용 |
| Bedrock 지연 | 사전 생성 레포트를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대하여: OutputDestination으로 선택 가능 (Pattern B)

UC12 logistics-ocr은 2026-05-10 업데이트에서 `OutputDestination` 파라미터를 지원했습니다
(`docs/output-destination-patterns.md` 참조).

**대상 워크로드**: 배송 전표 OCR / 재고 분석 / 물류 레포트

**2가지 모드**:

### STANDARD_S3(기본값, 종래대로)
새로운 S3 버킷(`${AWS::StackName}-output-${AWS::AccountId}`)을 생성하고,
AI 산출물을 거기에 기록합니다.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (기타 필수 파라미터)
```

### FSXN_S3AP("no data movement" 패턴)
AI 산출물을 FSxN S3 Access Point 경유로 원본 데이터와 **동일한 FSx ONTAP 볼륨**에
기록합니다. SMB/NFS 사용자가 업무에서 사용하는 디렉터리 구조 내에서 AI 산출물을
직접 열람할 수 있습니다. 표준 S3 버킷은 생성되지 않습니다.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (기타 필수 파라미터)
```

**주의사항**:

- `S3AccessPointName` 지정을 강력히 권장(Alias 형식과 ARN 형식 모두 IAM 허가)
- 5GB 초과 객체는 FSxN S3AP에서 불가(AWS 사양), 멀티파트 업로드 필수
- AWS 사양상의 제약은
  [프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
  및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조

---

## 검증된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 한다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ✅ **E2E 실행**: Phase 1-6에서 확인 완료(루트 README 참조)
- 📸 **UI/UX 재촬영**: ✅ 2026-05-10 재배포 검증에서 촬영 완료 (UC12 Step Functions 그래프, Lambda 실행 성공 확인)
- 🔄 **재현 방법**: 본 문서 말미의 "촬영 가이드"를 참조

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC12 Step Functions Graph view(SUCCEEDED)

![UC12 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색으로 가시화하는 최종 사용자 최중요 화면.

### 기존 스크린샷(Phase 1-6에서 해당분)

![UC12 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph(줌 표시 — 각 스텝 상세)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(waybills-ocr/, inventory/, reports/)
- Textract 전표 OCR 결과(Cross-Region)
- Rekognition 창고 이미지 레이블
- 배송 집계 레포트

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=logistics-ocr bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC12`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `waybills/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-logistics-ocr-demo-workflow`를 기동(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자 이름은 검은색 칠)
   - S3 출력 버킷 `fsxn-logistics-ocr-demo-output-<account>`의 조감
   - AI/ML 출력 JSON의 프리뷰(`build/preview_*.html` 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py logistics-ocr-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **클린업**:
   - `bash scripts/cleanup_generic_ucs.sh UC12`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
