# UC25: 전력·유틸리티 — 드론 이미지 점검 / SCADA 이상 탐지

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP S3 Access Points를 활용하여 송전 설비의 드론 점검 이미지에서 설비 결함을 탐지하고, SCADA 로그의 시계열 이상을 탐지하며, FLIR 열화상의 핫스팟을 분석하는 서버리스 워크플로입니다.

## Success Metrics

### Outcome
문서 처리와 분석을 자동화하여 운영 효율화와 컴플라이언스 강화를 실현합니다.

### Metrics
| 지표 | 목표값(예시) |
|-----------|------------|
| 결함 탐지율 | ≥ 85% |
| SCADA 이상 오탐율 | < 10% |
| 열화상 핫스팟 탐지 정확도 | ≥ 90% |
| 리포트 생성 시간 | < 5분 / 배치 |
| 비용 / 일일 실행 | < $3.00 |
| Human Review 필수율 | > 30%(Critical 심각도 탐지 시 전건 확인) |

### Measurement Method
Step Functions 실행 이력, AI/ML 서비스 추출 결과, CloudWatch EMF Metrics(ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- 낮은 신뢰도 결과는 수동 확인이 필요
- Critical 알림은 도메인 전문가가 검토
- 정기 요약 리포트는 경영진이 검토

## 아키텍처

자세한 데이터 흐름도는 [아키텍처 문서](docs/architecture.ko.md)를 참조하세요.

## 사전 요구 사항

> **S3 AP NetworkOrigin 주의**: Discovery Lambda는 VPC 내부에 배치됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해서는 접근할 수 없습니다(FSx 데이터 플레인으로 라우팅되지 않기 때문). NetworkOrigin=VPC인 S3 AP를 사용하거나 NAT Gateway를 통한 접근을 구성하세요. 자세한 내용은 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.

- AWS 계정과 적절한 IAM 권한
- FSx for ONTAP 파일 시스템(ONTAP 9.17.1P4D3 이상)
- S3 Access Point가 활성화된 볼륨
- VPC, 프라이빗 서브넷
- Amazon Bedrock 모델 액세스 활성화(Claude / Nova)

## 배포 절차

```bash
# 사전 요구: AWS SAM CLI가 필요합니다. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **주의**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)로 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우에는 `template-deploy.yaml`을 사용하세요(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

## ⚠️ 성능 관련 주의 사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP 전체에서 공유**됩니다. MapConcurrency=10으로 병렬 처리를 수행할 경우 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일의 일괄 처리를 수행하는 경우 FSx for ONTAP의 Throughput Capacity(MBps)를 확인하고 필요에 따라 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 처음에 MapConcurrency=5로 시작하고 FSx for ONTAP의 CloudWatch 지표(ThroughputUtilization)를 모니터링하면서 단계적으로 늘리세요.

## 정리

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## 비용 견적(월간 개산)

> **참고**: ap-northeast-1 리전 기준 개산입니다. 실제 비용은 사용량에 따라 달라집니다.

| 구성 | 월간 개산 |
|------|---------|
| 최소 구성(일 1회) | ~$8-20 |
| 표준 구성 | ~$20-50 |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. SCADA 데이터는 중요 인프라 정보입니다. 액세스 권한 관리와 감사 로그 보존은 전기사업법 및 중요 인프라 보호 가이드라인을 준수하세요.

> **관련 규제**: 전기사업법(電気事業法), 전기설비 기술기준(電気設備技術基準)

---

## S3AP Compatibility

FSx for ONTAP S3 Access Points의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.
