# Dynamic FlexCache 렌더 / EDA 워크플로우

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

렌더링/EDA/시뮬레이션 작업 제출 시 REST API를 통해 ONTAP FlexCache 볼륨을 동적으로 생성하고, 작업 완료 후 자동으로 삭제하는 워크플로우입니다. AWS Step Functions를 사용하여 NVIDIA 스타일의 작업별 캐시 관리 패턴을 구현합니다.

## 작업별 FlexCache를 생성하는 이유

| 이유 | 설명 |
|------|------|
| 비용 최적화 | 작업 실행 중에만 스토리지 비용 발생 |
| 데이터 격리 | 프로젝트/작업별 캐시 격리 |
| 보안 | 작업 완료 후 데이터 잔류 없음 |
| 운영 단순성 | 고아 볼륨 축적 방지 |
| 성능 최적화 | 작업에 필요한 데이터만 Prepopulate |

## 아키텍처

```
Job Request → Validate → Create FlexCache → Wait Ready → Prepopulate
    → Submit Job → Monitor Loop → Cleanup FlexCache → Report → Notify
```

## ONTAP REST API 작업

- FlexCache 생성: `POST /api/storage/flexcache/flexcaches`
- FlexCache 삭제: `DELETE /api/storage/flexcache/flexcaches/{uuid}`
- 작업 모니터링: `GET /api/cluster/jobs/{uuid}`
- Prepopulate: `PATCH /api/storage/flexcache/flexcaches/{uuid}`

## 성공 지표

| 지표 | 목표 |
|------|------|
| FlexCache 생성 시간 | < 2분 |
| FlexCache 삭제 시간 | < 1분 |
| 작업 완료율 | > 95% |
| 고아 볼륨 수 | 0 |
| 작업당 비용 (FlexCache 오버헤드) | < $0.50 |

---

## 배포

AWS SAM CLI로 배포합니다 (파라미터는 환경에 맞게 교체하세요):

```bash
# 전제 조건: AWS SAM CLI 필요. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name dynamic-flexcache-workflow-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    OntapManagementIp=10.0.0.1 \
    OntapSecretName=fsxn/ontap-credentials \
    OriginSvmName=svm1 \
    OriginVolumeName=render_assets \
    CacheSvmName=svm1 \
    SimulationMode=true
```

> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다).

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다. 조직은 적격한 전문가에게 상담하십시오.
