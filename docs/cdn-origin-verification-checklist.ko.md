# ORIGIN_PULL SigV4 × S3 AP alias — 실기 검증 체크리스트

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## 목적

[CDN 비교 문서](cdn-comparison.ko.md)에서 **검증 필요(TBV)**로 분류한 항목, 즉
**「각 CDN의 SigV4 오리진 서명이 FSx for ONTAP S3 Access Point의 `accesspoint alias` 호스트에 대해 표준 S3
버킷과 동일하게 작동하는가」**를 실기로 확정하기 위한 재현 가능한 절차입니다.

본 체크리스트는 `content-edge-delivery` UC의 `DeliveryMode=ORIGIN_PULL`(M1/M2) 채택 판단에 사용합니다.
**M3(PUBLISH_PUSH)는 본 검증에 의존하지 않습니다**(오리진 인증을 회피하므로).

> **구별 명시**: 본 검증은 "특정 테스트 환경에서의 실측"입니다. 일반적인 S3 동작이나 각 CDN의 표준 버킷
> 실적을 S3 AP alias에 대한 보장으로 취급하지 마십시오.

---

## 0. 전제 조건

- FSx for ONTAP 파일 시스템과 **Internet-origin** S3 Access Point(VPC-origin은 CDN 불가)
- S3 AP alias(예: `<alias>-ext-s3alias`)와 대상 리전
- **승인된 프리픽스** 하위의 테스트 오브젝트(예: `delivery-approved/test-1mb.bin`)
  - permission-aware 원칙에 따라 ACL 제어 마스터는 검증 대상으로 사용하지 않음
- 오리진 서명용 **최소 권한 IAM 자격 증명**(대상 AP의 `s3:GetObject`만). 가능하면 단기 자격 증명
- 검증 단말(curl 7.75 이상은 `--aws-sigv4` 지원), AWS CLI v2

> **보안**: 검증 중에도 액세스 키를 로그·스크린샷·커밋에 남기지 않음. 값이 아닌 키 이름으로 참조(공개 리포지토리 정책).

---

## 1. 베이스라인 검증(CDN 없음 / 최중요)

CDN을 거치지 않고 **S3 AP alias 호스트가 SigV4를 수용하는가**를 직접 확인. 여기가 모든 CDN 공통의 핵심.

### 1.1 AWS CLI(SDK 서명)

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- 기대: HTTP 200 + 오브젝트 취득 성공.
- 실패 시: IAM / AP 정책 / ONTAP 측 ID(UNIX UID / AD)의 2단계 인가를 분리해 확인.

### 1.2 원시 SigV4(CDN의 오리진 서명 동작 근사)

CDN은 대개 고정 액세스 키로 SigV4 서명하여 오리진을 가져온다. `curl --aws-sigv4`로 동등 동작을 근사:

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **이것이 200이면**: alias 호스트는 표준 버킷과 동일하게 SigV4를 수용 → M1/M4 실현 가능성 높음.
- **실패하면**: alias 고유의 어드레싱 차이가 원인일 수 있음 → 각 CDN의 오리진 설정에서 호스트 형식·리전·
  서비스명(`s3`)·패스 스타일/버추얼 호스트 처리를 개별 검증.
- 임시 자격 증명 사용 시 `-H "x-amz-security-token: $AWS_SESSION_TOKEN"` 추가.

### 1.3 네거티브 확인(사양 재확인)

- 무서명 GET이 **403/AccessDenied**일 것(Block Public Access 강제 확인).
- Presigned URL 사용 불가일 것(생성 불가/미지원) → 시청자 토큰은 CDN 네이티브 메커니즘으로.

---

## 2. CDN별 검증 절차

각 CDN에서 "오리진=S3 AP alias 호스트"를 설정하고, 캐시 미스 시 오리진 페치가 200이 되는지 확인.

### 2.1 Amazon CloudFront(M1 / OAC) — 레퍼런스
- `content-edge-delivery` 템플릿을 `EnableCloudFront=true`로 배포(OAC + `SigningProtocol: sigv4`).
- 검증: `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200.
- 기대: AWS 공식 튜토리얼에 준해 성립(**실적 있음**).

### 2.2 Fastly(M1 / SigV4 네이티브)
- S3 호환 프라이빗 오리진으로 alias 호스트를 설정하고 SigV4 서명(리전·서비스 `s3`) 활성화.
- 검증: Fastly 서비스 경유 GET → 200. alias 버추얼 호스트 형식이 Fastly SigV4 구현에서 올바르게 서명되는지 확인.

### 2.3 Cloudflare(M2 / Workers 서명)
- Worker에서 SigV4를 구현하고 alias 호스트로 서명 페치(R2가 아니라 S3 AP를 직접 오리진화하는 경우).
- 검증: Worker 경유 GET → 200. 서명 대상 헤더·페이로드 해시 처리 확인.

### 2.4 Akamai(M1 / Cloud Access Manager)
- Cloud Access Manager에서 AWS 서명 방식을 설정하고 Origin Characteristics로 alias 호스트 지정.
- 검증: Akamai 프로퍼티 경유 GET → 200. AP alias 호스트에서의 서명 적용 가부 확인.

### 2.5 Bunny.net(M1 / S3 오리진 풀)
- Pull Zone 오리진을 AWS S3 오리진 유형으로 alias 호스트에 설정. 검증: Pull Zone 경유 GET → 200.

### 2.6 Google Cloud CDN / Media CDN(M1 / private S3 origin)
- private S3 호환 오리진 SigV4 인증으로 alias 호스트 설정. 검증: Media CDN 경유 GET → 200. 크로스클라우드 egress 경로도 확인.

---

## 3. 합격/불합격 기준

| 판정 | 조건 |
|------|------|
| **PASS** | 베이스라인 1.2가 200 이고 해당 CDN 경유 캐시 미스 GET이 200. 시청자 토큰이 CDN 네이티브 메커니즘으로 동작 |
| **CONDITIONAL** | CDN 경유는 200이나 추가 설정(패스 스타일 등)이나 제약(특정 헤더)이 필요 |
| **FAIL** | alias 호스트로의 SigV4가 해당 CDN에서 성립하지 않아 회피책(M2 서명 구현/M4 서명 프록시/M3 전환)이 필요 |
| **BLOCKED** | 전제(Internet-origin, IAM, 테스트 오브젝트)가 미정비로 검증 불가 |

---

## 4. 검증 시 보안/거버넌스 확인

- [ ] 테스트 오브젝트는 `delivery-approved/` 하위만(ACL 제어 마스터 미사용)
- [ ] 오리진 서명용 IAM은 대상 AP의 `s3:GetObject` 최소 권한
- [ ] 장기 키를 엣지/설정에 남기지 않음(단기 자격 증명 우선, 검증 후 실효)
- [ ] 액세스 키·alias 실값·계정 ID를 로그/스크린샷/커밋에 남기지 않음
- [ ] 시청자 토큰은 CDN 네이티브 메커니즘 사용(S3 Presigned URL 미사용)
- [ ] 검증으로 생성한 임시 리소스(Distribution, Pull Zone 등) 정리

---

## 5. 결과 기록 테이블(증적)

| CDN | 메커니즘 | 설정 완료 | 1.2 베이스라인 | CDN 경유 GET | 시청자 토큰 | 판정 | 증적(HTTP 상태/헤더/일시) | 검증일 | 담당 롤 |
|-----|-----------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> 기록 주의: alias 실값·계정 ID·IP는 플레이스홀더화(`<alias>-ext-s3alias`, `123456789012`).
> 검증 결과는 "특정 테스트 환경에서의 실측"으로 취급하고 일반 보장으로 기재하지 않음.

---

## 6. 검증 결과 피드백

- 확정된 결과는 [CDN 비교 문서](cdn-comparison.ko.md) 3절 "S3 AP 고유 TBV" 열 / 4.1 "검증 필요" 갱신에 반영(TBV → 실측 결과).
- FAIL인 CDN은 `content-edge-delivery`에서 `DeliveryMode=PUBLISH_PUSH`(M3)를 권장 경로로 함.

## 관련 문서

- [CDN/엣지 배포 통합 비교](cdn-comparison.ko.md)
- [content-edge-delivery UC](../solutions/edge/content-delivery/README.ko.md)
- [S3AP 호환성 노트](s3ap-compatibility-notes.md)
