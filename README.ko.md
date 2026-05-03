# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Amazon FSx for NetApp ONTAP S3 Access Points를 활용한 업종별 서버리스 자동화 패턴 모음집입니다.

## 개요

이 리포지토리는 FSx for NetApp ONTAP에 저장된 엔터프라이즈 데이터를 **S3 Access Points**를 통해 서버리스로 처리하는 **5가지 업종별 패턴**을 제공합니다.

각 유스케이스는 독립적인 CloudFormation 템플릿으로 구성되어 있으며, 공통 모듈(ONTAP REST API 클라이언트, FSx 헬퍼, S3 AP 헬퍼)은 `shared/`에 있습니다.

### 주요 특징

- **폴링 기반 아키텍처**: EventBridge Scheduler + Step Functions (FSx ONTAP S3 AP는 `GetBucketNotificationConfiguration`을 지원하지 않음)
- **공통 모듈 분리**: OntapClient / FsxHelper / S3ApHelper를 모든 유스케이스에서 재사용
- **CloudFormation 네이티브**: 각 유스케이스가 독립적인 CloudFormation 템플릿
- **보안 우선**: TLS 검증 기본 활성화, 최소 권한 IAM, KMS 암호화
- **비용 최적화**: 고비용 상시 가동 리소스(VPC Endpoints 등)는 선택 사항

## 유스케이스

| # | 디렉토리 | 업종 | 패턴 | AI/ML 서비스 | 리전 호환성 |
|---|----------|------|------|-------------|------------|
| UC1 | `legal-compliance/` | 법무·컴플라이언스 | 파일 서버 감사 및 데이터 거버넌스 | Athena, Bedrock | 전체 리전 |
| UC2 | `financial-idp/` | 금융 서비스 | 계약서·청구서 처리 (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: 크로스 리전 |
| UC3 | `manufacturing-analytics/` | 제조업 | IoT 센서 로그 및 품질 검사 | Athena, Rekognition | 전체 리전 |
| UC4 | `media-vfx/` | 미디어·엔터테인먼트 | VFX 렌더링 파이프라인 | Rekognition, Deadline Cloud | Deadline Cloud 리전 |
| UC5 | `healthcare-dicom/` | 헬스케어 | DICOM 이미지 분류 및 익명화 | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: 크로스 리전 |

> **리전 제약**: Amazon Textract와 Amazon Comprehend Medical은 일부 리전(예: ap-northeast-1)에서 사용할 수 없습니다. `TEXTRACT_REGION` 및 `COMPREHEND_MEDICAL_REGION` 파라미터를 통해 크로스 리전 호출이 지원됩니다. [리전 호환성 매트릭스](docs/region-compatibility.md)를 참조하세요.

## 빠른 시작

### 사전 요구 사항

- AWS CLI v2
- Python 3.12+
- S3 Access Points가 활성화된 FSx for NetApp ONTAP
- AWS Secrets Manager에 저장된 ONTAP 자격 증명

### 배포

> ⚠️ **기존 환경에 대한 영향**
>
> - `EnableS3GatewayEndpoint=true`는 VPC에 S3 Gateway Endpoint를 추가합니다. 이미 존재하는 경우 `false`로 설정하세요.
> - `ScheduleExpression`은 주기적으로 Step Functions를 실행합니다. 즉시 필요하지 않은 경우 배포 후 스케줄을 비활성화하세요.
> - S3 버킷에 객체가 포함된 경우 스택 삭제가 실패할 수 있습니다. 삭제 전에 버킷을 비우세요.
> - VPC Endpoint 삭제에 5-15분이 소요됩니다. Lambda ENI 해제로 인해 Security Group 삭제가 지연될 수 있습니다.
>
> **리전**: AI/ML 서비스의 완전한 가용성을 위해 `us-east-1` 또는 `us-west-2`를 사용하세요. [리전 호환성](docs/region-compatibility.md)을 참조하세요.

```bash
# 리전 설정
export AWS_DEFAULT_REGION=us-east-1

# Lambda 함수 패키징
./scripts/deploy_uc.sh legal-compliance package

# CloudFormation 스택 배포
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ParameterKey=PrivateRouteTableIds,ParameterValue=<your-route-table-ids> \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false
```

## 문서

| 문서 | 설명 |
|------|------|
| [배포 가이드](docs/guides/deployment-guide.md) | 단계별 배포 절차 |
| [운영 가이드](docs/guides/operations-guide.md) | 모니터링 및 운영 절차 |
| [트러블슈팅 가이드](docs/guides/troubleshooting-guide.md) | 일반적인 문제와 해결 방법 |
| [비용 분석](docs/cost-analysis.md) | 비용 구조 및 최적화 |
| [리전 호환성](docs/region-compatibility.md) | 리전별 서비스 가용성 |
| [확장 패턴](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [검증 결과](docs/verification-results.md) | AWS 환경 테스트 결과 |

## 기술 스택

| 계층 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| IaC | CloudFormation (YAML) |
| 컴퓨팅 | AWS Lambda |
| 오케스트레이션 | AWS Step Functions |
| 스케줄링 | Amazon EventBridge Scheduler |
| 스토리지 | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| 보안 | Secrets Manager, KMS, IAM 최소 권한 |
| 테스트 | pytest + Hypothesis (PBT) |

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 참조하세요.
