# UC27: 인사·HR — 이력서 스크리닝 / PII 엄격 모드

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP의 S3 Access Points를 활용하여 이력서·경력기술서에서 스킬·경험을 구조화 추출하고, PII 엄격 모드로 보호 특성을 제외한 스코어링을 수행하는 서버리스 워크플로입니다.

> **중요: 규제상의 주의 사항**
> 본 패턴은 **문서 트리아지 및 요약 워크플로**이며, 자동 채용 결정 시스템이 아닙니다. 최종 채용 결정은 반드시 자격을 갖춘 인사 담당자가 내려야 합니다. 사용 전에 각 국가·지역의 노동법, 개인정보 규제(GDPR, APPI, CCPA 등), 차별 금지 요건에 대한 적합성을 검증해야 합니다. 출력에는 보호 특성에 의한 순위 지정을 포함하지 않으며, 평가 설명은 직무 관련 자격·경험만을 근거로 합니다.

## Success Metrics

### Outcome
문서 처리와 분석의 자동화를 통해 운영 효율화와 컴플라이언스 강화를 실현합니다.

### Metrics
| 메트릭 | 목표값(예시) |
|-----------|------------|
| 이력서 데이터 추출률 | ≥ 90% |
| 스코어링 공정성 | 보호 특성 편향 없음(연령·성별·국적 제외) |
| PII 컴플라이언스 | 100%(로그에 PII 출력 제로) |
| 리포트 생성 시간 | < 5분 / 배치 |
| 비용 / 일간 실행 | < $2.00 |
| Human Review 필수율 | > 30%(모든 스코어링 결과를 인사 팀이 확인) |

### Measurement Method
Step Functions 실행 이력, AI/ML 서비스 추출 결과, CloudWatch EMF Metrics(ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- 낮은 신뢰도 결과는 수동 확인이 필요
- Critical 알림은 도메인 전문가가 검토
- 정기 요약 리포트는 경영진이 검토

### Output Safeguard Requirements
- 출력 스키마에 age/gender/ethnicity/nationality 필드를 포함하지 않을 것
- 평가 설명은 직무 관련 자격·경험만을 근거로 할 것
- 검출된 보호 특성은 저장 전에 제거될 것
- 모든 추천 결과는 인간 검토를 필수로 할 것

## 아키텍처

자세한 데이터 플로 다이어그램은 [아키텍처 문서](docs/architecture.ko.md)를 참조하십시오.

## 전제 조건

> **S3 AP NetworkOrigin 주의**: Discovery Lambda는 VPC 내에 배치됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint 경유로는 접근할 수 없습니다(FSx 데이터 플레인으로 라우팅되지 않기 때문). NetworkOrigin=VPC의 S3 AP를 사용하거나 NAT Gateway 경유 접근을 구성하십시오. 자세한 내용은 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하십시오.

- AWS 계정과 적절한 IAM 권한
- FSx for ONTAP 파일 시스템(ONTAP 9.17.1P4D3 이상)
- S3 Access Point가 활성화된 볼륨
- VPC, 프라이빗 서브넷
- Amazon Bedrock 모델 액세스 활성화(Claude / Nova)
- Amazon Textract — Cross-Region(us-east-1) 호출 구성

## 배포 절차

```bash
# 사전 요구 사항: AWS SAM CLI가 필요합니다. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
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
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우에는 `template-deploy.yaml`을 사용하십시오(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

## ⚠️ 성능 관련 주의 사항

- FSx for ONTAP의 스루풋 용량은 **NFS/SMB/S3 AP 전체에서 공유**됩니다. MapConcurrency=10으로 병렬 처리를 수행하는 경우 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일의 일괄 처리를 수행하는 경우 FSx for ONTAP의 Throughput Capacity(MBps)를 확인하고 필요에 따라 MapConcurrency를 조정하십시오.
- 권장: 프로덕션 환경에서는 처음에 MapConcurrency=5로 시작하고 FSx for ONTAP의 CloudWatch 메트릭(ThroughputUtilization)을 모니터링하면서 단계적으로 증가시키십시오.

## 정리

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## 비용 예상(월간 개산)

> **비고**: ap-northeast-1 리전의 개산. 실제 비용은 사용량에 따라 다릅니다.

| 구성 | 월간 개산 |
|------|---------|
| 최소 구성(일간 1회) | ~$8-20 |
| 표준 구성 | ~$20-50 |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 채용 선발에서의 AI 활용은 직업안정법 및 남녀고용기회균등법을 준수하고, 보호 특성(연령, 성별, 국적 등)에 의한 편향을 배제해야 합니다. AI 스코어링은 참고 정보이며, 최종 판단은 인사 담당자가 내려야 합니다.

> **관련 규제**: 직업안정법, 개인정보보호법, 노동기준법

---

## S3AP Compatibility

FSx for ONTAP S3 Access Points의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하십시오.
