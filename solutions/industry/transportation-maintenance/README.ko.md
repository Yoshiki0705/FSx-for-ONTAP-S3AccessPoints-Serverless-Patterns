# UC22: 운수 및 철도 — 설비 점검 이미지 분석 / 유지보수 보고서 관리

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP S3 Access Points를 활용하여 철도 인프라 점검 이미지에서 열화 지표를 감지하고, 심각도를 분류하며, 유지보수 우선순위를 자동 생성하는 서버리스 워크플로우입니다. **안전 중요 인프라(교량, 신호 장비, 레일 접합부)에는 더 낮은 감지 임계값과 필수 인간 검토를 적용합니다.**

## Success Metrics

| 지표 | 목표값 |
|------|--------|
| 결함 감지율 (표준) | ≥ 85% |
| 결함 감지율 (안전 중요) | ≥ 95% |
| 심각도 분류 정확도 | ≥ 80% |
| 위음성률 (안전 중요) | < 5% |
| Human Review 비율 | > 30% |

## 거버넌스 노트

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. AI 감지 결과는 최종 판단이 아니며, 자격을 갖춘 엔지니어의 확인이 필수입니다.

## 배포

AWS SAM CLI로 배포합니다 (파라미터는 환경에 맞게 교체하세요):

```bash
# 전제 조건: AWS SAM CLI 필요. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-transport-maintenance \
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

> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다).

## ⚠️ 성능 고려사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP에서 공유**됩니다. MapConcurrency=10으로 병렬 처리 시 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일 일괄 처리 시 FSx for ONTAP의 Throughput Capacity (MBps)를 확인하고 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 MapConcurrency=5로 시작하고 CloudWatch 메트릭 (ThroughputUtilization)을 모니터링하면서 점진적으로 증가시키세요.

> **S3 AP NetworkOrigin 참고**: Discovery Lambda는 VPC 내에 배포됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해 액세스할 수 없습니다 (FSx 데이터 플레인으로 라우팅되지 않음). VPC-origin S3 AP를 사용하거나 NAT Gateway 액세스를 구성하세요. [S3AP 호환성 참고](../docs/s3ap-compatibility-notes.md)를 참조하세요.

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
