# UC26: 부동산 — 부동산 이미지 분석 / 계약서 추출

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP의 S3 Access Points를 활용하여 부동산 이미지에서 특징 추출 및 리스팅 설명문 자동 생성, 임대차 계약서에서 조건 추출, PII 검출을 통한 프라이버시 보호를 수행하는 서버리스 워크플로우입니다.

## Success Metrics

### Outcome
문서 처리 및 분석의 자동화를 통해 운영 효율화와 컴플라이언스 강화를 실현합니다.

### Metrics
| 메트릭 | 목표값(예시) |
|--------|------------|
| 부동산 특징 추출 정확도 | ≥ 85% |
| PII 검출률 | ≥ 95% |
| 계약 조건 추출 정확도 | ≥ 90% |
| 리포트 생성 시간 | < 5분 / 배치 |
| 비용 / 일일 실행 | < $2.50 |
| Human Review 필수 비율 | > 20% (PII 검출 이미지는 전건 확인) |

### Measurement Method
Step Functions 실행 이력, AI/ML 서비스 추출 결과, CloudWatch EMF Metrics(ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- 낮은 신뢰도 결과는 수동 확인이 필요
- Critical 알림은 도메인 전문가가 검토
- 정기 요약 리포트는 경영진이 검토

## 아키텍처

자세한 데이터 플로우 다이어그램은 [아키텍처 문서](docs/architecture.ko.md)를 참조하세요.

## 사전 요구사항

> **S3 AP NetworkOrigin 참고**: Discovery Lambda는 VPC 내에 배포됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해서는 액세스할 수 없습니다(FSx for ONTAP 데이터 플레인으로 라우팅되지 않기 때문). NetworkOrigin=VPC의 S3 AP를 사용하거나 NAT Gateway를 통한 액세스를 구성하세요. 자세한 내용은 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.

- AWS 계정 및 적절한 IAM 권한
- FSx for ONTAP 파일 시스템(ONTAP 9.17.1P4D3 이상)
- S3 Access Point가 활성화된 볼륨
- VPC, 프라이빗 서브넷
- Amazon Bedrock 모델 액세스 활성화(Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1) 호출 설정

## 배포 절차

```bash
# 사전 요구사항: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-real-estate \
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

> **참고**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)에서 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우 `template-deploy.yaml`을 사용하세요(Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다).

## ⚠️ 성능 고려사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP 전체에서 공유**됩니다. MapConcurrency=10으로 병렬 처리하는 경우 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일 일괄 처리 시 FSx for ONTAP의 Throughput Capacity(MBps)를 확인하고 필요에 따라 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 먼저 MapConcurrency=5로 시작하고 FSx for ONTAP의 CloudWatch 메트릭(ThroughputUtilization)을 모니터링하면서 단계적으로 증가시키세요.

## 클린업

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## 비용 견적(월간 개산)

> **비고**: ap-northeast-1 리전 기준 개산입니다. 실제 비용은 사용량에 따라 다릅니다.

| 구성 | 월간 개산 |
|------|---------|
| 최소 구성(일 1회) | ~$8-20 |
| 표준 구성 | ~$20-50 |

---

## Governance Note

> 이 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 임대차 계약서에 포함된 테넌트 정보는 관련 개인정보 보호법에 따라 적절히 관리하세요. 부동산 이미지에 찍히는 개인정보의 취급에는 부동산 거래 관련 규정에도 유의하세요.

> **관련 규제**: 宅地建物取引業法 (부동산 중개업법), 個人情報保護法 (개인정보 보호법)

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP의 호환성 제약, 트러블슈팅, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하세요.
