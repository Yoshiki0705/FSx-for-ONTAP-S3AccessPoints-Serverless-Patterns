# EDA 설계 파일 검증 — 데모 가이드

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 가이드는 반도체 설계 엔지니어를 위한 기술 데모를 정의합니다. 데모에서는 설계 파일(GDS/OASIS)의 자동 품질 검증 워크플로를 시연하고, 테이프아웃 전 설계 리뷰를 효율화하는 가치를 제시합니다.

**데모의 핵심 메시지**: 설계 엔지니어가 수동으로 수행하던 IP 블록 간 품질 체크를 자동화된 워크플로로 수 분 이내에 완료하고, AI가 생성하는 설계 리뷰 보고서로 즉시 조치를 취할 수 있도록 합니다.

**예상 시간**: 3~5분(내레이션이 포함된 화면 캡처 동영상)

---

## Target Audience & Persona

### Primary Audience: EDA 최종 사용자(설계 엔지니어)

| 항목 | 세부사항 |
|------|------|
| **직책** | Physical Design Engineer / DRC Engineer / Design Lead |
| **일상 업무** | 레이아웃 설계, DRC 실행, IP 블록 통합, 테이프아웃 준비 |
| **과제** | 여러 IP 블록의 품질을 전체적으로 파악하는 데 시간이 많이 소요됨 |
| **도구 환경** | Calibre, Virtuoso, IC Compiler, Innovus 등의 EDA 도구 |
| **기대 성과** | 설계 품질 문제를 조기에 발견하고 테이프아웃 일정을 준수 |

### Persona: 다나카 씨(Physical Design Lead)

- 대규모 SoC 프로젝트에서 40개 이상의 IP 블록 관리
- 테이프아웃 2주 전에 모든 블록의 품질 리뷰를 수행해야 함
- 각 블록의 GDS/OASIS 파일을 개별적으로 확인하는 것은 비현실적
- "모든 블록의 품질 요약을 한눈에 파악하고 싶다"

---

## Demo Scenario: Pre-tapeout Quality Review

### 시나리오 개요

테이프아웃 전 품질 리뷰 단계에서 설계 리드가 여러 IP 블록(40개 이상의 파일)에 대해 자동 품질 검증을 실행하고, AI가 생성하는 리뷰 보고서를 기반으로 조치를 결정합니다.

### 워크플로 전체 구조

```
설계 파일군        자동 검증          분석 결과           AI 리뷰
(GDS/OASIS)    →   워크플로   →   통계 집계    →    보고서 생성
                    트리거           (Athena SQL)     (자연어)
```

### 데모에서 제시하는 가치

1. **시간 단축**: 수동으로 며칠 걸리는 전체 리뷰를 수 분 만에 완료
2. **망라성**: 모든 IP 블록을 빠짐없이 검증
3. **정량적 판단**: 통계적 이상치 탐지(IQR 방법)를 통한 객관적 품질 평가
4. **실행 가능**: AI가 구체적인 권장 대응을 제시

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**화면**: 설계 프로젝트의 파일 목록(40개 이상의 GDS/OASIS 파일)

**내레이션 요지**:
> 테이프아웃 2주 전. 40개 이상의 IP 블록의 설계 품질을 확인해야 한다.
> 각 파일을 EDA 도구로 개별적으로 열어 체크하는 것은 현실적이지 않다.
> 셀 수 이상, 바운딩 박스 이상치, 명명 규칙 위반 — 이러한 것들을 전체적으로 탐지하는 방법이 필요하다.

**Key Visual**:
- 설계 파일의 디렉터리 구조(.gds, .gds2, .oas, .oasis)
- "수동 리뷰: 예상 3~5일" 텍스트 오버레이

---

### Section 2: Workflow Trigger(0:45–1:30)

**화면**: 설계 엔지니어가 품질 검증 워크플로를 트리거하는 작업

**내레이션 요지**:
> 설계 마일스톤 도달 후 품질 검증 워크플로를 시작한다.
> 대상 디렉터리를 지정하기만 하면 모든 설계 파일의 자동 검증이 시작된다.

**Key Visual**:
- 워크플로 실행 화면(Step Functions 콘솔)
- 입력 파라미터: 대상 볼륨 경로, 파일 필터(.gds/.oasis)
- 실행 시작 확인

**엔지니어의 액션**:
```
대상: /vol/eda_designs/ 하위의 모든 설계 파일
필터: .gds, .gds2, .oas, .oasis
실행: 품질 검증 워크플로 시작
```

---

### Section 3: Automated Analysis(1:30–2:30)

**화면**: 워크플로 실행 중 진행 상황 표시

**내레이션 요지**:
> 워크플로가 자동으로 다음을 실행한다:
> 1. 설계 파일 탐지 및 목록화
> 2. 각 파일의 헤더에서 메타데이터 추출(library_name, cell_count, bounding_box, units)
> 3. 추출된 데이터에 대한 통계 분석(SQL 쿼리)
> 4. AI를 통한 설계 리뷰 보고서 생성
>
> 대용량 GDS 파일(수 GB)이라도 헤더 부분(64KB)만 읽기 때문에 빠르게 처리된다.

**Key Visual**:
- 워크플로의 각 단계가 순차적으로 완료되는 모습
- 병렬 처리(Map State)로 여러 파일이 동시에 처리되는 표시
- 처리 시간: 약 2~3분(40개 파일의 경우)

---

### Section 4: Results Review(2:30–3:45)

**화면**: Athena SQL 쿼리 결과 및 통계 요약

**내레이션 요지**:
> 분석 결과를 SQL로 자유롭게 쿼리할 수 있다.
> 예를 들어 "바운딩 박스가 비정상적으로 큰 셀 표시"와 같은 애드혹 분석이 가능하다.

**Key Visual — Athena 쿼리 예시**:
```sql
-- 바운딩 박스 이상치 탐지
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

### Section 5: Actionable Insights(3:45–5:00)

**화면**: AI 생성 설계 리뷰 보고서

**내레이션 요지**:
> AI가 통계 분석 결과를 해석하여 설계 엔지니어를 위한 리뷰 보고서를 자동 생성한다.
> 리스크 평가, 구체적인 권장 대응, 우선순위가 지정된 액션 아이템이 포함된다.
> 이 보고서를 바탕으로 테이프아웃 전 리뷰 회의에서 즉시 논의를 시작할 수 있다.

**Key Visual — AI 리뷰 보고서(발췌)**:

```markdown
# 설계 리뷰 보고서

## 리스크 평가: Medium

## 탐지 사항 요약
- 바운딩 박스 이상치: 3건
- 명명 규칙 위반: 2건
- 무효 파일: 2건

## 권장 대응(우선순위 순)
1. [High] 무효 파일 2건의 원인 조사
2. [Medium] analog_frontend.oas의 레이아웃 최적화 검토
3. [Low] 명명 규칙 통일(block-a-io → block_a_io)
```

**클로징**:
> 수동으로 며칠 걸리던 전체 리뷰가 수 분 만에 완료.
> 설계 엔지니어는 분석 결과 확인과 조치 결정에 집중할 수 있다.

---

## Screen Capture Plan

### 필요한 화면 캡처 목록

| # | 화면 | 섹션 | 비고 |
|---|------|-----------|------|
| 1 | 설계 파일 디렉터리 목록 | Section 1 | FSx ONTAP 상의 파일 구조 |
| 2 | 워크플로 실행 시작 화면 | Section 2 | Step Functions 콘솔 |
| 3 | 워크플로 실행 중(Map State 병렬 처리) | Section 3 | 진행 상황이 보이는 상태 |
| 4 | 워크플로 완료 화면 | Section 3 | 모든 단계 성공 |
| 5 | Athena 쿼리 에디터 + 결과 | Section 4 | 이상치 탐지 쿼리 |
| 6 | 메타데이터 JSON 출력 예시 | Section 4 | 1개 파일의 추출 결과 |
| 7 | AI 설계 리뷰 보고서 전문 | Section 5 | Markdown 렌더링 표시 |
| 8 | SNS 알림 이메일 | Section 5 | 보고서 완료 알림 |

### 캡처 절차

1. 데모 환경에 샘플 데이터 배치
2. 워크플로를 수동 실행하고 각 단계에서 화면 캡처
3. Athena 콘솔에서 쿼리를 실행하고 결과를 캡처
4. 생성된 보고서를 S3에서 다운로드하여 표시

---

## 검증된 UI/UX 스크린샷(2026-05-10 재검증)

Phase 7 UC15/16/17과 동일한 방침으로, **설계 엔지니어가 일상 업무에서 실제로 보는 UI/UX 화면**을
촬영. Step Functions 그래프와 같은 기술자 전용 뷰는 제외(자세한 내용은
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md) 참조).

### 1. FSx for NetApp ONTAP Volumes — 설계 파일용 볼륨

설계 엔지니어가 보는 ONTAP 볼륨 목록. `eda_demo_vol`에 GDS/OASIS 파일을
NTFS ACL로 관리된 상태로 배치.

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     내용: FSx 콘솔에서 ONTAP Volumes 목록(eda_demo_vol 등), Status=Created, Type=ONTAP
     마스크: 계정 ID, SVM ID 실제 값, 파일 시스템 ID -->
![UC6: FSx Volumes 목록](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. S3 출력 버킷 — 설계 문서·분석 결과 목록

설계 리뷰 담당자가 워크플로 완료 후 결과를 확인하는 화면.
`metadata/` / `athena-results/` / `reports/`의 3개 프리픽스로 정리되어 있음.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     내용: S3 콘솔에서 bucket의 top-level prefix 확인
     마스크: 계정 ID, 버킷 이름 프리픽스 -->
![UC6: S3 출력 버킷](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. S3 출력 버킷 — 설계 문서·분석 결과 목록

설계 리뷰 담당자가 워크플로 완료 후 결과를 확인하는 화면.
`metadata/` / `athena-results/` / `reports/`의 3개 프리픽스로 정리되어 있음.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     내용: S3 콘솔에서 bucket의 top-level prefix 확인
     마스크: 계정 ID, 버킷 이름 프리픽스 -->
![UC6: S3 출력 버킷](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Athena 쿼리 결과 — EDA 메타데이터의 SQL 분석

설계 리드가 애드혹으로 DRC 정보를 탐색하는 화면.
Workgroup은 `fsxn-eda-uc6-workgroup`, 데이터베이스는 `fsxn-eda-uc6-db`.

<!-- SCREENSHOT: uc6-athena-query-result.png
     내용: EDA 메타데이터 테이블의 SELECT 결과(file_key, library_name, cell_count, bounding_box)
     마스크: 계정 ID -->
![UC6: Athena 쿼리 결과](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Bedrock 생성 설계 리뷰 보고서

**UC6의 핵심 기능**: Athena의 DRC 집계 결과를 바탕으로 Bedrock Nova Lite가
Physical Design Lead를 위한 일본어 리뷰 보고서를 생성함.

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     내용: 경영진 요약 + 셀 수 분석 + 명명 규칙 위반 목록 + 리스크 평가 (High/Medium/Low)
     실제 샘플 내용:
       ## 설계 리뷰 요약
       ### 경영진 요약
       이번 DRC 집계 결과를 바탕으로 설계 품질의 전체 평가를 다음과 같이 제시합니다.
       설계 파일은 총 2건이며, 셀 수 분포는 안정적이고 바운딩 박스 이상치는 확인되지 않았습니다.
       그러나 명명 규칙 위반이 6건 발견되었습니다.
       ...
       ### 리스크 평가
       - **High**: 없음
       - **Medium**: 명명 규칙 위반이 6건 확인되었습니다.
       - **Low**: 셀 수 분포나 바운딩 박스 이상치에는 문제가 없습니다.
     마스크: 계정 ID -->
![UC6: Bedrock 설계 리뷰 보고서](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### 실측값(2026-05-10 AWS 배포 검증)

- **Step Functions 실행 시간**: ~30초(Discovery + Map(2 files) + DRC + Report)
- **Bedrock 생성 보고서**: 2,093 bytes(마크다운 형식의 일본어)
- **Athena 쿼리**: 0.02 KB 스캔, 런타임 812 ms
- **실제 스택**: `fsxn-eda-uc6`(ap-northeast-1, 2026-05-10 시점 가동 중)

---

## Narration Outline

### 톤 & 스타일

- **시점**: 설계 엔지니어(다나카 씨)의 1인칭 시점
- **톤**: 실무적, 문제 해결형
- **언어**: 일본어(영어 자막 옵션)
- **속도**: 천천히 명확하게(기술 데모이므로)

### 내레이션 구성

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "테이프아웃 전에 40개 이상 블록의 품질 확인이 필요. 수동으로는 시간이 부족" |
| Trigger | 0:45–1:30 | "설계 마일스톤 후 워크플로를 시작하기만 하면 됨" |
| Analysis | 1:30–2:30 | "헤더 분석 → 메타데이터 추출 → 통계 분석이 자동으로 진행" |
| Results | 2:30–3:45 | "SQL로 자유롭게 쿼리. 이상치를 즉시 특정" |
| Insights | 3:45–5:00 | "AI 보고서로 우선순위가 지정된 조치를 제시. 리뷰 회의에 직결" |

---

## Sample Data Requirements

### 필요한 샘플 데이터

| # | 파일 | 포맷 | 용도 |
|---|---------|------------|------|
| 1 | `top_chip_v3.gds` | GDSII | 메인 칩(대규모, 1000개 이상 셀) |
| 2 | `block_a_io.gds2` | GDSII | I/O 블록(정상 데이터) |
| 3 | `memory_ctrl.oasis` | OASIS | 메모리 컨트롤러(정상 데이터) |
| 4 | `analog_frontend.oas` | OASIS | 아날로그 블록(이상치: 큰 BB) |
| 5 | `test_block_debug.gds` | GDSII | 디버그용(이상치: 높이 이상) |
| 6 | `legacy_io_v1.gds2` | GDSII | 레거시 블록(이상치: 너비·높이) |
| 7 | `block-a-io.gds2` | GDSII | 명명 규칙 위반 샘플 |
| 8 | `TOP CHIP (copy).gds` | GDSII | 명명 규칙 위반 샘플 |

### 샘플 데이터 생성 방침

- **최소 구성**: 8개 파일(위 목록)로 데모의 모든 시나리오를 커버
- **권장 구성**: 40개 이상 파일(통계 분석의 설득력 향상)
- **생성 방법**: Python 스크립트로 유효한 GDSII/OASIS 헤더를 가진 테스트 파일 생성
- **크기**: 헤더 분석만 하므로 각 파일 100KB 정도면 충분

### 기존 데모 환경 확인 사항

- [ ] FSx ONTAP 볼륨에 샘플 데이터가 배치되어 있는가
- [ ] S3 Access Point가 설정되어 있는가
- [ ] Glue Data Catalog의 테이블 정의가 존재하는가
- [ ] Athena 워크그룹을 사용할 수 있는가

---

## Timeline

### 1주일 이내 달성 가능

| # | 작업 | 소요 시간 | 전제 조건 |
|---|--------|---------|---------|
| 1 | 샘플 데이터 생성(8개 파일) | 2시간 | Python 환경 |
| 2 | 데모 환경에서 워크플로 실행 확인 | 2시간 | 배포된 환경 |
| 3 | 화면 캡처 획득(8개 화면) | 3시간 | 작업 2 완료 후 |
| 4 | 내레이션 원고 최종화 | 2시간 | 작업 3 완료 후 |
| 5 | 동영상 편집(캡처 + 내레이션) | 4시간 | 작업 3, 4 완료 후 |
| 6 | 리뷰 & 수정 | 2시간 | 작업 5 완료 후 |
| **합계** | | **15시간** | |

### 전제 조건(1주일 달성을 위해 필요)

- Step Functions 워크플로가 배포되어 정상 작동할 것
- Lambda 함수(Discovery, MetadataExtraction, DrcAggregation, ReportGeneration)가 작동 확인됨
- Athena 테이블과 쿼리가 실행 가능한 상태
- Bedrock 모델 액세스가 활성화됨

### Future Enhancements(향후 확장)

| # | 확장 항목 | 개요 | 우선순위 |
|---|---------|------|--------|
| 1 | DRC 도구 연계 | Calibre/Pegasus의 DRC 결과 파일을 직접 가져오기 | High |
| 2 | 인터랙티브 대시보드 | QuickSight를 통한 설계 품질 대시보드 | Medium |
| 3 | Slack/Teams 알림 | 리뷰 보고서 완료 시 채팅 알림 | Medium |
| 4 | 차이 리뷰 | 이전 실행과의 차이를 자동 탐지·보고 | High |
| 5 | 커스텀 규칙 정의 | 프로젝트 고유의 품질 규칙을 설정 가능하게 | Medium |
| 6 | 다국어 보고서 | 영어/일본어/중국어로 보고서 생성 | Low |
| 7 | CI/CD 통합 | 설계 플로 내 자동 품질 게이트로 통합 | High |
| 8 | 대규모 데이터 대응 | 1000개 이상 파일의 병렬 처리 최적화 | Medium |

---

## Technical Notes(데모 제작자용)

### 사용 컴포넌트(기존 구현만)

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로 전체 오케스트레이션 |
| Lambda (Discovery) | 설계 파일 탐지·목록화 |
| Lambda (MetadataExtraction) | GDSII/OASIS 헤더 파싱 및 메타데이터 추출 |
| Lambda (DrcAggregation) | Athena SQL을 통한 통계 분석 실행 |
| Lambda (ReportGeneration) | Bedrock을 통한 AI 리뷰 보고서 생성 |
| Amazon Athena | 메타데이터에 대한 SQL 쿼리 |
| Amazon Bedrock | 자연어 보고서 생성(Nova Lite / Claude) |

### 데모 실행 시 폴백

| 시나리오 | 대응 |
|---------|------|
| 워크플로 실행 실패 | 사전 녹화된 실행 화면 사용 |
| Bedrock 응답 지연 | 사전 생성된 보고서 표시 |
| Athena 쿼리 타임아웃 | 사전 획득한 결과 CSV 표시 |
| 네트워크 장애 | 모든 화면을 사전 캡처하여 동영상화 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상 제작 가이드로 작성되었습니다.*
