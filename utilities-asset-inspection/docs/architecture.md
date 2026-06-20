# UC25: 電力・ユーティリティ — ドローン画像点検 / SCADA 異常検知 アーキテクチャ

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["業務データ<br/>FSx for ONTAP ボリューム上のファイル"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 毎日 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内実行<br/>• ファイル検出・分類<br/>• Manifest 生成"]
        PROC["2️⃣ Processing Lambda(s)<br/>• AI/ML サービス呼び出し<br/>• データ抽出・分析<br/>• Rekognition, Athena, Bedrock"]
        RL["3️⃣ Report Lambda<br/>• レポート生成<br/>• CloudWatch EMF Metrics 送信<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        REPORTS["reports/{date}/summary.json<br/>分析結果レポート"]
        ERROUT["errors/{date}/{filename}.json<br/>エラー記録"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email<br/>（アラート通知）"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> PROC
    PROC --> RL
    RL --> REPORTS
    RL --> ERROUT
    RL --> SNS
```

---

## Key Design Decisions

1. **エラー分離** — 1 ファイルの処理失敗が他のファイルの処理を阻害しない
2. **Exponential Backoff** — AI/ML サービスへのリトライは shared/retry_handler.py で統一管理
3. **ポーリングベース** — S3 AP はイベント通知非対応のため EventBridge Scheduler による日次実行
4. **Cross-Region 対応** — 全サービス ap-northeast-1 で利用可能
5. **Idempotency** — 同一ファイルの再処理で重複レコードが生成されない設計

---

## AWS Services Used

| サービス | 役割 |
|---------|------|
| FSx for ONTAP | ファイルストレージ |
| S3 Access Points | ONTAP ボリュームへのサーバーレスアクセス |
| EventBridge Scheduler | 日次トリガー |
| Step Functions | ワークフローオーケストレーション |
| Lambda | コンピュート（Discovery, Defect Detector, SCADA Analyzer, Thermal Analyzer, Report） |
| Amazon Rekognition | AI/ML 処理 |
| Amazon Athena | AI/ML 処理 |
| Amazon Bedrock | AI/ML 処理 |
| SNS | アラート通知 |
| Secrets Manager | ONTAP REST API 認証情報管理 |
| CloudWatch + X-Ray | オブザーバビリティ |
