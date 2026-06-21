# UC20: 여행 및 호스피탈리티 — 예약 문서 처리 / 시설 점검 이미지 분석

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **문서**: [아키텍처](docs/architecture.ko.md) | [데모 가이드](docs/demo-guide.ko.md)

## 개요

FSx for ONTAP S3 Access Points를 활용하여 호텔/여관의 예약 문서(PDF, 스캔 이미지)에서 구조화된 데이터를 자동 추출하고, 시설 점검 이미지의 상태 분석 및 유지보수 권장 사항을 자동 생성하는 서버리스 워크플로우입니다.

### 주요 기능

- S3 AP를 통한 예약 문서 및 시설 점검 이미지 자동 감지
- Textract + Comprehend를 이용한 예약 데이터 구조화 추출 (투숙객명, 날짜, 객실 유형, 금액)
- 다국어 지원 (언어 감지 → Textract 힌트 + Comprehend 모델 자동 선택)
- Rekognition을 이용한 시설 상태 분석 (손상 감지, 청결도 점수 0–100)
- Bedrock을 이용한 유지보수 권장 사항 생성

## Success Metrics

### 성과 지표
| 지표 | 목표값 |
|------|--------|
| 예약 데이터 추출 정확도 | ≥ 90% |
| 시설 상태 감지율 | ≥ 85% |
| 다국어 지원 범위 | ≥ 5개 언어 |
| 리포트 생성 시간 | < 5분 / 배치 |
| Human Review 필요율 | > 15% |

### 측정 방법
Step Functions 실행 이력, Textract/Comprehend 추출 결과, Rekognition 분석 로그, CloudWatch EMF Metrics.

### Human Review 요구사항
- 시설 손상 감지 시 시설 관리팀이 확인 및 대응 판단
- 추출 정확도가 낮은 문서는 수동 확인

## 거버넌스 노트

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다.

## ⚠️ 성능 고려사항

- FSx for ONTAP의 처리량 용량은 **NFS/SMB/S3 AP에서 공유**됩니다. MapConcurrency=10으로 병렬 처리 시 동일 볼륨의 다른 워크로드에 영향을 줄 수 있습니다.
- 대량 파일 일괄 처리 시 FSx for ONTAP의 Throughput Capacity (MBps)를 확인하고 MapConcurrency를 조정하세요.
- 권장: 프로덕션 환경에서는 MapConcurrency=5로 시작하고 CloudWatch 메트릭 (ThroughputUtilization)을 모니터링하면서 점진적으로 증가시키세요.

> **S3 AP NetworkOrigin 참고**: Discovery Lambda는 VPC 내에 배포됩니다. S3 Access Point의 NetworkOrigin이 `Internet`인 경우 S3 Gateway VPC Endpoint를 통해 액세스할 수 없습니다 (FSx 데이터 플레인으로 라우팅되지 않음). VPC-origin S3 AP를 사용하거나 NAT Gateway 액세스를 구성하세요. [S3AP 호환성 참고](../docs/s3ap-compatibility-notes.md)를 참조하세요.

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
