# UC19: 광고·마케팅 / 크리에이티브 자산 관리 — 자산 카탈로그화 및 브랜드 준수 검사

🌐 **Language / 언어**: [日本語](architecture.md) | [English](architecture.en.md) | 한국어 | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 엔드투엔드 아키텍처 (입력 → 출력)

---

## 아키텍처 다이어그램

```mermaid
flowchart TB
    subgraph INPUT["📥 입력 — FSx for ONTAP"]
        DATA["크리에이티브 자산<br/>.jpeg/.png/.tiff (이미지)<br/>.mp4/.mov (동영상)<br/>.psd (디자인 파일)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 트리거"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 매일 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 워크플로우"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 내 실행<br/>• 미디어 파일 감지<br/>• 포맷 + 크기 필터(5 GB 제한)<br/>• Manifest 생성"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• S3 AP 경유 자산 취득<br/>• Rekognition DetectLabels(80% 신뢰도 임계값)<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• 최대 50 태그/자산 생성"]
        TC["3️⃣ Text Compliance Lambda<br/>• Textract 텍스트 추출(us-east-1 크로스리전)<br/>• 브랜드 용어 가이드라인 JSON 로드<br/>• Bedrock InvokeModel — 브랜드 준수 검사<br/>• 결과: compliant / non-compliant + 매칭 용어 목록"]
        RL["4️⃣ Report Lambda<br/>• 자산 카탈로그 생성(JSON + CSV)<br/>• 모더레이션 위반 플래그 지정(requires-review)<br/>• CloudWatch EMF Metrics 전송<br/>• SNS 알림"]
    end

    subgraph OUTPUT["📤 출력 — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json"]
        CSV["reports/{execution-id}/asset-catalog.csv"]
        FLAGGED["reports/{execution-id}/flagged-assets.json"]
        ERROUT["errors/{execution-id}/{filename}.json"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    RL --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
```

---

## 사용 AWS 서비스

| 서비스 | 역할 |
|--------|------|
| FSx for ONTAP | 크리에이티브 자산 스토리지 |
| S3 Access Points | ONTAP 볼륨에 대한 서버리스 액세스 |
| EventBridge Scheduler | 일일 트리거(00:00 UTC) |
| Step Functions | 워크플로우 오케스트레이션(병렬 Map State) |
| Lambda | 컴퓨팅(Discovery, Visual Analyzer, Text Compliance, Report) |
| Amazon Rekognition | 비주얼 분석(라벨, 모더레이션, 텍스트 감지) |
| Amazon Textract | 텍스트 오버레이 추출(us-east-1 크로스리전) |
| Amazon Bedrock | 브랜드 가이드라인 준수 검사 추론(Claude / Nova) |
| SNS | 모더레이션 위반 알림 통지 |
| CloudWatch + X-Ray | 관측성(EMF Metrics, 트레이싱) |
