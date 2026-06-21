# FSx for ONTAP 기반 Amazon Quick 에이전트 워크스페이스

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 개요

**Amazon Quick Suite**(에이전트형 AI 워크스페이스)의 데이터 기반으로 Amazon FSx for NetApp ONTAP를 **S3 Access Points 경유**로 활용하는 패턴입니다. 업무 부서가 Windows 파일 조작으로 유지하는 데이터를 Quick의 각 기능(Index / Sight / Flows / Research)에서 횡단 활용합니다.

UC29(매니지드 Bedrock KB 셀프서비스)와 달리, UC30은 **비정형 검색·BI·액션 자동화를 묶은 에이전트형 워크스페이스**에 초점을 둡니다.

> Amazon Quick Suite는 2025년 10월 공개. 기능·요금·리전은 time-sensitive이며 [aws.amazon.com/quick](https://aws.amazon.com/quick/) 참조.

## Quick 기능과 S3 AP 매핑

| Quick 기능 | 데이터(S3 AP) | 구현 |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/` (비정형) | S3 AP 읽기 전용 데이터 소스 |
| Quick Sight (BI) | `analytics/<role>/` (csv) | Glue/Athena (Athena Query Lambda) |
| Quick Flows | `flows/<role>/` (json) | Action API (API Gateway + Lambda + Bedrock) |

## 두 가지 데모 시나리오

| 시나리오 | 개요 |
|---------|------|
| **A: 수동 워크스페이스** | Windows로 데이터 배치, Quick 콘솔에서 Index 연결·Quick Sight 데이터셋·Quick Flows 수동 체험 |
| **B: 자동화** | 데이터 준비·BI 쿼리·액션을 서버리스로 자동화(Data Prep / Athena Query / Action API) |

## 역할 × 서비스 구성

역할은 Amazon Quick 대상(sales, marketing, IT, operations, finance, legal + developers)에 맞춤. 샘플 데이터는 [`sample-data/quick-workspace/`](sample-data/) 참조. UC29와 역할 구성 공유.

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## 보안

- 데이터 이동 없음(FSx for ONTAP 원본 유지, S3 AP 읽기 전용)
- Action API는 IAM 인증(SigV4) — 미인증 공개 엔드포인트 금지
- 최소 권한, 암호화(SSE-FSX/SSE-S3/TLS)
- Quick 본체 데이터 소스 연결은 Quick 콘솔에서 구성

## Governance Note

> 기술 아키텍처 가이던스이며 법적·규제 자문이 아닙니다. Quick 기능·요금은 변경될 수 있어 공식 정보를 확인하세요.
