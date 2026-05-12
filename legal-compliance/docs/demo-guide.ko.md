# 파일 서버 권한 감사 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 참고: 이 번역은 Amazon Bedrock Claude로 생성되었습니다. 번역 품질 향상에 대한 기여를 환영합니다.

## Executive Summary

본 데모에서는 파일 서버상의 과도한 액세스 권한을 자동 검출하는 감사 워크플로를 실연합니다. NTFS ACL을 분석하고, 최소 권한 원칙을 위반하는 항목을 식별하여 컴플라이언스 보고서를 자동 생성합니다.

**데모의 핵심 메시지**: 수동으로 수 주가 소요되는 파일 서버 권한 감사를 자동화하고, 과도한 권한의 리스크를 즉시 가시화합니다.

**예상 시간**: 3~5분

---

## Target Audience & Persona

| 항목 | 세부사항 |
|------|------|
| **직책** | 정보 보안 담당 / IT 컴플라이언스 관리자 |
| **일상 업무** | 액세스 권한 검토, 감사 대응, 보안 정책 관리 |
| **과제** | 수천 개 폴더의 권한을 수동으로 확인하는 것은 비현실적 |
| **기대 성과** | 과도한 권한의 조기 발견과 컴플라이언스 증적의 자동화 |

### Persona: 사토 씨(정보 보안 관리자)

- 연차 감사에서 모든 공유 폴더의 권한 검토가 필요
- "Everyone 전체 제어" 등의 위험한 설정을 즉시 검출하고 싶음
- 감사 법인에 제출할 보고서를 효율적으로 작성하고 싶음

---

## Demo Scenario: 연차 권한 감사의 자동화

### 워크플로 전체 구조

```
파일 서버     ACL 수집        권한 분석          보고서 생성
(NTFS 공유)   →   메타데이터   →   위반 검출    →    감사 보고서
                   추출            (규칙 대조)      (AI 요약)
```

---

## Storyboard(5개 섹션 / 3~5분)

### Section 1: Problem Statement(0:00–0:45)

**내레이션 요지**:
> 연차 감사 시기. 수천 개의 공유 폴더에 대해 권한 검토가 필요하지만, 수동 확인으로는 수 주가 소요됩니다. 과도한 권한이 방치되면 정보 유출 리스크가 높아집니다.

**Key Visual**: 대량의 폴더 구조와 "수동 감사: 예상 3~4주"의 오버레이

### Section 2: Workflow Trigger(0:45–1:30)

**내레이션 요지**:
> 감사 대상 볼륨을 지정하고, 권한 감사 워크플로를 시작합니다.

**Key Visual**: Step Functions 실행 화면, 대상 경로 지정

### Section 3: ACL Analysis(1:30–2:30)

**내레이션 요지**:
> 각 폴더의 NTFS ACL을 자동 수집하고, 다음 규칙으로 위반을 검출합니다:
> - Everyone / Authenticated Users에 대한 과도한 권한
> - 불필요한 상속의 축적
> - 퇴직자 계정의 잔존

**Key Visual**: 병렬 처리에 의한 ACL 스캔 진행 상황

### Section 4: Results Review(2:30–3:45)

**내레이션 요지**:
> 검출 결과를 SQL로 쿼리합니다. 위반 건수, 리스크 레벨별 분포를 확인합니다.

**Key Visual**: Athena 쿼리 결과 — 위반 목록 테이블

### Section 5: Compliance Report(3:45–5:00)

**내레이션 요지**:
> AI가 감사 보고서를 자동 생성합니다. 리스크 평가, 권장 대응, 우선순위가 부여된 액션을 제시합니다.

**Key Visual**: 생성된 감사 보고서(리스크 요약 + 대응 권장)

---

## Screen Capture Plan

| # | 화면 | 섹션 |
|---|------|-----------|
| 1 | 파일 서버의 폴더 구조 | Section 1 |
| 2 | 워크플로 실행 시작 | Section 2 |
| 3 | ACL 스캔 병렬 처리 중 | Section 3 |
| 4 | Athena 위반 검출 쿼리 결과 | Section 4 |
| 5 | AI 생성 감사 보고서 | Section 5 |

---

## Narration Outline

| 섹션 | 시간 | 핵심 메시지 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "수천 개 폴더의 권한 감사를 수동으로 수행하는 것은 비현실적" |
| Trigger | 0:45–1:30 | "대상 볼륨을 지정하여 감사를 시작" |
| Analysis | 1:30–2:30 | "ACL을 자동 수집하고, 정책 위반을 검출" |
| Results | 2:30–3:45 | "위반 건수와 리스크 레벨을 즉시 파악" |
| Report | 3:45–5:00 | "감사 보고서를 자동 생성, 대응 우선순위를 제시" |

---

## Sample Data Requirements

| # | 데이터 | 용도 |
|---|--------|------|
| 1 | 정상 권한 폴더(50+) | 베이스라인 |
| 2 | Everyone 전체 제어 설정(5건) | 고위험 위반 |
| 3 | 퇴직자 계정 잔존(3건) | 중위험 위반 |
| 4 | 과도한 상속 폴더(10건) | 저위험 위반 |

---

## Timeline

### 1주일 이내에 달성 가능

| 작업 | 소요 시간 |
|--------|---------|
| 샘플 ACL 데이터 생성 | 2시간 |
| 워크플로 실행 확인 | 2시간 |
| 화면 캡처 취득 | 2시간 |
| 내레이션 원고 작성 | 2시간 |
| 동영상 편집 | 4시간 |

### Future Enhancements

- Active Directory 연계에 의한 퇴직자 자동 검출
- 실시간 권한 변경 모니터링
- 시정 액션의 자동 실행

---

## Technical Notes

| 컴포넌트 | 역할 |
|--------------|------|
| Step Functions | 워크플로 오케스트레이션 |
| Lambda (ACL Collector) | NTFS ACL 메타데이터 수집 |
| Lambda (Policy Checker) | 정책 위반 규칙 대조 |
| Lambda (Report Generator) | Bedrock에 의한 감사 보고서 생성 |
| Amazon Athena | 위반 데이터의 SQL 분석 |

### 폴백

| 시나리오 | 대응 |
|---------|------|
| ACL 수집 실패 | 사전 취득 완료 데이터를 사용 |
| Bedrock 지연 | 사전 생성 보고서를 표시 |

---

*본 문서는 기술 프레젠테이션용 데모 동영상의 제작 가이드입니다.*

---

## 출력 대상에 대하여: FSxN S3 Access Point (Pattern A)

UC1 legal-compliance는 **Pattern A: Native S3AP Output**으로 분류됩니다
(`docs/output-destination-patterns.md` 참조).

**설계**: 계약 메타데이터, 감사 로그, 요약 보고서는 모두 FSxN S3 Access Point 경유로
원본 계약 데이터와 **동일한 FSx ONTAP 볼륨**에 기록됩니다. 표준 S3 버킷은
생성되지 않습니다("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력 계약 데이터 읽기용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력 쓰기용 S3 AP Alias(입력과 동일해도 가능)

**배포 예시**:
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (기타 필수 파라미터)
```

**SMB/NFS 사용자 관점**:
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # 원본 계약서
  └── summaries/2026/05/                # AI 생성 요약(동일 볼륨 내)
      └── contract_ABC.json
```

AWS 사양상의 제약에 대해서는
[프로젝트 README의 "AWS 사양상의 제약과 회피책" 섹션](../../README.md#aws-仕様上の制約と回避策)
및 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)를 참조하십시오.

---

## 검증 완료된 UI/UX 스크린샷

Phase 7 UC15/16/17과 UC6/11/14의 데모와 동일한 방침으로, **최종 사용자가 일상 업무에서 실제로
보는 UI/UX 화면**을 대상으로 합니다. 기술자용 뷰(Step Functions 그래프, CloudFormation
스택 이벤트 등)는 `docs/verification-results-*.md`에 집약합니다.

### 이 유스케이스의 검증 상태

- ✅ **E2E 실행**: Phase 1-6에서 확인 완료(루트 README 참조)
- 📸 **UI/UX 재촬영**: ✅ 2026-05-10 재배포 검증에서 촬영 완료 (UC1 Step Functions 그래프, Lambda 실행 성공 확인)
- 🔄 **재현 방법**: 본 문서 말미의 "촬영 가이드"를 참조

### 2026-05-10 재배포 검증에서 촬영(UI/UX 중심)

#### UC1 Step Functions Graph view(SUCCEEDED)

![UC1 Step Functions Graph view(SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

Step Functions Graph view는 각 Lambda / Parallel / Map 상태의 실행 상황을
색으로 가시화하는 최종 사용자 최중요 화면입니다.

#### UC1 Step Functions Graph(SUCCEEDED — Phase 8 Theme D/E/N 검증, 2:38:20)

![UC1 Step Functions Graph(SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-succeeded.png)

Phase 8 Theme E (event-driven) + Theme N (observability) 활성화 상태에서 실행.
549 ACL iterations, 3871 events, 2:38:20에 모든 단계 SUCCEEDED.

#### UC1 Step Functions Graph(확대 표시 — 각 단계 상세)

![UC1 Step Functions Graph(확대 표시)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-zoomed.png)

#### UC1 S3 Access Points for FSx ONTAP(콘솔 표시)

![UC1 S3 Access Points for FSx ONTAP](../../docs/screenshots/masked/uc1-demo/s3-access-points-for-fsx.png)

#### UC1 S3 Access Point 상세(개요 뷰)

![UC1 S3 Access Point 상세](../../docs/screenshots/masked/uc1-demo/s3ap-detail-overview.png)

### 기존 스크린샷(Phase 1-6에서 해당분)

#### UC1 CloudFormation 스택 배포 완료(2026-05-02 검증 시)

![UC1 CloudFormation 스택 배포 완료(2026-05-02 검증 시)](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### UC1 Step Functions SUCCEEDED(E2E 실행 성공)

![UC1 Step Functions SUCCEEDED(E2E 실행 성공)](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### 재검증 시 UI/UX 대상 화면(권장 촬영 목록)

- S3 출력 버킷(audit-reports/, acl-audits/, athena-results/ 프리픽스)
- Athena 쿼리 결과(ACL 위반 검출 SQL)
- Bedrock 생성 감사 보고서(컴플라이언스 위반 요약)
- SNS 알림 이메일(감사 알림)

### 촬영 가이드

1. **사전 준비**:
   - `bash scripts/verify_phase7_prerequisites.sh`로 전제 확인(공통 VPC/S3 AP 유무)
   - `UC=legal-compliance bash scripts/package_generic_uc.sh`로 Lambda 패키지
   - `bash scripts/deploy_generic_ucs.sh UC1`로 배포

2. **샘플 데이터 배치**:
   - S3 AP Alias 경유로 `contracts/` 프리픽스에 샘플 파일을 업로드
   - Step Functions `fsxn-legal-compliance-demo-workflow`를 시작(입력 `{}`)

3. **촬영**(CloudShell·터미널은 닫기, 브라우저 우측 상단의 사용자 이름은 검은색 처리):
   - S3 출력 버킷 `fsxn-legal-compliance-demo-output-<account>`의 전체 보기
   - AI/ML 출력 JSON의 미리보기(`build/preview_*.html` 형식을 참고)
   - SNS 이메일 알림(해당하는 경우)

4. **마스크 처리**:
   - `python3 scripts/mask_uc_demos.py legal-compliance-demo`로 자동 마스크
   - `docs/screenshots/MASK_GUIDE.md`에 따라 추가 마스크(필요에 따라)

5. **정리**:
   - `bash scripts/cleanup_generic_ucs.sh UC1`로 삭제
   - VPC Lambda ENI 해제에 15-30분(AWS 사양)

---

## 실행 시간 목안(Phase 8 검증 실적)

UC1의 처리 시간은 ONTAP 볼륨상의 파일 수에 비례합니다.

| 단계 | 처리 내용 | 실측값 (549 파일) |
|---------|---------|---------------------|
| Discovery | ONTAP REST API로 파일 목록 취득 | 8분 |
| AclCollection (Map) | 각 파일의 NTFS ACL 수집 | 2시간 20분 |
| AthenaAnalysis | Glue Data Catalog + Athena 쿼리 | 5분 |
| ReportGeneration | Bedrock Nova Lite로 보고서 생성 | 5분 |
| **합계** | | **2시간 38분** |

### 파일 수별 예상 처리 시간

| 파일 수 | 예상 합계 시간 | 권장 용도 |
|-----------|------------|---------|
| 10 | ~5분 | 빠른 데모 |
| 50 | ~15분 | 표준 데모 |
| 100 | ~30분 | 상세 검증 |
| 500+ | ~2.5시간 | 프로덕션 상당 테스트 |

### 성능 최적화 힌트

- **Map state MaxConcurrency**: 기본값 40 → 100으로 올리면 AclCollection 시간을 단축 가능
- **Lambda 메모리**: Discovery Lambda는 512MB 이상을 권장(VPC ENI 연결 고속화)
- **Lambda 타임아웃**: 대량 파일 환경에서는 900s를 권장(기본값 300s로는 부족)
- **SnapStart**: Python 3.13 + SnapStart로 콜드 스타트를 50-80% 감소 가능

### Phase 8 신기능

- **Event-driven 트리거** (`EnableEventDriven=true`): S3AP에 파일 추가 시 자동 시작
- **CloudWatch Alarms** (`EnableCloudWatchAlarms=true`): SFN 실패 + Lambda 오류의 자동 알림
- **EventBridge 실패 알림**: 실행 실패 시 SNS Topic으로 푸시 알림
