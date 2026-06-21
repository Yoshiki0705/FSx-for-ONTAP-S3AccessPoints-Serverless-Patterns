# GenAI RAG — 엔터프라이즈 파일 기반

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

엔터프라이즈 파일 서버(FSx for ONTAP)의 기밀 문서를 S3 Access Points를 통해 Amazon Bedrock / RAG 파이프라인에 **S3로 복사하지 않고** 안전하게 제공하는 패턴입니다. 파일 권한(ACL/NTFS)을 유지하면서 Permission-aware RAG를 구현합니다.

## 해결하는 문제

| 문제 | 솔루션 |
|------|--------|
| 민감한 파일을 S3로 복사하여 발생하는 데이터 확산 | S3 AP를 통한 직접 읽기, 복사 불필요 |
| 파일 권한 손실 | ONTAP REST API로 ACL 검색, RAG 응답 시 필터링 |
| 데이터 최신성 문제 | FlexCache + S3 AP로 최신 데이터 제공 |
| 대규모 파일 서버의 전체 볼륨 처리 | EventBridge Scheduler + 델타 감지로 효율화 |
| AI 처리와 데이터 간의 거리 | FlexCache로 AI 처리 VPC 근처에 데이터 배치 |

## Permission-aware RAG 개념

1. **인덱싱 시**: ONTAP REST API로 각 문서의 ACL/권한 정보를 검색하여 벡터 스토어에 메타데이터로 저장
2. **쿼리 시**: 사용자의 AD SID / 그룹 멤버십에 기반하여 접근 가능한 문서로만 검색 범위 필터링
3. **응답 시**: 필터링된 문서만 Bedrock에 전달하여 답변 생성

## FlexCache의 역할

- AI 처리 환경(Lambda VPC) 근처에 데이터 배치
- 임베딩 처리 시 대량 읽기 가속
- Origin으로의 WAN 전송 감소
- S3 AP를 통한 서버리스 처리 제공

## 보안 설계

- **데이터 이동 없음**: 파일은 FSx for ONTAP에 유지, S3 AP를 통한 읽기 전용
- **권한 보존**: ONTAP REST API로 ACL 검색, RAG 응답 시 필터링
- **암호화**: SSE-FSX(저장), TLS(전송), KMS(출력)
- **최소 권한**: Lambda에 필요한 S3 AP 작업만 허용
- **감사**: CloudTrail + ONTAP 감사 로그

## 성공 지표

| 지표 | 목표 |
|------|------|
| 실행당 청크 처리 파일 수 | > 200 파일 |
| ACL 추출 성공률 | > 95% |
| 임베딩 생성 시간 | < 5분 / 100 파일 |
| Permission-aware 필터링 정확도 | > 99% |
| Human Review 비율 | < 10% (저신뢰도 청크) |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다. 조직은 적격한 전문가에게 상담하십시오.
