# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/엣지 (벤더 비종속)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 개요

FSx for NetApp ONTAP를 **단일 진실 공급원(마스터)**으로 유지하면서, S3 Access Points(S3 AP) 상의
**배포 승인된 렌디션**을 CDN/엣지 네트워크를 통해 배포 가능하게 하는 **벤더 비종속** 서버리스 패턴입니다.

배포 네트워크별 기술적 실현 가능성 비교(CloudFront / Akamai / Fastly / Cloudflare / Bunny.net /
Google Media CDN 등)는 **[CDN 비교](../docs/cdn-comparison.ko.md)**를 참조하세요.

> 본 패턴은 reference implementation입니다. 배포 벤더 선정, 권리 처리, 지역 제한, 컴플라이언스는 고객 책임입니다.

> **TL;DR(30초)**: ONTAP/NAS 마스터를 옮기지 않고 **승인된 렌디션만** CloudFront 또는 서드파티 CDN으로 배포.
> 검증 리스크가 가장 낮은 `PUBLISH_PUSH`(M3)부터 시작. SigV4 직접 풀(ORIGIN_PULL)은
> [검증 체크리스트](../docs/cdn-origin-verification-checklist.ko.md)로 실측 후 채택.

## 비즈니스 성과와 도입(Outcome / Adoption)

"배포됨"이 아니라 **업무 성과**로 평가합니다.

| 구분 | Outcome / Metric / 측정 방법 |
|---|---|
| Business Outcome | 마스터를 이중 보유하지 않고 엣지 배포 실현(배포용 복제는 승인된 렌디션만) |
| Metric | 배포 레이어로 유출되는 마스터 건수 = 0 / 승인 증적 `unrecorded` 건수 |
| 측정 방법 | publish 매니페스트의 `provenance`와 `skipped`/`published` 집계 |

- **안전한 실험 경계**: `DemoMode=true`로 FSx/외부 CDN 없이 로직 검증.
- **Business Sponsor**: 배포 오너(미디어/배포 기반 팀)를 임명하고 Go/No-Go 승인.
- **Go/No-Go 체크리스트**: `ApprovedPrefix` 외가 대상이 되지 않음 / 승인 증적 기록 / 시청자 토큰이 CDN
  네이티브 메커니즘으로 동작 / ORIGIN_PULL 채택 시 SigV4×alias 실측이 PASS.
- 향후 작업은 "미완성"이 아니라 **에비던스 확장**(TBV → 실측)으로 위치 지음.

## Partner/SI 이용 가이드

- **최초 고객 질문**: "기존 NAS/ONTAP 자산을 복제 없이 엣지 배포에 연결하고 싶은가. 배포는 CloudFront인가,
  기존 계약 CDN(Akamai 등)인가."
- **PoC 산출물**: DemoMode 데모 → 승인된 렌디션의 배포 매니페스트 →(선택) 실기 SigV4 검증 결과.
  [CDN 비교](../docs/cdn-comparison.ko.md)를 고객 대화에 그대로 사용 가능.

## 두 가지 통합 메커니즘

- **ORIGIN_PULL**: 오브젝트 복제 없이, CDN이 SigV4로 S3 AP를 직접 가져오는 전제의 오리진 참조 매니페스트
  생성. CloudFront는 OAC로 네이티브 지원(레퍼런스). 서드파티 CDN의 SigV4 오리진 서명은 **검증 필요**.
- **PUBLISH_PUSH**: 승인된 렌디션을 CDN 측 S3 호환 오브젝트 스토어로 복제. 오리진 인증 문제를 회피하며
  CDN 비종속 — 검증 리스크가 가장 낮은 첫 단계.

## 주요 컴포넌트

| 컴포넌트 | 역할 |
|---|---|
| `functions/publish/handler.py` | 승인된 렌디션을 배포 레이어에 반영하고 배포 매니페스트를 S3 AP에 기록 |
| `functions/delivery_log_sync/handler.py` | CDN 배포 로그를 정규화(IP 마스킹)하고 S3 AP에 기록하여 제작 데이터와 대조 |
| Step Functions | Publish → SNS 알림 |
| CloudFront(옵션) | ORIGIN_PULL의 레퍼런스 배포(OAC + SigV4) |

## 배포

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다).

## 보안 / 거버넌스

- **permission-aware**: 배포 대상은 `ApprovedPrefix` 하위로 한정. ACL 제어 마스터를 직접 배포하지 않음.
- **시청자 인증**: S3 Presigned URL 미지원 → CDN 네이티브 토큰 메커니즘 사용.
- **PII**: 배포 로그 기록 시 클라이언트 IP 마스킹(`RedactClientIp=true`).
- **최소 권한**: 배포 Lambda는 Internet-origin S3 AP 접근을 위해 **VPC 외부**에서 실행.

> **Governance Note**: 배포는 ONTAP 파일 권한을 강제하지 않습니다. 배포 경계는 "승인된 렌디션만 배포"
> 운영 규칙과 승인 증적 기록, 배포 대상의 접근 제어로 담보합니다.

### 책임 분담(RACI / Public Sector 관점)

| 역할 | 책임 |
|---|---|
| Data Owner | 배포 대상 데이터의 분류·소재지·공개 가부의 최종 책임 |
| Approver | `ApprovedPrefix` 배치 승인. 승인 증적(approved-by / approval-id) 부여 |
| Audit Reviewer | publish 매니페스트의 `provenance`와 배포 로그를 정기 검토 |
| Ops Owner | 알람 수신·장애 대응·롤백 실행 |

- AI/자동 판정은 **보조 시그널**이며, 공개 배포 가부는 사람(Data Owner / Approver)이 결정.
- 검증용 데이터는 **비기밀 합성/샘플**을 사용(운영(프로덕션) 개인 데이터를 검증에 전용하지 않음).
- 기술적 검증은 법무·컴플라이언스·프라이버시 평가를 **대체하지 않음**.

## 운영 / Runbook

- **알람**: `EnableCloudWatchAlarms=true`로 Lambda 에러(publish/log-sync)와 Step Functions 실패를 SNS 통지
  (`NotificationEmail`).
- **장애 분류**: publish 에러 → `/aws/lambda/<stack>-publish` 확인. S3 AP 인가(IAM + AP policy + ONTAP ID)와
  외부 스토어 인증(Secrets Manager)을 분리. 외부 push 실패 → `ExternalStoreSecretName`·엔드포인트·버킷 확인.
  배포 경계 의심 → [인시던트 대응 Playbook](../docs/incident-response-playbook.md).
- **롤백**: 배포는 승인된 렌디션의 publish만. 오공개 시 배포 대상(CDN 스토어/Distribution)에서 해당 오브젝트를
  제거하고 `ApprovedPrefix`에서 취하 후 재 publish.
- **외부 스토어 인증**: PUBLISH_PUSH로 Akamai/R2/Fastly 등에 복제 시 AWS 기본 인증은 통용되지 않으므로
  `ExternalStoreSecretName`(Secrets Manager, `{"access_key_id","secret_access_key"}`) 필요.

## 관련 문서

- [CDN/엣지 배포 통합 비교](../docs/cdn-comparison.ko.md)
- [ORIGIN_PULL SigV4 검증 체크리스트](../docs/cdn-origin-verification-checklist.ko.md)(실기 검증 절차)
- [대체 아키텍처 비교](../docs/comparison-alternatives.md)
- [인시던트 대응 Playbook](../docs/incident-response-playbook.md)
