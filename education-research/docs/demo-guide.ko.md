# 논문 분류·인용 네트워크 분석 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 학술 논문의 자동 분류와 인용 네트워크 분석 파이프라인을 실연한다. 대량의 논문 PDF에서 메타데이터를 추출하고 연구 트렌드를 가시화한다.

**데모의 핵심 메시지**: 논문 컬렉션을 자동 분류하고 인용 관계를 분석함으로써 연구 분야의 전체상과 중요 논문을 즉시 파악한다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | 연구자 / 도서관정보학 전문가 / 리서치 어드미니스트레이터 |
| **일상 업무** | 문헌 조사, 연구 동향 분석, 논문 관리 |
| **과제** | 대량의 논문에서 관련 연구를 효율적으로 발견할 수 없음 |
| **기대하는 성과** | 연구 분야의 매핑과 중요 논문의 자동 특정 |

### Persona: 와타나베 씨(연구자)

- 새로운 연구 테마의 문헌 서베이를 실시 중
- 500+ 논문의 PDF를 수집했지만 전체상을 파악할 수 없음
- "분야별로 자동 분류하고 인용이 많은 중요 논문을 특정하고 싶다"

---

## Demo Scenario: 문헌 컬렉션의 자동 분석

### 워크플로우 전체상

```
논문 PDF 군       메타데이터 추출     분류·분석        가시화 레포트
(500+ 건)    →   타이틀/저자  →  토픽 분류  →   네트워크
                  인용 정보          인용 해석          맵 생성
```

---

## Storyboard(5 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 500편 이상의 논문 PDF를 수집. 분야별 분포, 중요 논문, 연구 트렌드를 파악하고 싶지만 전부 읽는 것은 불가능.

**Key Visual**: 논문 PDF 파일 목록(대량)

### Section 2: Metadata Extraction(0:45–1:30)

**내레이션 요지**:
> 각 논문 PDF에서 타이틀, 저자, 초록, 인용 리스트를 자동 추출.

**Key Visual**: 메타데이터 추출 처리, 추출 결과 샘플

### Section 3: Classification(1:30–2:30)

**내레이션 요지**:
> AI가 초록을 해석하고 연구 토픽을 자동 분류. 클러스터링을 통해 관련 논문 그룹을 형성.

**Key Visual**: 토픽 분류 결과, 카테고리별 논문 수

### Section 4: Citation Analysis(2:30–3:45)

**내레이션 요지**:
> 인용 관계를 해석하고 피인용 수가 많은 중요 논문을 특정. 인용 네트워크의 구조를 분석.

**Key Visual**: 인용 네트워크 통계, 중요 논문 랭킹

### Section 5: Research Map(3:45–5:00)

**내레이션 요지**:
> AI가 연구 분야의 전체상을 서머리 레포트로 생성. 트렌드, 갭, 향후 연구 방향을 제시.

**Key Visual**: 연구 맵 레포트(트렌드 분석 + 추천 문헌)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 논문 PDF 컬렉션 | Section 1 |
| 2 | 메타데이터 추출 결과 | Section 2 |
| 3 | 토픽 분류 결과 | Section 3 |
| 4 | 인용 네트워크 통계 | Section 4 |
| 5 | 연구 맵 레포트 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 키 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "500편의 논문 전체상을 파악하고 싶다" |
| Extraction | 0:45–1:30 | "PDF에서 메타데이터를 자동 추출" |
| Classification | 1:30–2:30 | "AI가 토픽별로 자동 분류" |
| Citation | 2:30–3:45 | "인용 네트워크로 중요 논문을 특정" |
| Map | 3:45–5:00 | "연구 분야의 전체상과 트렌드를 가시화" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 논문 PDF(30건, 3분야) | 메인 처리 대상 |
| 2 | 인용 관계 데이터(상호 인용 있음) | 네트워크 분석 데모 |
| 3 | 고피인용 논문(5건) | 중요 논문 특정 데모 |

---

## Timeline

### 1주일 이내에 달성 가능

| 태스크 | 소요 시간 |
|--------|---------|
| 샘플 논문 데이터 준비 | 3시간 |
| 파이프라인 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- 인터랙티브 인용 네트워크 가시화
- 논문 추천 시스템
- 정기적인 신착 논문의 자동 분류

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (PDF Parser) | 논문 PDF 메타데이터 추출 |
| Lambda (Classifier) | Bedrock에 의한 토픽 분류 |
| Lambda (Citation Analyzer) | 인용 네트워크 구축·분석 |
| Amazon Athena | 메타데이터 집계·검색 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| PDF 파싱 실패 | 사전 추출 완료 데이터를 사용 |
| 분류 정확도 부족 | 사전 분류 완료 결과를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **엔드 유저가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 한다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약.

### 이 유스케이스의 검증 상태

- ✅ **E2E 실행**: Phase 1-6에서 확인 완료(루트 README 참조)
- 📸 **UI/UX 재촬영**: ✅ 2026-05-10 재배포 검증에서 촬영 완료 (UC13 Step Functions 그래프, Lambda 실행 성공을 확인)
- 🔄 **재현 방법**: 본 문서 말미의 "촬영 가이드"를 참조

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC13 Step Functions Graph view(SUCCEEDED)

![UC13 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 스테이트의 실행 상황을
색으로 가시화하는 엔드 유저 최중요 화면.

### 기존 스크린샷(Phase 1-6에서 해당분)

![UC13 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph(전체 조감)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph(줌 표시 — 각 스텝 상세)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### 재검증 시 UI/UX 대상 화면(권장 촬영 리스트)

- S3 출력 버킷(papers-ocr/, citations/, reports/)
- Textract 논문 OCR 결과(Cross-Region)
- Comprehend 엔티티 검출(저자, 인용, 키워드)
- 연구 네트워크 분석 레포트

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=education-research bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC13`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `papers/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-education-research-demo-workflow`를 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자명은 검은색 칠):
   - S3 출력 버킷 `fsxn-education-research-demo-output-<account>`의 조감
   - AI/ML 출력 JSON의 프리뷰(`build/preview_*.html`의 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py education-research-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **클린업**:
   - `bash scripts/cleanup_generic_ucs.sh UC13`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS의 사양)
