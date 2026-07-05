# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

FSx for ONTAP에 저장된 SAP IDoc 익스포트, HULFT 랜딩 파일, EDI 랜딩 존 파일, 배치 작업 출력을 S3 Access Points를 통해 액세스하여 처리하는 서버리스 패턴입니다.

## Use Cases

> **Scope note**: 이 패턴은 IDoc 익스포트, EDI 파일, HULFT 전송, 감사 추출물, 배치 출력과 같은 SAP/ERP 인접 파일 랜딩 존을 대상으로 합니다. 인증된 SAP 통합 메커니즘이나 트랜잭션 ERP 인터페이스를 대체하기 위한 것이 아닙니다. SAP 인증 스토리지 통합에 대해서는 [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)을 참조하세요.

- **SAP IDoc 익스포트 처리**: IDoc 플랫 파일(ORDERS, INVOIC, DESADV)을 파싱하고 요약합니다
- **HULFT 파일 랜딩**: HULFT/DataSpider가 FSx for ONTAP로 전송한 파일을 처리합니다
- **EDI 인바운드 처리**: 랜딩 존의 EDI X12/EDIFACT 문서를 처리합니다
- **배치 작업 출력**: 메인프레임 배치 작업, JCL 출력 또는 예약된 리포트의 출력을 분석합니다
- **ERP 데이터 추출**: SAP, Oracle EBS 또는 기타 ERP 시스템의 CSV/XML 추출물을 처리합니다

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions Workflow           │ │
│  │  Scheduler   │────▶│                                          │ │
│  │              │     │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Processing│─▶│ Report │ │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda   │  │ Lambda │ │ │
│                       │  └────┬─────┘  └────┬─────┘  └───┬────┘ │ │
│                       └───────┼─────────────┼─────────────┼──────┘ │
│                               │             │             │        │
│                               ▼             ▼             ▼        │
│                       ┌──────────────┐ ┌─────────┐  ┌─────────┐   │
│                       │ FSx for ONTAP│ │ Amazon  │  │  Amazon │   │
│                       │ via S3 AP    │ │ Bedrock │  │   SNS   │   │
│                       │              │ │ (Nova)  │  │         │   │
│                       │ ListObjectsV2│ │Summarize│  │ Email   │   │
│                       │ GetObject    │ │Classify │  │ Notify  │   │
│                       └──────────────┘ └─────────┘  └─────────┘   │
│                                              │                     │
│                                              ▼                     │
│                                        ┌──────────┐                │
│                                        │ S3 Output│                │
│                                        │  Bucket  │                │
│                                        └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

1. **Discovery** — S3 Access Point을 통해 FSx for ONTAP의 파일을 나열하며(`ListObjectsV2`), 프리픽스로 필터링합니다
2. **Processing** — 각 파일에 대해: S3 AP를 통해 콘텐츠를 읽고(`GetObject`), 요약/분류를 위해 Amazon Bedrock으로 전송합니다
3. **Report** — 실행 요약을 생성하고, S3에 기록하며, SNS 알림을 전송합니다

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | FSx for ONTAP 볼륨용 S3 AP 별칭 | (필수) |
| `OntapSecretArn` | ONTAP 자격 증명용 Secrets Manager ARN | (필수) |
| `ScheduleExpression` | 실행 주기 | `rate(1 hour)` |
| `OutputBucketName` | 결과를 저장할 S3 버킷 | (필수) |
| `NotificationEmail` | SNS 알림용 이메일 | (필수) |
| `FilePrefix` | 스캔할 디렉터리 프리픽스 | `idoc-export/` |
| `BedrockModelId` | 요약용 Bedrock 모델 | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 실행당 최대 파일 수 | `100` |

## Deployment

```bash
# 전제 조건: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build
sam deploy --guided --stack-name fsxn-s3ap-sap-erp \
  --parameter-overrides \
    S3AccessPointAlias=my-sap-s3ap-alias \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:my-secret \
    OutputBucketName=my-sap-output-bucket \
    NotificationEmail=ops-team@example.com \
    FilePrefix="idoc-export/" \
    ScheduleExpression="cron(0 */2 * * ? *)"
```

> **주의**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)와 함께 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우에는 `template-deploy.yaml`을 사용하세요(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

문서 유형에 맞게 요약 프롬프트를 사용자 정의하려면 `functions/processing/index.py`를 편집하세요.

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — 엔터프라이즈 패턴 전체 목록
- [Quick Start Guide](../docs/quick-start.md) — 첫 배포 안내
- [Deployment Profiles](../docs/deployment-profiles.md) — 프로덕션 구성 옵션

---

## 비용 견적(월간 개산)

> **참고**: 다음은 ap-northeast-1 리전의 개산이며, 실제 비용은 사용량에 따라 다릅니다. 최신 요금은 [AWS Pricing Calculator](https://calculator.aws/)에서 확인하세요.

### 서버리스 구성 요소(종량 과금)

| 서비스 | 단가 | 예상 사용량 | 월간 개산 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 함수 × 100 files/일 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/일 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/일 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/실행 | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/일 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/월 | ~$0.76 |

### 고정 비용(FSx for ONTAP — 기존 환경 전제)

| 구성 요소 | 월간 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (기존 환경 공유) |
| S3 Access Point | 추가 요금 없음(S3 API 요금만) |

### 합계 개산

| 구성 | 월간 개산 |
|------|---------|
| 최소 구성(일 1회 실행) | ~$5-15 |
| 표준 구성(시간별 실행) | ~$15-50 |
| 대규모 구성(고빈도 + 알람) | ~$50-150 |

> **Governance Caveat**: 비용 견적은 개산이며 보장값이 아닙니다. 실제 청구 금액은 사용 패턴, 데이터 양, 리전에 따라 다릅니다.

---

## 로컬 테스트

### Prerequisites 확인

```bash
# 전제 조건 확인
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 용)
aws sts get-caller-identity  # AWS 자격 증명
```

### sam local invoke

```bash
# 빌드
# 전제 조건: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

# Discovery Lambda 로컬 실행
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 환경 변수 오버라이드 포함
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 유닛 테스트

```bash
python3 -m pytest tests/ -v
```

자세한 내용은 [로컬 테스트 퀵 스타트](../docs/local-testing-quick-start.md)를 참조하세요.

---

## 출력 샘플 (Output Sample)

SAP/ERP 파일 처리 워크플로의 출력 예시:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 15,
    "prefix": "idoc-export/",
    "categories": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3}
  },
  "processing": [
    {
      "key": "idoc-export/ORDERS_20260523_001.idoc",
      "status": "completed",
      "category": "sap_idoc",
      "summary": "수주 IDoc (ORDERS05). 거래처: Sample Corporation, 주문 번호: PO-2026-001, 금액: 2,500,000 JPY",
      "document_type": "ORDERS05",
      "key_fields": ["BELNR", "KUNNR", "NETWR", "WAERK"]
    }
  ],
  "report": {
    "total_files": 15,
    "succeeded": 14,
    "failed": 1,
    "success_rate_pct": 93.3,
    "category_breakdown": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3},
    "report_key": "reports/sap-erp-summary-1716480000.json"
  }
}
```

> **참고**: 위는 샘플 출력이며, 실제 값은 환경과 입력 데이터에 따라 다릅니다. 벤치마크 수치는 sizing reference이며 service limit이 아닙니다.

---

## Governance Note

> 이 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제상의 조언이 아닙니다. 조직은 자격을 갖춘 전문가와 상담해야 합니다.

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP의 호환성 제약, 트러블슈팅, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.
---

## Performance Considerations

- FSx for ONTAP의 처리량 용량은 NFS/SMB/S3AP에서 공유됩니다
- S3 Access Point를 경유하는 레이턴시는 수십 밀리초의 오버헤드가 발생합니다
- 대량 파일 처리 시에는 Step Functions Map state의 MaxConcurrency로 병렬도를 제어하세요
- Lambda 메모리 크기 증가는 네트워크 대역폭 향상에도 기여합니다

> **참고**: 이 패턴의 성능 수치는 sizing reference이며 service limit이 아닙니다. 실제 환경에서의 성능은 FSx for ONTAP 처리량 용량, 네트워크 구성, 동시 실행 워크로드에 따라 다릅니다.
