# Partner/SI 1페이지 요약: FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 언어**: [日本語](partner-si-one-pager.md) | [English](partner-si-one-pager.en.md) | [한국어](partner-si-one-pager.ko.md) | [简体中文](partner-si-one-pager.zh-CN.md)

---

## What — 이 리포지토리가 제공하는 것

| 항목 | 내용 |
|------|------|
| 업종별 유스케이스 | 28 UC (법무, 의료, 제조, 공공 부문 등) |
| FlexCache/FlexClone 패턴 | 6 FC (DR, 렌더링, RAG, CAE, 생명과학, 게임) |
| 템플릿 형식 | CloudFormation (SAM Transform) — 독립 배포 가능 |
| 트리거 모드 | POLLING (기본) / EVENT_DRIVEN (FPolicy) / HYBRID |
| 성숙도 모델 | 4단계 (Sandbox → Scheduled → Monitored → Production) |
| 테스트 | 1,499+ unit/property tests, cfn-lint, ruff validation |

## When — 언제 사용하는가

다음 조건에 해당하는 고객에게 제안 가능:

- ✅ FSx for ONTAP에 파일 데이터를 보유
- ✅ 파일 데이터에 대한 서버리스 자동 처리 필요
- ✅ S3 API 경유 읽기/쓰기 (GetObject, PutObject, ListObjectsV2 등) 필요
- ✅ NTFS ACL / AD SID 기반 접근 제어 필요 (권한 인식 처리)
- ✅ AI/ML (Bedrock, Textract, Comprehend, Rekognition) 활용 희망
- ✅ 이벤트 기반 또는 스케줄 실행으로 파일 처리 자동화 희망

## How — PoC 진행 방법

```
Step 1: 가장 가까운 UC 특정 → Success Metrics 확인
Step 2: 템플릿 배포 → S3AP 접근 검증
Step 3: 고객별 Baseline 측정
Step 4: Go/No-Go 기준으로 평가
```

**소요 시간 목안**:
- Level 1 (Sandbox): 1-2시간
- Level 2 (Scheduled): 1-2일
- Level 3 (Monitored): 1-2주

## Where — 주요 리소스 위치

| 리소스 | 경로 |
|--------|------|
| Success Metrics | 각 UC의 README.md |
| 거버넌스 | [docs/governance-checklist.md](governance-checklist.md) |
| 프로덕션 준비 | [docs/production-readiness.md](production-readiness.md) |
| 벤치마크 | [docs/s3ap-benchmark-results.md](s3ap-benchmark-results.md) |
| 고객 히어링 | [docs/customer-discovery-template.md](customer-discovery-template.md) |
| 비용 시산 | [docs/cost-calculator.md](cost-calculator.md) |
| PoC 판정 | [docs/poc-go-nogo-template.md](poc-go-nogo-template.md) |

---

> **주의**: 본 리포지토리는 "설계 판단을 배우기 위한 레퍼런스 구현"입니다. 프로덕션 환경 적용에는 고객 고유의 보안 리뷰, 컴플라이언스 평가, 성능 검증이 필요합니다.
