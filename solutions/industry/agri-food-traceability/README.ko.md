# UC21: 농업 및 식품 — 농지 항공 이미지 분석 / 이력추적 문서 관리

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP S3 Access Points를 활용하여 농지 드론/항공 이미지에서 작물 건강 상태를 분석하고, 이력추적 문서의 구조화 데이터 추출 및 로트 분류를 자동화하는 서버리스 워크플로우입니다.

### 주요 기능

- GeoTIFF/JPEG 이미지 자동 감지 (GPS 메타데이터, 최대 500MB)
- Rekognition + Bedrock 식생 지수 분석 및 이상 분류 (신뢰도 ≥ 0.70)
- Textract + Comprehend 이력추적 문서 추출 (분류 신뢰도 ≥ 0.80)

## Success Metrics

| 지표 | 목표값 |
|------|--------|
| 작물 이상 감지 정확도 | ≥ 70% confidence |
| 이력추적 분류율 | ≥ 80% confidence |
| 위치 정보 검증률 | ≥ 90% |

## 거버넌스 노트

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다.

## ⚠️ 성능 고려사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP에서 공유**됩니다. MapConcurrency=10으로 병렬 처리 시 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일 일괄 처리 시 FSx for ONTAP의 Throughput Capacity (MBps)를 확인하고 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 MapConcurrency=5로 시작하고 CloudWatch 메트릭 (ThroughputUtilization)을 모니터링하면서 점진적으로 증가시키세요.

> **S3 AP NetworkOrigin 참고**: Discovery Lambda는 VPC 내에 배포됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해 액세스할 수 없습니다 (FSx 데이터 플레인으로 라우팅되지 않음). VPC-origin S3 AP를 사용하거나 NAT Gateway 액세스를 구성하세요. [S3AP 호환성 참고](../docs/s3ap-compatibility-notes.md)를 참조하세요.

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
