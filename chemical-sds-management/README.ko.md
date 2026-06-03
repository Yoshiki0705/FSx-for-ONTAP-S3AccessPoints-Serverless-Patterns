# UC28: 화학 및 소재 — SDS 위험 분류 추출 / GHS 검증

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to extract hazard classifications and handling precautions from Safety Data Sheets (SDS), validate GHS mandatory section completeness, and extract experimental data from laboratory notebook images.

## Success Metrics

| Metric | Target |
|--------|--------|
| GHS section validation completeness | 100% (8 mandatory sections verified) |
| Expired SDS detection rate | 100% |
| Hazard classification extraction accuracy | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.50 |
| Human review required rate | > 25% (all critical priority alerts reviewed) |

## Architecture

See [Architecture Document](docs/architecture.ko.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled
- Amazon Textract — Cross-Region (us-east-1)

> **S3 AP NetworkOrigin 참고**: Discovery Lambda는 VPC 내에 배포됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해 액세스할 수 없습니다 (FSx 데이터 플레인으로 라우팅되지 않음). VPC-origin S3 AP를 사용하거나 NAT Gateway 액세스를 구성하세요. [S3AP 호환성 참고](../docs/s3ap-compatibility-notes.md)를 참조하세요.

## Deployment

```bash
aws cloudformation deploy \
  --template-file chemical-sds-management/template.yaml \
  --stack-name fsxn-chemical-sds \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```


## ⚠️ 성능 고려사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP에서 공유**됩니다. MapConcurrency=10으로 병렬 처리 시 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일 일괄 처리 시 FSx ONTAP의 Throughput Capacity (MBps)를 확인하고 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 MapConcurrency=5로 시작하고 CloudWatch 메트릭 (ThroughputUtilization)을 모니터링하면서 점진적으로 증가시키세요.

## Cleanup

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. Handling of chemical substance information in SDS must comply with applicable chemical management and occupational safety laws. Final GHS classification determinations must be made by qualified chemical safety professionals.

> **Related Regulations**: 化学物質管理促進法 (PRTR Act), 労働安全衛生法 (Industrial Safety and Health Act), 消防法 (Fire Service Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
