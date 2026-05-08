# 기존 환경 영향 평가 가이드

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## 개요

본 문서는 각 Phase의 기능을 활성화할 때 기존 환경에 미치는 영향을 평가하고, 안전한 활성화 절차와 롤백 방법을 제공합니다.

> **대상 범위**: Phase 1–5 (향후 Phase 추가 시 본 문서를 업데이트)

설계 원칙:
- **Phase 1 (UC1–UC5)**: 독립 CloudFormation 스택. VPC/서브넷에 ENI 추가만 영향
- **Phase 2 (UC6–UC14)**: 독립 스택 + 크로스 리전 API 호출
- **Phase 3 (횡단 기능 강화)**: 기존 UC 확장. 모든 기능 옵트인 (기본 비활성화)
- **Phase 4 (프로덕션 SageMaker·멀티 계정·이벤트 기반)**: UC9 확장 + 신규 템플릿. 옵트인
- **Phase 5 (Serverless Inference·비용 최적화·CI/CD·Multi-Region)**: 모든 기능 옵트인 (기본 비활성화)

---

## Phase 1: 기반 UC (UC1–UC5)

| 파라미터 | 기본값 | 활성화 시 영향 |
|---------|--------|-------------|
| VpcId / PrivateSubnetIds | — (필수) | Lambda ENI 생성 |
| EnableS3GatewayEndpoint | "true" | ⚠️ 기존 S3 Gateway EP 충돌 가능 |
| EnableVpcEndpoints | "false" | Interface VPC Endpoints 생성 |
| ScheduleExpression | "rate(1 hour)" | 정기 Step Functions 실행 |
| EnableCloudWatchAlarms | "false" | 신규 알람 생성 (기존 영향 없음) |

## Phase 2: 확장 UC (UC6–UC14)

| 파라미터 | 기본값 | 활성화 시 영향 |
|---------|--------|-------------|
| CrossRegion | "us-east-1" | 크로스 리전 API 호출 (지연 50–200ms) |
| MapConcurrency | 10 | Lambda 동시 실행 할당량에 영향 |

## Phase 3: 횡단 기능 강화

| 파라미터 | 기본값 | 활성화 시 영향 |
|---------|--------|-------------|
| EnableStreamingMode | "false" | UC11 신규 리소스 (기존 폴링 영향 없음) |
| EnableSageMakerTransform | "false" | ⚠️ UC9 워크플로에 SageMaker 경로 추가 |
| EnableXRayTracing | "true" | ⚠️ X-Ray 트레이스 전송 시작 |

## Phase 4: 프로덕션 확장

| 파라미터 | 기본값 | 활성화 시 영향 |
|---------|--------|-------------|
| EnableDynamoDBTokenStore | "false" | 신규 DynamoDB 테이블 생성 |
| EnableRealtimeEndpoint | "false" | ⚠️ 상시 가동 비용 발생 (~$166/월) |
| EnableABTesting | "false" | Multi-Variant Endpoint 구성 |

## Phase 5: Serverless Inference·비용 최적화·CI/CD·Multi-Region

| 파라미터 | 기본값 | 활성화 시 영향 |
|---------|--------|-------------|
| InferenceType | "none" | "serverless"로 변경 시 라우팅 변경 |
| EnableScheduledScaling | "false" | ⚠️ 기존 Endpoint 스케일링 변경 |
| EnableAutoStop | "false" | ⚠️ 유휴 Endpoint 자동 중지 |
| EnableBillingAlarms | "false" | 신규 알람 생성 (기존 영향 없음) |
| EnableMultiRegion | "false" | ⚠️ **불가역** — DynamoDB Global Table 변환 |

---

## 안전한 활성화 순서

| 순서 | 기능 | Phase | 리스크 |
|------|------|-------|--------|
| 1 | UC1 배포 (최소 구성) | 1 | 낮음 |
| 2 | 관측성 (X-Ray + EMF) | 3 | 낮음 |
| 3 | CI/CD 파이프라인 | 5 | 없음 |
| 4 | Kinesis 스트리밍 (UC11) | 3 | 낮음 |
| 5 | SageMaker Batch Transform (UC9) | 3 | 낮음 |
| 6 | Serverless Inference | 5 | 낮음 |
| 7 | Real-time Endpoint | 4 | 중간 ⚠️ |
| 8 | Scheduled Scaling / Auto-Stop | 5 | 중간 ⚠️ |
| 9 | Multi-Account | 4 | 중간 ⚠️ |
| 10 | Multi-Region | 5 | 높음 ⚠️ **불가역** |

---

## 비용 영향 요약

| Phase | 기능 | 기본 상태 | 추가 비용 |
|-------|------|---------|----------|
| 1/2 | VPC Endpoints | 비활성화 | ~$29/월 |
| 3 | Kinesis | 비활성화 | ~$11/샤드/월 |
| 3 | X-Ray | 활성화 | ~$5/백만 트레이스 |
| 4 | Real-time Endpoint | 비활성화 | ⚠️ ~$166/월 |
| 5 | Serverless Inference | 비활성화 | 종량 과금 |
| 5 | Multi-Region | 비활성화 | Global Table 추가 비용 |

---

## 관련 문서

- [비용 구조 분석](cost-analysis.md) | [스트리밍 vs 폴링 가이드](streaming-vs-polling-guide-ko.md)
- [추론 비용 비교](inference-cost-comparison.md) | [비용 최적화 가이드](cost-optimization-guide.md)
- [CI/CD 가이드](ci-cd-guide.md) | [Multi-Region DR](multi-region/disaster-recovery.md)

---

*본 문서는 FSxN S3AP Serverless Patterns의 기존 환경 영향 평가 가이드입니다.*
