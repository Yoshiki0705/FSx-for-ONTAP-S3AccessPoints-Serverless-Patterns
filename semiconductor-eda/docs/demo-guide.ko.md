# EDA 설계 파일 검증 — 데모 가이드

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 가이드는 반도체 설계 엔지니어를 위한 기술 데모를 정의합니다. 데모에서는 설계 파일(GDS/OASIS)의 자동 품질 검증 워크플로를 시연하며, 테이프아웃 전 설계 리뷰를 효율화하는 가치를 보여줍니다.

**데모 핵심 메시지**: 설계 엔지니어가 수동으로 수행하던 IP 블록 횡단 품질 검사를 자동화된 워크플로로 수 분 내에 완료하고, AI가 생성하는 설계 리뷰 리포트로 즉시 조치를 취할 수 있도록 합니다.

**예상 시간**: 3~5분 (내레이션 포함 화면 캡처 영상)

---

## Target Audience & Persona

### Primary Audience: EDA 최종 사용자 (설계 엔지니어)

| 항목 | 상세 |
|------|------|
| **직책** | Physical Design Engineer / DRC Engineer / Design Lead |
| **일상 업무** | 레이아웃 설계, DRC 실행, IP 블록 통합, 테이프아웃 준비 |
| **과제** | 여러 IP 블록의 품질을 횡단적으로 파악하는 데 시간이 많이 소요됨 |
| **도구 환경** | Calibre, Virtuoso, IC Compiler, Innovus 등의 EDA 도구 |
| **기대 성과** | 설계 품질 문제를 조기에 발견하여 테이프아웃 일정을 준수 |

### Persona: 다나카 씨 (Physical Design Lead)

- 대규모 SoC 프로젝트에서 40개 이상의 IP 블록을 관리
- 테이프아웃 2주 전에 모든 블록의 품질 리뷰를 실시해야 함
- 각 블록의 GDS/OASIS 파일을 개별적으로 확인하는 것은 비현실적
- "모든 블록의 품질 요약을 한눈에 파악하고 싶다"

---

## Demo Scenario: Pre-tapeout Quality Review

### 시나리오 개요

테이프아웃 전 품질 리뷰 단계에서, 설계 리드가 여러 IP 블록(40개 이상 파일)에 대해 자동 품질 검증을 실행하고, AI가 생성한 리뷰 리포트를 기반으로 조치를 결정합니다.

### 전체 워크플로

```
설계 파일군        자동 검증          분석 결과           AI 리뷰
(GDS/OASIS)    →   워크플로    →   통계 집계    →    리포트 생성
                    트리거           (Athena SQL)     (자연어)
```

### 데모에서 보여주는 가치

1. **시간 단축**: 수동으로 수일 걸리던 횡단 리뷰를 수 분 만에 완료
2. **완전성**: 모든 IP 블록을 빠짐없이 검증
3. **정량적 판단**: 통계적 이상치 검출(IQR 방법)에 의한 객관적 품질 평가
4. **실행 가능**: AI가 구체적인 권장 조치를 제시

---

## Storyboard (5개 섹션 / 3~5분)

### Section 1: Problem Statement (0:00–0:45)

**화면**: 설계 프로젝트의 파일 목록 (40개 이상의 GDS/OASIS 파일)

**내레이션 요지**:
> 테이프아웃 2주 전. 40개 이상의 IP 블록의 설계 품질을 확인해야 합니다.
> 각 파일을 EDA 도구로 개별적으로 열어 확인하는 것은 현실적이지 않습니다.
> 셀 수 이상, 바운딩 박스 이상치, 명명 규칙 위반 — 이를 횡단적으로 검출할 방법이 필요합니다.

**Key Visual**:
- 설계 파일 디렉토리 구조 (.gds, .gds2, .oas, .oasis)
- "수동 리뷰: 예상 3~5일" 텍스트 오버레이

---

### Section 2: Workflow Trigger (0:45–1:30)

**화면**: 설계 엔지니어가 품질 검증 워크플로를 트리거하는 조작

**내레이션 요지**:
> 설계 마일스톤 도달 후, 품질 검증 워크플로를 시작합니다.
> 대상 디렉토리를 지정하기만 하면 모든 설계 파일의 자동 검증이 시작됩니다.

**Key Visual**:
- 워크플로 실행 화면 (Step Functions 콘솔)
- 입력 파라미터: 대상 볼륨 경로, 파일 필터 (.gds/.oasis)
- 실행 시작 확인

**엔지니어의 조작**:
```
대상: /vol/eda_designs/ 하위의 모든 설계 파일
필터: .gds, .gds2, .oas, .oasis
실행: 품질 검증 워크플로 시작
```

---

### Section 3: Automated Analysis (1:30–2:30)

**화면**: 워크플로 실행 중 진행 상황 표시

**내레이션 요지**:
> 워크플로가 자동으로 다음을 실행합니다:
> 1. 설계 파일 검출 및 목록화
> 2. 각 파일 헤더에서 메타데이터 추출 (library_name, cell_count, bounding_box, units)
> 3. 추출 데이터에 대한 통계 분석 (SQL 쿼리)
> 4. AI에 의한 설계 리뷰 리포트 생성
>
> 대용량 GDS 파일(수 GB)도 헤더 부분(64KB)만 읽기 때문에 빠르게 처리됩니다.

**Key Visual**:
- 워크플로의 각 단계가 순차적으로 완료되는 모습
- 병렬 처리(Map State)로 여러 파일이 동시에 처리되는 표시
- 처리 시간: 약 2~3분 (40개 파일의 경우)

---

### Section 4: Results Review (2:30–3:45)

**화면**: Athena SQL 쿼리 결과 및 통계 요약

**내레이션 요지**:
> 분석 결과를 SQL로 자유롭게 쿼리할 수 있습니다.
> 예를 들어 "바운딩 박스가 비정상적으로 큰 셀 표시"와 같은 애드혹 분석이 가능합니다.

**Key Visual — Athena 쿼리 예시**:
```sql
-- 바운딩 박스 이상치 검출
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — 쿼리 결과**:

| file_key | library_name | width | height | 판정 |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | 이상치 |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | 이상치 |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | 이상치 |

---

### Section 5: Actionable Insights (3:45–5:00)

**화면**: AI 생성 설계 리뷰 리포트

**내레이션 요지**:
> AI가 통계 분석 결과를 해석하여 설계 엔지니어를 위한 리뷰 리포트를 자동 생성합니다.
> 리스크 평가, 구체적인 권장 조치, 우선순위가 매겨진 액션 아이템이 포함됩니다.
> 이 리포트를 바탕으로 테이프아웃 전 리뷰 회의에서 즉시 논의를 시작할 수 있습니다.

**Key Visual — AI 리뷰 리포트 (발췌)**:

```markdown
# 설계 리뷰 리포트

## 리스크 평가: Medium

## 검출 사항 요약
- 바운딩 박스 이상치: 3건
- 명명 규칙 위반: 2건
- 무효 파일: 2건

## 권장 조치 (우선순위순)
1. [High] 무효 파일 2건의 원인 조사
2. [Medium] analog_frontend.oas의 레이아웃 최적화 검토
3. [Low] 명명 규칙 통일 (block-a-io → block_a_io)
```

**클로징**:
> 수동으로 수일 걸리던 횡단 리뷰가 수 분 만에 완료됩니다.
> 설계 엔지니어는 분석 결과 확인과 조치 결정에 집중할 수 있습니다.

---

## Screen Capture Plan

### 필요한 화면 캡처 목록

| # | 화면 | 섹션 | 비고 |
|---|------|------|------|
| 1 | 설계 파일 디렉토리 목록 | Section 1 | FSx ONTAP 상의 파일 구조 |
| 2 | 워크플로 실행 시작 화면 | Section 2 | Step Functions 콘솔 |
| 3 | 워크플로 실행 중 (Map State 병렬 처리) | Section 3 | 진행 상황이 보이는 상태 |
| 4 | 워크플로 완료 화면 | Section 3 | 모든 단계 성공 |
| 5 | Athena 쿼리 에디터 + 결과 | Section 4 | 이상치 검출 쿼리 |
| 6 | 메타데이터 JSON 출력 예시 | Section 4 | 1개 파일의 추출 결과 |
| 7 | AI 설계 리뷰 리포트 전문 | Section 5 | Markdown 렌더링 표시 |
| 8 | SNS 알림 이메일 | Section 5 | 리포트 완료 알림 |

### 캡처 절차

1. 데모 환경에 샘플 데이터 배치
2. 워크플로를 수동 실행하고 각 단계에서 화면 캡처
3. Athena 콘솔에서 쿼리를 실행하고 결과 캡처
4. 생성된 리포트를 S3에서 다운로드하여 표시

---

## Narration Outline

### 톤 & 스타일

- **시점**: 설계 엔지니어(다나카 씨)의 1인칭 시점
- **톤**: 실무적, 문제 해결형
- **언어**: 일본어 (영어 자막 옵션)
- **속도**: 천천히 명확하게 (기술 데모이므로)

### 내레이션 구성

| 섹션 | 시간 | 핵심 메시지 |
|------|------|------------|
| Problem | 0:00–0:45 | "테이프아웃 전에 40개 이상 블록의 품질 확인이 필요. 수동으로는 시간이 부족" |
| Trigger | 0:45–1:30 | "설계 마일스톤 후 워크플로를 시작하기만 하면 됨" |
| Analysis | 1:30–2:30 | "헤더 해석 → 메타데이터 추출 → 통계 분석이 자동으로 진행" |
| Results | 2:30–3:45 | "SQL로 자유롭게 쿼리. 이상치를 즉시 특정" |
| Insights | 3:45–5:00 | "AI 리포트로 우선순위 조치를 제시. 리뷰 회의에 직결" |

---

## Sample Data Requirements

### 필요한 샘플 데이터

| # | 파일 | 포맷 | 용도 |
|---|------|------|------|
| 1 | `top_chip_v3.gds` | GDSII | 메인 칩 (대규모, 1000+ 셀) |
| 2 | `block_a_io.gds2` | GDSII | I/O 블록 (정상 데이터) |
| 3 | `memory_ctrl.oasis` | OASIS | 메모리 컨트롤러 (정상 데이터) |
| 4 | `analog_frontend.oas` | OASIS | 아날로그 블록 (이상치: 큰 BB) |
| 5 | `test_block_debug.gds` | GDSII | 디버그용 (이상치: 높이 이상) |
| 6 | `legacy_io_v1.gds2` | GDSII | 레거시 블록 (이상치: 폭·높이) |
| 7 | `block-a-io.gds2` | GDSII | 명명 규칙 위반 샘플 |
| 8 | `TOP CHIP (copy).gds` | GDSII | 명명 규칙 위반 샘플 |

### 샘플 데이터 생성 방침

- **최소 구성**: 8개 파일 (위 목록)로 데모의 모든 시나리오를 커버
- **권장 구성**: 40개 이상 파일 (통계 분석의 설득력 향상)
- **생성 방법**: Python 스크립트로 유효한 GDSII/OASIS 헤더를 가진 테스트 파일 생성
- **크기**: 헤더 해석만 수행하므로 각 파일 약 100KB로 충분

### 기존 데모 환경 확인 사항

- [ ] FSx ONTAP 볼륨에 샘플 데이터 배치 완료 여부
- [ ] S3 Access Point 설정 완료 여부
- [ ] Glue Data Catalog 테이블 정의 존재 여부
- [ ] Athena 워크그룹 사용 가능 여부

---

## Timeline

### 1주일 이내 달성 가능

| # | 태스크 | 소요 시간 | 전제 조건 |
|---|--------|----------|----------|
| 1 | 샘플 데이터 생성 (8개 파일) | 2시간 | Python 환경 |
| 2 | 데모 환경에서 워크플로 실행 확인 | 2시간 | 배포 완료된 환경 |
| 3 | 화면 캡처 취득 (8개 화면) | 3시간 | 태스크 2 완료 후 |
| 4 | 내레이션 원고 최종화 | 2시간 | 태스크 3 완료 후 |
| 5 | 영상 편집 (캡처 + 내레이션) | 4시간 | 태스크 3, 4 완료 후 |
| 6 | 리뷰 & 수정 | 2시간 | 태스크 5 완료 후 |
| **합계** | | **15시간** | |

### 전제 조건 (1주일 달성을 위해 필요)

- Step Functions 워크플로가 배포 완료되어 정상 동작할 것
- Lambda 함수 (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration)가 동작 확인 완료
- Athena 테이블과 쿼리가 실행 가능한 상태
- Bedrock 모델 액세스가 활성화

### Future Enhancements (향후 확장)

| # | 확장 항목 | 개요 | 우선순위 |
|---|----------|------|---------|
| 1 | DRC 도구 연동 | Calibre/Pegasus의 DRC 결과 파일을 직접 수집 | High |
| 2 | 인터랙티브 대시보드 | QuickSight를 통한 설계 품질 대시보드 | Medium |
| 3 | Slack/Teams 알림 | 리뷰 리포트 완료 시 채팅 알림 | Medium |
| 4 | 차분 리뷰 | 이전 실행과의 차이를 자동 검출·리포트 | High |
| 5 | 커스텀 규칙 정의 | 프로젝트 고유의 품질 규칙을 설정 가능하게 | Medium |
| 6 | 다국어 리포트 | 영어/일본어/중국어로 리포트 생성 | Low |
| 7 | CI/CD 통합 | 설계 플로 내 자동 품질 게이트로 통합 | High |
| 8 | 대규모 데이터 대응 | 1000개 이상 파일의 병렬 처리 최적화 | Medium |

---

## Technical Notes (데모 작성자용)

### 사용 컴포넌트 (기존 구현만)

| 컴포넌트 | 역할 |
|----------|------|
| Step Functions | 워크플로 전체 오케스트레이션 |
| Lambda (Discovery) | 설계 파일 검출·목록화 |
| Lambda (MetadataExtraction) | GDSII/OASIS 헤더 파싱 및 메타데이터 추출 |
| Lambda (DrcAggregation) | Athena SQL을 통한 통계 분석 실행 |
| Lambda (ReportGeneration) | Bedrock을 통한 AI 리뷰 리포트 생성 |
| Amazon Athena | 메타데이터에 대한 SQL 쿼리 |
| Amazon Bedrock | 자연어 리포트 생성 (Nova Lite / Claude) |

### 데모 실행 시 폴백

| 시나리오 | 대응 |
|----------|------|
| 워크플로 실행 실패 | 사전 녹화된 실행 화면 사용 |
| Bedrock 응답 지연 | 사전 생성된 리포트 표시 |
| Athena 쿼리 타임아웃 | 사전 취득된 결과 CSV 표시 |
| 네트워크 장애 | 모든 화면을 사전 캡처하여 영상화 |

---

*본 문서는 기술 프레젠테이션용 데모 영상의 제작 가이드로 작성되었습니다.*
