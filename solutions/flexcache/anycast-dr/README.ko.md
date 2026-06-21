# FlexCache AnyCast / DR 패턴

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

ONTAP FlexCache AnyCast 및 DR(재해 복구) 구성을 FSx for ONTAP × S3 Access Points × AWS Serverless 서비스와 결합하여 구현하기 위한 설계 가이드, 시뮬레이션 데모, 운영 설계 문서를 제공하는 패턴입니다.

## 해결하는 문제

| 문제 | FlexCache AnyCast / DR 솔루션 |
|------|-------------------------------|
| 지리적으로 분산된 팀의 읽기 성능 | 가장 가까운 FlexCache에서 핫 데이터 제공 |
| EDA/미디어/HPC 클라우드 버스팅 | 온프레미스 Origin + 클라우드 FlexCache로 WAN 전송 감소 |
| DR 시 읽기 연속성 | Origin 장애 시에도 캐시 기반 읽기 지속 |
| WAN 전송량 감소 | 핫 데이터만 캐시, 델타 전송 |
| 클라이언트 마운트 구성 복잡성 | AnyCast IP를 통한 단일 마운트 포인트 |

## 아키텍처 개요

```
Control Plane (AnyCast/VIP 제어):
  Health Check Lambda → Route Decision Lambda → Route 53 / DNS

Data Plane (S3 AP 서버리스 처리):
  EventBridge Scheduler → Step Functions → Discovery → Processing → Report

Storage Layer:
  Origin Volume → FlexCache A (Region/AZ A) → S3 AP A
                → FlexCache B (Region/AZ B) → S3 AP B
```

## 주요 설계 결정

- **시뮬레이션 모드**: 실제 FlexCache 인프라 없이 데모/테스트 실행 가능
- **헬스 체크**: Lambda 기반 FlexCache 볼륨 상태 모니터링
- **라우트 결정**: DNS 기반으로 가장 가까운 정상 FlexCache로 라우팅
- **S3 AP 통합**: 서버리스 처리가 가장 가까운 S3 AP에서 읽기

## 성공 지표

| 지표 | 목표 |
|------|------|
| 장애 감지 시간 | < 30초 |
| DNS 전파 시간 | < 60초 |
| 장애 조치 중 읽기 연속성 | > 99.9% |
| 캐시 히트율 (핫 데이터) | > 80% |
| WAN 전송 감소율 | > 60% |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다. 조직은 적격한 전문가에게 상담하십시오.
