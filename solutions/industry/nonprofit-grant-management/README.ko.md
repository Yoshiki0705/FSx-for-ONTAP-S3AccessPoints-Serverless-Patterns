# UC24: 비영리단체 — 보조금 신청 분류 / 성과 매칭

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP의 S3 Access Points를 활용하여 보조금 신청서를 자동으로 분류하고, 신청자 정보와 예산을 추출하며, 활동 보고서에서 성과 지표를 추출하여 원래 보조금 목표와 매칭하는 서버리스 워크플로입니다.

## Success Metrics

### Outcome
문서 처리와 분석을 자동화하여 운영 효율성과 컴플라이언스를 강화합니다.

### Metrics
| 지표 | 목표값(예시) |
|-----------|------------|
| 보조금 신청 분류 정확도 | ≥ 85% |
| 성과 달성도 측정 정확도 | ≥ 80% |
| 신청서 데이터 추출률 | ≥ 90% |
| 보고서 생성 시간 | < 5 분 / 배치 |
| 비용 / 일일 실행 | < $1.50 |
| Human Review 필수 비율 | > 25%(저신뢰도 분류 결과) |

### Measurement Method
Step Functions 실행 기록, AI/ML 서비스 추출 결과, CloudWatch EMF Metrics(ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- 저신뢰도 결과는 수동 확인이 필요합니다
- Critical 알림은 도메인 전문가가 검토합니다
- 정기 요약 보고서는 경영진이 검토합니다

## 아키텍처

자세한 데이터 흐름도는 [아키텍처 문서](docs/architecture.ko.md)를 참조하세요.

## 사전 요구 사항

> **S3 AP NetworkOrigin 주의**: Discovery Lambda는 VPC 내부에 배치됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해 액세스할 수 없습니다(FSx 데이터 플레인으로 라우팅되지 않기 때문). NetworkOrigin=VPC인 S3 AP를 사용하거나 NAT Gateway를 통한 액세스를 구성하세요. 자세한 내용은 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.

- AWS 계정 및 적절한 IAM 권한
- FSx for ONTAP 파일 시스템(ONTAP 9.17.1P4D3 이상)
- S3 Access Point가 활성화된 볼륨
- VPC, 프라이빗 서브넷
- Amazon Bedrock 모델 액세스 활성화(Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1) 호출 구성

## 배포 절차

```bash
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
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

> **참고**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)로 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우 `template-deploy.yaml`을 사용하세요(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

## ⚠️ 성능 관련 고려 사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP 전체에서 공유**됩니다. MapConcurrency=10으로 병렬 처리하는 경우 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일을 일괄 처리하는 경우 FSx for ONTAP의 Throughput Capacity (MBps)를 확인하고 필요에 따라 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 먼저 MapConcurrency=5로 시작하고 FSx for ONTAP의 CloudWatch 메트릭 (ThroughputUtilization)을 모니터링하면서 단계적으로 늘리세요.

## 정리

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## 비용 예상(월간 개략치)

> **참고**: ap-northeast-1 리전 기준 개략치. 실제 비용은 사용량에 따라 다릅니다.

| 구성 | 월간 개략치 |
|------|---------|
| 최소 구성(일 1회) | ~$8-20 |
| 표준 구성 | ~$20-50 |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 보조금 신청에 포함된 개인정보·조직정보의 취급은 각 보조기관의 규정 및 개인정보보호법을 준수하세요.

> **관련 규제**: 일본 NPO법(특정비영리활동촉진법), 공익법인인정법

---

## S3AP Compatibility

FSx for ONTAP S3 AP의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.
