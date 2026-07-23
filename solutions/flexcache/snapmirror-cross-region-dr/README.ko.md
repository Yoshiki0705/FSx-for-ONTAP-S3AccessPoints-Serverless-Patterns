# SnapMirror Cross-Region DR + S3 Access Points 패턴

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 개요

S3 Access Points를 통해 수집된 데이터를 SnapMirror Asynchronous로 크로스 리전 대상에 복제하고, 대상 볼륨에 새 S3 AP를 자동으로 연결하는 재해 복구 패턴입니다.

정상 운영 시 소스 볼륨의 S3 AP를 통해 데이터가 수집됩니다. DR 이벤트 발생 시 Lambda 함수가 약 3분 내에 페일오버를 오케스트레이션합니다: SnapMirror break → junction path → S3 AP 생성.

## 아키텍처

```mermaid
graph TB
    subgraph "정상 운영 (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>소스]
        SRC_VOL[소스 볼륨<br/>vol_sm_dr_source]
    end
    subgraph "복제"
        SM[SnapMirror Async<br/>스케줄: 5분 간격]
    end
    subgraph "DR 페일오버 (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>대상<br/>(페일오버 시 생성)]
        DST_VOL[대상 볼륨 (DP)<br/>vol_sm_dr_dest]
        SNS[SNS 알림]
        CLIENT[애플리케이션<br/>(새 S3 AP로 전환)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|증분<br/>복제| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## 주요 컴포넌트

| 컴포넌트 | 설명 |
|-----------|------|
| 소스 볼륨 + S3 AP | 데이터 수집 포인트 (Region A). 정상 운영 시 사용 |
| SnapMirror Async | 볼륨 레벨 증분 복제 (RPO = 스케줄 간격) |
| 대상 볼륨 (DP) | 데이터 보호 볼륨 (break 전까지 읽기 전용). FSx API를 통해 생성 (SM-VAL-009) |
| Failover Lambda | 자동화: break → junction → S3 AP 생성. RTO ~3분 |
| SNS Topic | 페일오버 후 새 S3 AP 엔드포인트를 애플리케이션에 통지 |

## RTO / RPO

| 메트릭 | 값 | 비고 |
|--------|:---:|------|
| **RTO** | ~3분 | SnapMirror break (즉시) + junction 전파 (~2분) + S3 AP 생성 (~30초) |
| **RPO** | ≤ SnapMirror 스케줄 | 기본 5분 스케줄. 마지막 전송 이후 데이터 손실 가능 |

## 사전 요구사항

- 서로 다른 리전의 FSx for ONTAP 클러스터 2개
- VPC Peering 및 Cluster/SVM Peering 설정 완료
- `aws fsx create-volume`으로 DP 대상 볼륨 생성 (ONTAP REST API 단독으로는 불가 — SM-VAL-009)
- SnapMirror 관계 초기화 및 `snapmirrored` 상태 확인
- Secrets Manager에 fsxadmin 자격 증명 (양 리전)
- Lambda에서 대상 ONTAP 관리 IP (포트 443)로의 VPC 접근

## 배포

```bash
# 1. 스택 배포 (소스 볼륨, 대상 DP 볼륨, Failover Lambda, SNS 생성)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. 소스 S3 AP + SnapMirror 관계 생성
#    (스택 출력의 PostDeployInstructions 참조)

# 3. 페일오버 테스트 (드라이 런)
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## 페일오버 실행

```bash
# DR 페일오버 트리거
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# 결과 확인
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## 검증

```bash
# 페일오버 후 대상 S3 AP에서 읽기
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## 기술적 제약사항

| 제약사항 | 상세 |
|----------|------|
| SnapMirror Asynchronous 전용 | S3 NAS bucket 볼륨에서 Synchronous 모드는 지원되지 않음 |
| SVM-DR 미지원 | S3 NAS bucket을 포함하는 SVM은 SVM-DR을 차단. 볼륨 레벨 SnapMirror만 가능 |
| FSx API를 통한 DP 볼륨 | SM-VAL-009: ONTAP REST API만으로 생성된 볼륨은 FSx API에서 인식 불가, S3 AP 차단 |
| S3 AP 비전송 | SM-002: S3 AP는 AWS 레이어 리소스. 대상에 새 AP 필요 |
| 클라이언트 애플리케이션 업데이트 | 새 AP는 다른 ARN/alias를 가짐. 애플리케이션 엔드포인트 전환 필요 |
| SnapMirror 스케줄 | FSx for ONTAP 최소: 5분 간격 |

## 정리 (순서 중요 — SM-VAL-011)

```bash
# ⚠️ 고아 리소스 방지를 위해 정확한 순서를 따르세요

# 1. SnapMirror 관계 삭제 (대상 클러스터에서)
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    그 후 소스에서: snapmirror release (ONTAP CLI)

# 2. SVM Peers 삭제 (양 클러스터) — 양측에서 num_records: 0 확인까지 폴링

# 3. Cluster Peers 삭제 (양 클러스터)

# 4. VPC Peering 삭제 (스텝 2 확인 후에만)

# 5. S3 Access Points 분리/삭제 (소스 및 생성된 경우 대상)
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. CloudFormation 스택 삭제
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## 참고 자료

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
