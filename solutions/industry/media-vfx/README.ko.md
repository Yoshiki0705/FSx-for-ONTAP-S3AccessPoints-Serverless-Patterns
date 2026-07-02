# UC4: 미디어 — VFX 렌더링 파이프라인

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처 다이어그램](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP의 S3 Access Points를 활용하여 VFX 렌더링 작업의 자동 제출, 품질 검사, 승인된 출력의 반환을 수행하는 서버리스 워크플로입니다.

### 이 패턴이 적합한 경우

- VFX / 애니메이션 제작에서 FSx for ONTAP를 렌더링 스토리지로 사용하고 있다
- 렌더링 완료 후의 품질 검사를 자동화하여 수동 검토 부담을 줄이고 싶다
- 품질 검사를 통과한 에셋을 파일 서버에 자동으로 반환하고 싶다(S3 AP PutObject)
- Deadline Cloud와 기존 NAS 스토리지를 통합한 파이프라인을 구축하고 싶다

### 이 패턴이 적합하지 않은 경우

- 렌더링 작업의 즉시 실행(파일 저장 트리거)이 필요하다
- Deadline Cloud 이외의 렌더 팜(온프레미스 Thinkbox Deadline 등)을 사용한다
- 렌더링 출력이 5 GB를 초과한다(S3 AP PutObject의 상한)
- 품질 검사에 자체 화질 평가 모델이 필요하다(Rekognition의 레이블 검출로는 불충분)

### 주요 기능

- S3 AP를 통한 렌더링 대상 에셋 자동 검출
- AWS Deadline Cloud로 렌더링 작업 자동 제출
- Amazon Rekognition에 의한 품질 평가(해상도, 아티팩트, 색상 일관성)
- 품질 통과 시 S3 AP를 통해 FSx for ONTAP에 PutObject, 불합격 시 SNS 알림

## Success Metrics

### Outcome
VFX 에셋의 자동 분류·메타데이터 부여를 통해 에셋 검색 시간을 단축합니다.

### Metrics
| 메트릭 | 목표값(예시) |
|-----------|------------|
| 실행당 처리된 에셋 수 | > 200 files |
| 메타데이터 부여 성공률 | > 95% |
| 에셋 검색 시간 단축 | > 60% |
| 파일당 처리 시간 | < 60 초 |
| 실행당 비용 | < $10 |
| Human Review 대상 비율 | < 10% |

### Measurement Method
Step Functions 실행 이력, Rekognition label count, S3 출력 메타데이터.

## 아키텍처

```mermaid
graph LR
    subgraph "Step Functions 워크플로"
        D[Discovery Lambda<br/>에셋 검출]
        JS[Job Submit Lambda<br/>Deadline Cloud 작업 제출]
        QC[Quality Check Lambda<br/>Rekognition 품질 평가]
    end

    D -->|Manifest| JS
    JS -->|Job Result| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    JS -.->|GetObject| S3AP
    JS -.->|CreateJob| DC[AWS Deadline Cloud]
    QC -.->|DetectLabels| Rekognition[Amazon Rekognition]
    QC -.->|PutObject (통과 시)| S3AP
    QC -.->|Publish (불합격 시)| SNS[SNS Topic]
```

### 워크플로 단계

1. **Discovery**: S3 AP에서 렌더링 대상 에셋을 검출하고 Manifest를 생성
2. **Job Submit**: S3 AP를 통해 에셋을 가져와 AWS Deadline Cloud에 렌더링 작업을 제출
3. **Quality Check**: Rekognition으로 렌더링 결과의 품질을 평가. 통과 시 S3 AP에 PutObject, 불합격 시 SNS 알림으로 재렌더링을 플래그

## 전제 조건

- AWS 계정과 적절한 IAM 권한
- FSx for ONTAP 파일 시스템(ONTAP 9.17.1P4D3 이상)
- S3 Access Point가 활성화된 볼륨
- Secrets Manager에 등록된 ONTAP REST API 자격 증명
- VPC, 프라이빗 서브넷
- 구성이 완료된 AWS Deadline Cloud Farm / Queue
- Amazon Rekognition을 사용할 수 있는 리전

## 배포 절차

### 1. 파라미터 준비

배포 전에 다음 값을 확인하십시오:

- FSx for ONTAP S3 Access Point Alias
- ONTAP 관리 IP 주소
- Secrets Manager 시크릿 이름
- AWS Deadline Cloud Farm ID / Queue ID
- VPC ID, 프라이빗 서브넷 ID

### 2. SAM 배포

```bash
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-media-vfx \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    S3AccessPointOutputAlias=<your-output-volume-ext-s3alias> \
    OntapSecretName=<your-ontap-secret-name> \
    OntapManagementIp=<your-ontap-management-ip> \
    ScheduleExpression="rate(1 hour)" \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    DeadlineFarmId=<your-deadline-farm-id> \
    DeadlineQueueId=<your-deadline-queue-id> \
    QualityThreshold=80.0 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **참고**: `template.yaml`은 SAM CLI(`sam build` + `sam deploy`)로 사용합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하는 경우에는 `template-deploy.yaml`을 사용하십시오(Lambda zip 파일의 사전 패키징과 S3 업로드가 필요합니다).

> **참고**: `<...>` 플레이스홀더를 실제 환경 값으로 교체하십시오.

### 3. SNS 구독 확인

배포 후 지정한 이메일 주소로 SNS 구독 확인 이메일이 전송됩니다.

> **참고**: `S3AccessPointName`을 생략하면 IAM 정책이 Alias 기반만 되어 `AccessDenied` 오류가 발생할 수 있습니다. 프로덕션 환경에서는 지정을 권장합니다. 자세한 내용은 [문제 해결 가이드](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー)를 참조하십시오.

## 구성 파라미터 목록

| 파라미터 | 설명 | 기본값 | 필수 |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx for ONTAP S3 AP Alias(입력용) | — | ✅ |
| `S3AccessPointName` | S3 AP 이름(ARN 기반 IAM 권한 부여용. 생략 시 Alias 기반만) | `""` | ⚠️ 권장 |
| `S3AccessPointOutputAlias` | FSx for ONTAP S3 AP Alias(출력용) | — | ✅ |
| `OntapSecretName` | ONTAP 자격 증명의 Secrets Manager 시크릿 이름 | — | ✅ |
| `OntapManagementIp` | ONTAP 클러스터 관리 IP 주소 | — | ✅ |
| `ScheduleExpression` | EventBridge Scheduler의 스케줄 표현식 | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | 프라이빗 서브넷 ID 목록 | — | ✅ |
| `NotificationEmail` | SNS 알림 대상 이메일 주소 | — | ✅ |
| `DeadlineFarmId` | AWS Deadline Cloud Farm ID | — | ✅ |
| `DeadlineQueueId` | AWS Deadline Cloud Queue ID | — | ✅ |
| `QualityThreshold` | Rekognition 품질 평가 임계값(0.0〜100.0) | `80.0` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints 활성화 | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms 활성화 | `false` | |

## 비용 구조

### 요청 기반(종량 과금)

| 서비스 | 과금 단위 | 개산(100 에셋/월) |
|---------|---------|----------------------|
| Lambda | 요청 수 + 실행 시간 | ~$0.01 |
| Step Functions | 상태 전이 수 | 무료 범위 내 |
| S3 API | 요청 수 | ~$0.01 |
| Rekognition | 이미지 수 | ~$0.10 |
| Deadline Cloud | 렌더링 시간 | 별도 견적※ |

※ AWS Deadline Cloud의 비용은 렌더링 작업의 규모·시간에 따라 달라집니다.

### 상시 가동(선택 사항)

| 서비스 | 파라미터 | 월액 |
|---------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints=true` | ~$28.80 |
| CloudWatch Alarms | `EnableCloudWatchAlarms=true` | ~$0.20 |

> 데모/PoC 환경에서는 변동비만으로 **~$0.12/월**(Deadline Cloud 제외)부터 이용할 수 있습니다.

## 정리

```bash
# CloudFormation 스택 삭제
aws cloudformation delete-stack \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1

# 삭제 완료 대기
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1
```

> **참고**: S3 버킷에 오브젝트가 남아 있으면 스택 삭제가 실패할 수 있습니다. 사전에 버킷을 비우십시오.

## Supported Regions

UC4는 다음 서비스를 사용합니다:

| 서비스 | 리전 제약 |
|---------|-------------|
| Amazon Rekognition | 거의 모든 리전에서 사용 가능 |
| AWS Deadline Cloud | 지원 리전이 제한적([Deadline Cloud 지원 리전](https://docs.aws.amazon.com/general/latest/gr/deadline-cloud.html)) |
| AWS X-Ray | 거의 모든 리전에서 사용 가능 |
| CloudWatch EMF | 거의 모든 리전에서 사용 가능 |

> 자세한 내용은 [리전 호환성 매트릭스](../docs/region-compatibility.md)를 참조하십시오.

## 참고 링크

### AWS 공식 문서

- [FSx for ONTAP S3 Access Points 개요](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [CloudFront로 스트리밍(공식 튜토리얼)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html)
- [Lambda로 서버리스 처리(공식 튜토리얼)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Deadline Cloud API 레퍼런스](https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html)
- [Rekognition DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html)

### AWS 블로그 기사

- [S3 AP 발표 블로그](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
- [3가지 서버리스 아키텍처 패턴](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### GitHub 샘플

- [aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing](https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing) — Rekognition 대규모 처리
- [aws-samples/dotnet-serverless-imagerecognition](https://github.com/aws-samples/dotnet-serverless-imagerecognition) — Step Functions + Rekognition
- [aws-samples/serverless-patterns](https://github.com/aws-samples/serverless-patterns) — 서버리스 패턴 모음

### 프로젝트 내 가이드

- [FlexClone 서버리스 패턴(일본어)](../docs/guides/flexclone-serverless-patterns.md) — FlexClone + Step Functions + S3AP에 의한 연속 프레임 처리 파이프라인, 멀티프로토콜 마운트, 산업별 유스케이스
- [FlexClone Serverless Patterns (English)](../docs/guides/flexclone-serverless-patterns-en.md) — FlexClone + Step Functions + S3AP sequential frame processing pipeline

## 검증된 환경

| 항목 | 값 |
|------|-----|
| AWS 리전 | ap-northeast-1 (도쿄) |
| FSx for ONTAP 버전 | ONTAP 9.17.1P4D3 |
| FSx 구성 | SINGLE_AZ_1 |
| Python | 3.12 |
| 배포 방식 | CloudFormation (표준) |

## Lambda VPC 배치 아키텍처

검증에서 얻은 지견을 바탕으로 Lambda 함수는 VPC 내/외로 분리 배치되어 있습니다.

**VPC 내 Lambda**(ONTAP REST API 액세스가 필요한 함수만):
- Discovery Lambda — S3 AP + ONTAP API

**VPC 외 Lambda**(AWS 관리형 서비스 API만 사용):
- 그 외 모든 Lambda 함수

> **이유**: VPC 내 Lambda에서 AWS 관리형 서비스 API(Athena, Bedrock, Textract 등)에 액세스하려면 Interface VPC Endpoint가 필요합니다(각 $7.20/월). VPC 외 Lambda는 인터넷을 통해 AWS API에 직접 액세스할 수 있으며 추가 비용 없이 동작합니다.

> **참고**: ONTAP REST API를 사용하는 UC(UC1 법무·컴플라이언스)에서는 `EnableVpcEndpoints=true`가 필수입니다. Secrets Manager VPC Endpoint를 통해 ONTAP 자격 증명을 가져오기 때문입니다.

## FlexCache 렌더링 고속화 확장

### 개요

VFX 렌더링 워크플로에서 render input assets(텍스처, 지오메트리, 플레이트)는 읽기 중심이며 FlexCache의 최적 적용 대상입니다. 작업 시작 시 FlexCache를 동적으로 생성하고 렌더링 완료 후 자동 삭제함으로써 비용 최적화와 성능 개선을 양립할 수 있습니다.

### 렌더링 데이터 분류

| 데이터 종류 | 액세스 패턴 | FlexCache 적용 | S3 AP 이용 |
|-----------|---------------|:---:|:---:|
| Textures | 읽기 전용 | ✅ | ⚠️ 바이너리 |
| Geometry/Plates | 읽기 전용 | ✅ | ⚠️ 바이너리 |
| Scene Files | 읽기 전용 | ✅ | ❌ |
| Render Output (EXR/PNG) | 쓰기 | ❌ | ✅ QC/메타데이터 |
| Logs | 쓰기 → 읽기 | ❌ | ✅ 분석 |
| Cache (sim/fluid) | 읽기 쓰기 | ❌ | ❌ |

### Dynamic FlexCache Render Workflow

작업 단위로 FlexCache를 생성·삭제하는 워크플로의 자세한 내용은 다음을 참조하십시오:

- **[Dynamic FlexCache Render/EDA Workflow](../dynamic-flexcache-render-workflow/README.md)** — Step Functions에 의한 자동화
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md) — 멀티 리전 렌더 팜
- [산업·워크로드 매핑](../docs/industry-workload-mapping.md) — Pattern E: Media/VFX Render Farm

### 기대되는 효과

| KPI | FlexCache 없음 | FlexCache 있음 | 개선율 |
|-----|--------------|---------------|--------|
| 렌더링 시작 대기 | 10-20분 | 2-5분 | 75% |
| 프레임당 시간 | 15분 | 10분 | 33% |
| WAN 전송량/작업 | 500GB | 50GB | 90% |
| 비용/프레임 | $0.50 | $0.35 | 30% |

---

## AWS 문서 링크

| 서비스 | 문서 |
|---------|------------|
| FSx for ONTAP | [FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon CloudFront | [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) |
| Amazon Bedrock | [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework 대응

| 기둥 | 대응 |
|----|------|
| 운영 우수성 | X-Ray 트레이싱, EMF 메트릭, 작업 상태 모니터링 |
| 보안 | 최소 권한 IAM, CloudFront OAC, KMS 암호화 |
| 신뢰성 | Step Functions Retry/Catch, 품질 검사 게이트 |
| 성능 효율 | CloudFront CDN 전송, Lambda 병렬 처리 |
| 비용 최적화 | 서버리스, CloudFront 캐시 활용 |
| 지속 가능성 | 온디맨드 실행, CDN에 의한 오리진 부하 경감 |

---

## 로컬 테스트

### Prerequisites 체크

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
# 전제: AWS SAM CLI가 필요합니다. sam build가 코드와 공유 레이어를 자동으로 패키징합니다.
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

자세한 내용은 [로컬 테스트 퀵 스타트](../docs/local-testing-quick-start.md)를 참조하십시오.

---

## 출력 샘플 (Output Sample)

VFX 렌더링 품질 검사의 출력 예시:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 48,
    "prefix": "renders/shot-042/"
  },
  "quality_check": [
    {
      "key": "renders/shot-042/frame-0001.exr",
      "resolution": "4096x2160",
      "color_space": "ACEScg",
      "quality_score": 0.94,
      "issues": [],
      "cloudfront_url": "https://d1234.cloudfront.net/delivery/shot-042/frame-0001.exr"
    }
  ],
  "delivery": {
    "total_frames": 48,
    "passed_qc": 46,
    "failed_qc": 2,
    "cloudfront_distribution": "d1234.cloudfront.net"
  }
}
```

> **참고**: 위는 샘플 출력이며 실제 값은 환경·입력 데이터에 따라 달라집니다. 벤치마크 수치는 sizing reference이며 service limit이 아닙니다.

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적·컴플라이언스·규제상의 조언이 아닙니다. 조직은 적격한 전문가와 상담하십시오.

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP의 호환성 제약, 문제 해결, 트리거 패턴에 대해서는 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)를 참조하십시오.
