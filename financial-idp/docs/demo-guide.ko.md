# 계약서·청구서 자동 처리 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 계약서·청구서의 자동 처리 파이프라인을 실연한다. OCR에 의한 텍스트 추출과 엔티티 추출을 결합하여 비구조화 문서에서 구조화 데이터를 자동 생성한다.

**데모의 핵심 메시지**: 종이 기반의 계약서·청구서를 자동으로 디지털화하고, 금액·날짜·거래처 등의 중요 정보를 즉시 추출·구조화한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 상세 |
|------|------|
| **직책** | 경리부문 매니저 / 계약 관리 담당 |
| **일상 업무** | 청구서 처리, 계약서 관리, 지급 승인 |
| **과제** | 대량의 종이 문서 수동 입력에 시간이 소요됨 |
| **기대하는 성과** | 문서 처리 자동화와 입력 오류 감소 |

### Persona: 야마다 씨(경리부문 리더)

- 월간 200+ 건의 청구서를 처리
- 수동 입력에 의한 오류와 지연이 과제
- "청구서가 도착하면 자동으로 금액과 지급 기한을 추출하고 싶다"

---

## Demo Scenario: 청구서 배치 처리

### 워크플로우 전체 구조

```
문서 스캔       OCR 처리        엔티티       구조화 데이터
(PDF/이미지)   →   텍스트 추출  →   추출·분류   →    출력 (JSON)
                                   (AI 분석)
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 월간 도착하는 200건 이상의 청구서. 수동으로 금액·날짜·거래처를 입력하는 것은 시간이 걸리고, 오류도 발생한다.

**Key Visual**: 대량의 PDF 청구서 파일 목록

### Section 2: Document Upload(0:45–1:30)

**내레이션 요지**:
> 스캔 완료 문서를 파일 서버에 배치하는 것만으로 자동 처리 파이프라인이 시작된다.

**Key Visual**: 파일 업로드 → 워크플로우 자동 시작

### Section 3: OCR & Extraction(1:30–2:30)

**내레이션 요지**:
> OCR로 텍스트를 추출하고, AI가 문서 타입을 판정. 청구서·계약서·영수증을 자동 분류하고, 각 문서에서 중요 필드를 추출한다.

**Key Visual**: OCR 처리 진행, 문서 분류 결과

### Section 4: Structured Output(2:30–3:45)

**내레이션 요지**:
> 추출 결과를 구조화 데이터로 출력. 금액, 지급 기한, 거래처명, 청구 번호 등이 JSON 형식으로 이용 가능.

**Key Visual**: 추출 결과 테이블(청구 번호, 금액, 기한, 거래처)

### Section 5: Validation & Report(3:45–5:00)

**내레이션 요지**:
> AI가 추출 결과의 신뢰도를 평가하고, 낮은 신뢰도 항목을 플래그. 처리 요약 보고서로 전체 처리 상황을 파악.

**Key Visual**: 신뢰도 점수 포함 결과, 처리 요약 보고서

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 청구서 PDF 파일 목록 | Section 1 |
| 2 | 워크플로우 자동 시작 | Section 2 |
| 3 | OCR 처리·문서 분류 결과 | Section 3 |
| 4 | 구조화 데이터 출력(JSON/테이블) | Section 4 |
| 5 | 처리 요약 보고서 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "월 200건의 청구서를 수동 처리하는 것은 한계" |
| Upload | 0:45–1:30 | "파일 배치만으로 자동 처리가 시작" |
| OCR | 1:30–2:30 | "OCR + AI로 문서 분류와 필드 추출" |
| Output | 2:30–3:45 | "구조화 데이터로 즉시 이용 가능" |
| Report | 3:45–5:00 | "신뢰도 평가로 인적 확인이 필요한 부분을 명시" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 청구서 PDF(10건) | 메인 처리 대상 |
| 2 | 계약서 PDF(3건) | 문서 분류 데모 |
| 3 | 영수증 이미지(3건) | 이미지 OCR 데모 |
| 4 | 저품질 스캔(2건) | 신뢰도 평가 데모 |

---

## Timeline

### 1주일 이내에 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 문서 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 회계 시스템으로의 자동 연계
- 승인 워크플로우 통합
- 다국어 문서 대응(영어·중국어)

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (OCR Processor) | Textract에 의한 문서 텍스트 추출 |
| Lambda (Entity Extractor) | Bedrock에 의한 엔티티 추출 |
| Lambda (Classifier) | 문서 타입 분류 |
| Amazon Athena | 추출 데이터의 집계 분석 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| OCR 정확도 저하 | 사전 처리 완료 텍스트를 사용 |
| Bedrock 지연 | 사전 생성 결과를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대해: FSxN S3 Access Point (Pattern A)

UC2 financial-idp는 **Pattern A: Native S3AP Output**으로 분류됩니다
(`docs/output-destination-patterns.md` 참조).

**설계**: 청구서 OCR 결과, 구조화 메타데이터, BedRock 요약은 모두 FSxN S3 Access Point 경유로
원본 청구서 PDF와 **동일한 FSx ONTAP 볼륨**에 기록됩니다. 표준 S3 버킷은
생성되지 않습니다("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력 데이터 읽기용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력 쓰기용 S3 AP Alias(입력과 동일해도 가능)

**배포 예시**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (기타 필수 파라미터)
```

**SMB/NFS 사용자 관점**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # 원본 청구서
  └── summaries/2026/05/                # AI 생성 요약(동일 볼륨 내)
      └── invoice_001.json
```

AWS 사양상의 제약에 대해서는
[프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조.

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 한다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ⚠️ **E2E 검증**: 일부 기능만(프로덕션 환경에서는 추가 검증 권장)
- 📸 **UI/UX 촬영**: ✅ SFN Graph 완료(Phase 8 Theme D, commit 081cc66)

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC2 Step Functions Graph view(SUCCEEDED)

![UC2 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색으로 시각화하는 최종 사용자 최중요 화면.

### 기존 스크린샷(Phase 1-6에서 해당분)

![UC2 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(textract-results/, comprehend-entities/, reports/)
- Textract OCR 결과 JSON(계약서·청구서에서 추출된 필드)
- Comprehend 엔티티 검출 결과(조직명, 날짜, 금액)
- Bedrock 생성 요약 보고서

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=financial-idp bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC2`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `invoices/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-financial-idp-demo-workflow`를 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자명은 검은색 처리):
   - S3 출력 버킷 `fsxn-financial-idp-demo-output-<account>`의 전체 뷰
   - AI/ML 출력 JSON의 프리뷰(`build/preview_*.html` 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py financial-idp-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요 시)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC2`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)
