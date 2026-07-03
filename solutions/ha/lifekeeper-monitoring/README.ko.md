# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 개요

**SIOS LifeKeeper**로 구성된 고가용성(HA) 클러스터의 로그와 페일오버 이벤트를 **Amazon FSx for NetApp ONTAP**의 S3 Access Points를 통해 비침투적으로 수집, 분석하는 서버리스 패턴입니다.

Amazon Bedrock(Nova Pro)을 활용한 **근본 원인 분석(Root Cause Analysis)**과 **클러스터 헬스 스코어링**을 통해 페일오버의 신속한 원인 규명과 예후 감지를 실현합니다.

---

## 상정 시나리오

엔터프라이즈 환경에서 SAP, Oracle, 기간 업무 애플리케이션을 SIOS LifeKeeper로 HA 보호하고, 공유 스토리지로 FSx for ONTAP Multi-AZ를 사용하고 있습니다.

**과제**:
- 페일오버 발생 시 근본 원인 규명에 시간이 걸린다
- LifeKeeper 로그 분석은 수작업이 많고 특정 담당자에게 의존적이다
- HA 클러스터 노드에 모니터링 에이전트를 추가하면 장애점이 늘어난다
- 스토리지 계층(FSx for ONTAP)과 애플리케이션 계층(LifeKeeper)의 장애 구분이 어렵다

**해결책**:
FSx for ONTAP S3 Access Points를 사용하여 LifeKeeper가 기록하는 로그를 **비침투적으로** 서버리스 분석 파이프라인에서 처리합니다. AI 기반 자동 분석으로 운영 부담을 줄입니다.

---

## SIOS LifeKeeper + FSx for ONTAP 조합

### 아키텍처상의 위치

| 계층 | 담당 | HA 제공 범위 |
|---------|------|------------|
| 스토리지 | FSx for ONTAP Multi-AZ | 데이터 가용성, AZ 이중화, 자동 페일오버 |
| 애플리케이션 | SIOS LifeKeeper | VIP 제어, 서비스 모니터링, 자동 복구 |
| 분석(본 패턴) | S3 AP + 서버리스 + Bedrock | 비침투형 로그 분석, AI 근본 원인 분석 |

### SIOS LifeKeeper란

SIOS Technology사가 제공하는 Linux/Windows용 HA 클러스터링 소프트웨어입니다. AWS 상에서 미션 크리티컬 애플리케이션의 고가용성을 실현합니다.

**주요 특징**:
- 애플리케이션 인식형 Recovery Kit(SAP S/4HANA, Oracle, NFS, IP 등을 직접 모니터링)
- 크로스 AZ 페일오버(단일 리전 내 2 AZ)
- VIP 관리(Elastic IP / Secondary IP)
- 통신 경로 이중화를 통한 스플릿 브레인 방지
- AWS Partner Solution으로 공식 제공

**실적**: Astro Malaysia사가 SAP + Oracle on AWS 환경에서 SIOS LifeKeeper를 채택하여 99.99%의 가용성을 실현했습니다.

### FSx for ONTAP 공유 디스크 지원 (V10 이후)

LifeKeeper V10.0.1 이후, FSx for ONTAP를 공유 디스크로 직접 보호할 수 있게 되었습니다. 기존에는 DataKeeper(블록 복제)만 가능했지만, 공유 디스크 구성이 추가되어 더 단순한 HA 구성이 가능해졌습니다.

| 프로토콜 | 필요한 Recovery Kit | 비고 |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | AWS 상의 FSx for ONTAP 이용 시 필수 |
| NFS | NAS Recovery Kit | 표준적인 NFS 공유 디스크 구성 |

> SIOS bcblog의 검증 기사(2026-05-08)에서는 RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) 구성에서 스위치오버가 정상적으로 동작함이 확인되었습니다.

### FSx for ONTAP가 제공하는 가치

- **Multi-AZ 공유 스토리지**: LifeKeeper의 양쪽 노드에서 NFS/iSCSI로 접근 가능
- **자동 스토리지 페일오버**: 스토리지 계층의 AZ 장애를 자동으로 처리
- **Snapshot**: 페일오버 전후의 데이터 상태를 보전
- **S3 Access Points**: 로그 분석을 위한 비침투적 데이터 접근 경로
- **멀티프로토콜**: SMB + NFS + iSCSI + S3 API를 단일 볼륨에서 제공하여 데이터 이중 보관을 회피
- **클라우드 네이티브**: AWS Management Console에서 직접 이용 시작 가능(별도 라이선스 불필요)

> "데이터를 S3에 복사하여 이용하는 것이 아니라, FSx for ONTAP 상의 데이터를 그대로 S3 API를 통해 활용할 수 있는 점이 큰 장점" — [SIOS bcblog 인터뷰 기사](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/)에서 (Content was rephrased for compliance with licensing restrictions)

### 공개 참고 자료

| 자료 | 발행처 | URL |
|------|--------|-----|
| SIOS LifeKeeper와 Amazon FSx for NetApp ONTAP를 활용한 고가용성 솔루션 | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| NetApp ONTAP와 LifeKeeper를 통한 고가용성 설계 | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Amazon FSx for NetApp ONTAP를 LifeKeeper의 공유 디스크로 이용 | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## 기능

### Discovery Lambda
- FSx for ONTAP S3 AP를 통해 LifeKeeper 로그 파일을 검출
- 페일오버 이벤트 / 헬스 체크 / 구성 변경 / Recovery Kit 로그로 분류
- 중요도(CRITICAL / HIGH / MEDIUM / LOW)를 자동 평가

### Processing Lambda
- LifeKeeper 리소스 상태 전이를 검출(ISP→OSF, ISS→ISP 등)
- Bedrock(Nova Pro)을 통한 근본 원인 분석
- 클러스터 헬스 스코어 산출(0-100점)
- 스토리지 계층 vs 애플리케이션 계층의 장애 구분

### Report Lambda
- Markdown 헬스 리포트 생성
- 중요도 임계값에 기반한 SNS 페일오버 알림
- LifeKeeper 명령(`lcdstatus`, 통신 경로 확인)의 권장 조치 포함

---

## 배포

### 사전 요구 사항

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP 파일 시스템 + S3 Access Point(DemoMode=true인 경우 불필요)
- Bedrock 모델 액세스 활성화(Amazon Nova Pro)

### 빠른 배포

```bash
# DemoMode로 배포 (FSx for ONTAP 불필요)
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **주의**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)로 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우에는 `template-deploy.yaml`을 사용하세요(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

### 프로덕션 배포

```bash
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### 파라미터

| 파라미터 | 기본값 | 설명 |
|-----------|-----------|------|
| S3AccessPointAlias | (필수) | FSx for ONTAP S3 AP 별칭 |
| DemoMode | false | 데모 모드 활성화 |
| ScheduleExpression | rate(5 minutes) | 모니터링 간격 |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | amazon.nova-pro-v1:0 | 분석용 Bedrock 모델 |
| FailoverAlertSeverity | CRITICAL | SNS 알림 최소 중요도 |
| ClusterName | lifekeeper-cluster | LifeKeeper 클러스터 이름 |
| OutputDestination | STANDARD_S3 | 리포트 출력 대상 |
| LogRetentionInDays | 90 | CloudWatch Logs 보존 기간 |

---

## 테스트

```bash
# 유닛 테스트
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# DemoMode에서의 엔드투엔드 테스트
# (사전에 데모용 S3 버킷에 샘플 로그를 배치)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## 헬스 스코어

| 스코어 | 레벨 | 의미 | 권장 조치 |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | 정상 | 정기 리포트 확인 |
| 70-89 | WARNING | 주의 | 통신 경로, 스토리지 I/O 확인 |
| 50-69 | DEGRADED | 저하 | LifeKeeper GUI/CLI로 상태 확인, FSx for ONTAP 모니터링 |
| 0-49 | CRITICAL | 위험 | 즉시 대응. `lcdstatus` + ONTAP 관리 CLI로 상태 확인 |

---

## 디렉터리 구성

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM 템플릿
├── samconfig.toml.example     # 배포 설정 예시
├── README.md                  # 본 문서 (일본어)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper 로그 검출
│   ├── processing/
│   │   └── handler.py         # Bedrock 근본 원인 분석
│   └── report/
│       └── handler.py         # 리포트 생성, 알림
├── statemachine/
│   └── workflow.asl.json      # Step Functions 정의
├── docs/
│   ├── architecture.md        # 아키텍처 상세
│   └── demo-guide.md          # 데모 가이드 (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # 유닛 테스트
```

---

## 관련 패턴

| 패턴 | 관련성 |
|---------|--------|
| `solutions/sap/erp-adjacent/` | LifeKeeper로 보호된 SAP 환경의 IDoc/배치 처리 |
| `solutions/event-driven/fpolicy/` | FPolicy 이벤트 구동을 통한 즉시 로그 감지 |
| `solutions/flexcache/anycast-dr/` | 멀티 리전 DR 구성의 참고 |

---

## Governance Note

본 패턴은 HA 클러스터의 **운영 모니터링 보조**를 목적으로 하며, 다음 사항에 유의합니다:

- AI에 의한 분석 결과는 운영 판단의 **참고 정보**이며, 자동 페일오버 제어나 복구 조작은 수행하지 않습니다
- LifeKeeper 구성 변경은 반드시 LifeKeeper GUI/CLI에서 수행해야 합니다
- 페일오버 판단은 LifeKeeper 자체의 헬스 체크 메커니즘에 위임해야 합니다
- 본 패턴은 **Human-in-the-loop**를 전제로 한 설계입니다

---

## Performance Considerations

- **모니터링 간격**: 5분 간격에서는 최대 5분의 감지 지연이 발생합니다. 즉시성이 필요한 경우 `TriggerMode=HYBRID`로 FPolicy 이벤트 구동을 병용하세요
- **로그 크기**: 대량의 로그 파일이 있는 경우 `MaxFilesPerExecution`으로 배치 크기를 제어하세요
- **Bedrock 비용**: 페일오버가 빈번한 환경에서는 Bedrock 호출 비용에 주의하세요. `FailoverAlertSeverity`로 분석 대상을 좁힙니다
- **S3 AP 처리량**: FSx for ONTAP S3 AP는 파일 시스템 전체의 대역폭을 공유합니다. 대량의 로그 읽기가 업무 I/O에 영향을 주지 않도록 Snapshot 기반 읽기도 검토하세요

---

## License

MIT
