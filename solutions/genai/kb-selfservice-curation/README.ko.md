# 셀프서비스 지식 베이스 큐레이션

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 개요

업무 부서 구성원이 **익숙한 Windows 탐색기의 드래그 앤 드롭만으로** Amazon Bedrock Knowledge Base 데이터 소스를 유지할 수 있게 하는 패턴입니다.

FSx for ONTAP에 **AI 전용 볼륨/폴더**를 만들어 SMB로 각 역할·부서에 공개하고, 동일한 데이터를 **S3 Access Points(읽기 경로)**로 Amazon Bedrock Knowledge Base 데이터 소스에 연결합니다. 파일 변경을 감지하여 **자동으로 수집(Ingestion)**합니다.

이를 통해 IT 부서가 요청별로 수작업 ETL/복사/수집을 수행하던 운영에서, **현장이 스스로 지식을 유지하는 민주화된 운영**으로 전환합니다.

## Before / After

> **참고**: 고객명·개인명·팀명을 마스킹한 일반화된 운영 스토리입니다.

- **Before**: 업무 부서 요청 → IT가 EC2 Windows Server에서 수동 복사 → S3 업로드 → Bedrock KB 수동 수집. 요청마다 병목, 데이터 이중 관리, 속인화.
- **After**: "AI에 사용할 데이터는 이 Windows 폴더에 두고 직접 관리하세요." 사용자는 평소처럼 드래그 앤 드롭, S3 AP 경유로 KB가 자동 동기화되어 즉시 검색 대상.

## 두 가지 데모 시나리오

동일한 기반에서 운영 성숙도에 따라 2단계를 체험할 수 있습니다. 자세한 내용은 [데모 가이드](docs/demo-guide.md)를 참조하세요.

| 시나리오 | 개요 | 수집 트리거 |
|---------|------|------------|
| **A: 수동 유지보수 체험** | Windows 파일 조작(추가/수정/삭제)으로 AI 데이터 유지, 수집은 사람이 수동(콘솔 "동기화"/CLI) | 수동 |
| **B: 자동화** | A의 수동 동기화를 Lambda + Step Functions + EventBridge로 자동화(감지→수집→완료 대기→알림) | 자동 |

> 업무 사용자의 조작(드래그 앤 드롭)은 두 시나리오에서 동일합니다. 달라지는 것은 수집 이후를 사람이 하는지, 서버리스가 하는지뿐입니다.

## 해결하는 문제

| 문제 | 솔루션 |
|------|--------|
| 지식 업데이트가 IT 수작업 대기 | 현장이 Windows 조작으로 유지, 자동 수집 |
| S3 복사로 인한 데이터 이중 관리 | S3 AP로 FSx for ONTAP 원본을 직접 데이터 소스화 |
| 수집 누락·업데이트 누락 | 파일 변경 감지 후 자동 Ingestion |
| ETL/S3/Bedrock 전문 기술 필요 | Windows 드래그 앤 드롭만 |
| 데이터 소유권 불명확 | 폴더 구성을 역할·부서 단위로 분리 |

## 매니지드 KB vs 커스텀 RAG

본 UC는 **매니지드 Bedrock Knowledge Bases(Pattern C)**를 채택하여 운영 부담을 최소화합니다. 검색 시 파일 단위 권한 필터링이 필요한 경우 커스텀 RAG([FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/), Pattern A)를 선택하세요.

> **배포 전제**: Knowledge Base와 데이터 소스는 [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) 또는 Bedrock 콘솔로 생성하고 ID를 템플릿 파라미터로 전달합니다.

## 보안

- 데이터 이동 없음(FSx for ONTAP 원본 유지, S3 AP는 읽기 전용)
- 쓰기는 SMB/NFS 경유, AI 수집 경로(S3 AP)는 읽기 이용
- 폴더 단위 NTFS ACL로 부서별 쓰기 권한 분리
- S3 AP 데이터 소스 경계는 볼륨/프리픽스 단위(사용자별 가시 범위 제어는 범위 외)

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공하며 법적·규제 자문이 아닙니다. 자격을 갖춘 전문가와 상담하세요.
