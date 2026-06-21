# UC18: 통신 / 네트워크 분석 — CDR/네트워크 로그 이상 탐지 및 컴플라이언스 보고서

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | 한국어 | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 엔드투엔드 아키텍처 (입력 → 출력)

---

## 아키텍처 다이어그램

```mermaid
flowchart TB
    subgraph INPUT["📥 입력 — FSx for ONTAP"]
        DATA["통신 데이터<br/>.csv/.asn1/.parquet (CDR 파일)<br/>syslog / SNMP trap (네트워크 장비 로그)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 트리거"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 매일 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 워크플로"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 내 실행<br/>• CDR/syslog 파일 탐지<br/>• 접미사 필터 적용<br/>• Manifest 생성"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• S3 AP를 통해 CDR 조회<br/>• 통화 메타데이터 추출<br/>(발신자 ID, 수신자 ID, 통화 시간, 타임스탬프, 기지국 ID)<br/>• Athena 트래픽 통계 쿼리<br/>(시간대별 통화량, 평균 통화 시간, 최대 동시 통화 수)"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Syslog RFC 5424 파싱<br/>• SNMP trap 분석<br/>• 장비 장애 탐지<br/>(link-down, 하드웨어 오류, 프로세스 크래시)<br/>• 용량 임계값 초과 탐지 (기본값 80%)"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• 7일 롤링 기준선 비교<br/>• 3σ 임계값 이상 플래그 지정<br/>• 이상 스코어링"]
        RL["5️⃣ Report Lambda<br/>• 일별 네트워크 상태 요약 생성<br/>• 이상 알림 보고서 생성<br/>• S3 출력 (reports/daily/{YYYY-MM-DD}/)<br/>• SNS 알림<br/>• CloudWatch EMF 메트릭"]
    end

    subgraph OUTPUT["📤 출력 — S3 버킷"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>CDR 트래픽 통계"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>장비 장애 분석 결과"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>이상 탐지 결과"]
        ERROUT["errors/cdr/{filename}.json<br/>CDR 파싱 오류 기록"]
    end

    subgraph NOTIFY["📧 알림"]
        SNS["Amazon SNS<br/>이메일 / Slack<br/>(중대 이상 및 장비 장애 알림)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## 주요 설계 결정

1. **CDR과 syslog의 병렬 처리** — CDR 분석과 로그 분석은 독립적으로 실행 가능. Step Functions Map State로 병렬화하여 처리량 향상
2. **대규모 CDR 집계를 위한 Athena** — 서버리스 SQL로 대량 CDR 레코드를 효율적으로 집계
3. **7일 롤링 기준선** — 요일 특성을 고려한 통계적 이상 탐지
4. **3σ 임계값 이상 플래그** — 통계적으로 유의미한 이상만 탐지. 오탐을 최소화
5. **오류 격리** — CDR 파싱 실패는 `errors/cdr/`에 기록하고 전체 배치를 중단하지 않음
6. **폴링 기반** — S3 AP는 이벤트 알림을 지원하지 않으므로 EventBridge Scheduler로 일별 실행

---

## 사용 AWS 서비스

| 서비스 | 역할 |
|--------|------|
| FSx for ONTAP | CDR/네트워크 로그 스토리지 |
| S3 Access Points | ONTAP 볼륨에 대한 서버리스 접근 |
| EventBridge Scheduler | 일별 트리거 (00:00 UTC) |
| Step Functions | 워크플로 오케스트레이션 (병렬 Map State) |
| Lambda | 컴퓨팅 (Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report) |
| Amazon Athena | CDR 트래픽 통계 SQL 쿼리 |
| Amazon Bedrock | 이상 탐지 추론 (Claude / Nova) |
| SNS | 중대 이상 및 장비 장애 알림 |
| Secrets Manager | ONTAP REST API 인증 정보 관리 |
| CloudWatch + X-Ray | 관측성 (EMF 메트릭, 트레이싱) |
