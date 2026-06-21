# CDN / 엣지 배포 통합 비교 — FSx for ONTAP S3 Access Points에서의 배포

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. 범위

FSx for ONTAP S3 Access Points(S3 AP) 상의 데이터를 CDN/엣지 네트워크를 통해 배포할 때의
**기술적 실현 가능성**을 정리한 참고 자료입니다. 본 문서는 벤더 간 우열 비교, 가격/성능 비교,
마케팅적 주장을 **다루지 않습니다**. 다루는 것은 FSx for ONTAP S3 AP의 제약에 대해 **무엇이 실현 가능하고,
무엇이 불가능하며, 무엇이 검증 필요인가**뿐입니다. 배포 벤더 선정은 본 문서 범위 밖의 요소(고객 계약·SLA·
운영 체계·리전 요건 등)를 포함하여 고객이 판단합니다.

## 1. 배포 설계를 좌우하는 S3 AP 제약

| 제약 | 내용 | 배포에 대한 영향 |
|------|------|----------------|
| Block Public Access 강제(비활성화 불가) | 기본 활성·변경 불가 | 인증 없는 퍼블릭 오리진 불가. 오리진 인증 필수 |
| 오리진 인증은 SigV4(IAM) | IAM / AP 정책으로 평가 | CDN은 오리진 요청에 AWS SigV4 서명 필요 |
| 2단계 인가(AWS + ONTAP) | IAM 후 ONTAP 파일 ID(UNIX UID / Windows AD) | 배포 대상은 ONTAP ID로 읽을 수 있는 범위로 한정 |
| Presigned URL 미지원 | 공식 미지원 | 시청자 토큰 인증에 S3 Presigned URL 사용 불가. CDN 네이티브 토큰 사용 |
| NetworkOrigin(Internet/VPC, 변경 불가) | CDN은 관리형/외부망에서 접근 | CDN 연계에는 **Internet origin** 필요 |
| PutObject 최대 5 GB | 단일 PUT 한도 | 대용량 쓰기는 멀티파트 |

## 2. 통합 메커니즘(벤더 비종속)

- **M1 — 네이티브 SigV4 오리진 풀**: CDN이 SigV4 서명으로 S3 AP를 직접 가져옴. CDN이 SigV4 오리진 서명을
  탑재한 경우 실현 가능. **검증 필요**: S3 AP의 `accesspoint alias` 호스트는 표준 버킷과 다르므로 SigV4
  동작은 실기 검증 필요.
- **M2 — 엣지 컴퓨트 SigV4 서명**: CDN의 엣지 런타임(Workers/Compute/EdgeWorkers)에서 SigV4를 자체 구현.
  네이티브 오리진 서명이 없는 경우에 실현 가능하며, 서명·키 관리를 직접 보유.
- **M3 — CDN 네이티브 S3 호환 스토어로 푸시**: FSx를 마스터로 유지하고, 승인된 렌디션만 CDN 측 오브젝트
  스토어로 복제. 오리진 인증 문제를 회피하며 CDN 비종속. 검증 리스크가 가장 낮은 첫 단계.
- **M4 — 자체 관리 SigV4 서명 프록시**: 서명 중간층(Lambda Function URL / ALB)을 오리진으로 배치. 거의
  모든 CDN에서 동작하나, 프록시가 가용성·스케일 대상이 됨.

> 공통 절대 제약: 시청자 토큰 인증에 S3 Presigned URL을 사용할 수 없음 — CDN 네이티브 토큰 사용.
> 퍼블릭 배포는 NFS/SMB ACL을 경유하지 않으므로 승인된 렌디션만 배포(4절 참조).

## 3. 배포 네트워크별 메커니즘 대응(사실 기반)

○ = 공식 기능 있음 / △ = 조건부·자체 구현 / − = 해당 기능 없음 / TBV = S3 AP 고유의 검증 필요.

| 배포망 | M1 네이티브 SigV4 풀 | M2 엣지 서명 | M3 자사 S3 호환 스토어 | 시청자 토큰 | S3 AP 고유 TBV |
|--------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | (표준 S3로) | CloudFront 서명 URL/Cookie | **실적 있음**(AWS 공식 튜토리얼이 S3 AP + OAC 제시) |
| Akamai | ○ Cloud Access Manager(AWS 서명) | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | AP alias 호스트에서의 서명 TBV |
| Fastly | ○ S3 호환 프라이빗 오리진에 SigV4 | △ Compute | ○ Fastly Object Storage | Fastly 서명 URL | AP alias에서의 SigV4 TBV |
| Cloudflare | −(프록시 자체는 SigV4 미탑재) | ○ Workers로 SigV4 서명 | ○ R2(S3 호환) | Cloudflare 서명 URL | Workers 서명 + AP alias TBV |
| Bunny.net | △ S3 오리진 풀(AWS S3 오리진 유형) | − | ○ Bunny Storage(S3 호환 API, beta) | Pull Zone 토큰 인증 | AP alias에서의 서명 TBV |
| Google Cloud CDN / Media CDN | ○ private S3 호환 오리진 SigV4 인증 | △ Media CDN 라우팅 | (GCS / 임의 S3 호환) | Media CDN 서명 URL/Cookie | 크로스클라우드 egress + AP alias TBV |

### 표에 싣지 않은/주석 처리
- **Azure Front Door / Azure CDN**: 동일 메커니즘(M1/M4) 적용 가능·TBV. 주 대상 외.
- **Gcore**: S3 호환 오브젝트 스토리지 + 스토리지를 오리진으로(M3). 주 대상 외.
- **Edgio(구 Limelight / Edgecast)**: **2025-01-15에 CDN 사업 정지**. 자산 대부분을 Akamai가 취득.
  **가동 중인 선택지가 아님** — 제외.

> 출처는 각 사의 공개 문서(CloudFront OAC, Akamai Cloud Access Manager, Fastly S3 호환 프라이빗 오리진,
> Cloudflare Workers/R2, Bunny Storage, Google Media CDN). 모두 **표준 S3 호환 버킷**에 대한 기술이며,
> FSx for ONTAP S3 AP accesspoint alias에서의 동작은 TBV.

## 4. 보안 고정 요건(메커니즘 공통)

1. 퍼블릭 배포는 NFS/SMB ACL을 우회 — **승인된 렌디션만 배포**. ACL 제어 마스터를 배포 레이어로 직접 흘리지 않음.
2. 마스터(ACL 제어·기밀)와 배포 성과물(퍼블릭/준퍼블릭)을 분리. M3는 이 분리가 구조적으로 자연스러움.
3. 시청자 인증은 CDN 네이티브 토큰 메커니즘(S3 Presigned URL 미사용).
4. 최소 권한 오리진 자격 증명. 엣지에 장기 키를 두지 않고 단기 자격 증명 우선.
5. 배포 로그: FSx로 로그를 기록할 때 시청자 PII 취급을 설계에 포함.
6. **배포 승인 추적**: 어떤 오브젝트를 누가 언제 퍼블릭 배포로 승인했는지 기록. 승인자가 미기록인 오브젝트는
   차단이 아니라 `unrecorded`로 **가시화**.
7. **데이터 소재지 / 지역 제한**: CDN은 글로벌 배포. 리전 외로 나갈 수 없는 데이터는 배포 대상에서 제외하거나
   geo-blocking으로 제어. 승인 프로세스에 소재지 판정을 포함.

### 4.1 에비던스 분류
- **공개 에비던스**: 3절의 각 배포망 기능 — 공개 문서 기반, **시점 의존**, 채택 전 최신 정보로 재확인.
- **검증 필요(본 프로젝트)**: FSx for ONTAP S3 AP accesspoint alias에 대한 각 CDN의 SigV4 오리진 서명 실동작.

## 5. 실현 가능성 요약

| 질문 | 답변 |
|------|------|
| S3 AP를 인증 없는 CDN 오리진으로 공개할 수 있는가 | **불가**(BPA 강제) |
| S3 AP에서 CDN으로 직접 배포할 수 있는가 | **조건부 가능** — SigV4 지원/구현 시 M1/M2. AP alias 서명은 TBV |
| SigV4가 없는 CDN으로도 배포할 수 있는가 | **가능** — M3(푸시) 또는 M4(서명 프록시) |
| 시청자용으로 S3 Presigned URL을 쓸 수 있는가 | **불가** — CDN 네이티브 토큰 사용 |
| 배포 시 ONTAP ACL을 강제할 수 있는가 | **불가** — "승인된 렌디션만 배포" + 추적으로 담보 |
| 검증 리스크가 가장 낮은 첫 단계 | **M3(푸시)** — 오리진 인증 회피, CDN 비종속, DemoMode 친화 |

> **Governance Caveat**: 본 자료는 기술적 참고 정보입니다. 각 사 기능은 갱신되므로 채택 전 최신 공식
> 문서로 재확인하세요. S3 AP accesspoint alias에 대한 SigV4 오리진 서명은 본 프로젝트의 검증 항목(TBV)입니다.
> 배포 벤더 선정은 고객이 판단합니다.
