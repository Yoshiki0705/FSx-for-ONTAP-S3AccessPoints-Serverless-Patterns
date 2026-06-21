# UC30: Amazon Quick Agentic Workspace — アーキテクチャ

## 概要

FSx for ONTAP の AI 専用ボリュームを **S3 Access Points** 経由で **Amazon Quick Suite** の
データ基盤として活用する。Quick の3つの利用面（Index/Research、Sight、Flows）に対して、
S3 AP 上のデータを **ロール × サービス** で整理し、サーバーレスな基盤で支える。

## アーキテクチャ図

```
┌──────────────────────────────────────────────────────────────────────────┐
│  業務ユーザー（各ロール）                                                  │
│  ┌──────────────────┐  Windows ドラッグ&ドロップ                          │
│  └────────┬─────────┘                                                      │
│           ▼ SMB                                                            │
│  ┌──────────────────────────────────────────────┐                         │
│  │ FSx for ONTAP : quick-workspace/              │                         │
│  │   index/<role>/  analytics/<role>/  flows/<role>/                       │
│  └────────┬─────────────────────────────────────┘                         │
│           ▼ 読み取りパス                                                   │
│  ┌──────────────────┐                                                      │
│  │ S3 Access Point  │                                                      │
│  └───┬───────┬───────┬───────────────────────────┐                        │
│      │       │       │                            │                        │
│      ▼       ▼       ▼                            ▼                        │
│  ┌────────┐ ┌──────────┐ ┌───────────────┐  ┌──────────────┐              │
│  │Data    │ │Glue +    │ │ Quick Index / │  │ Quick Flows  │              │
│  │Prep    │ │Athena    │ │ Research      │  │ (HTTP action)│              │
│  │Lambda  │ │(Athena   │ │ (非構造化)    │  └──────┬───────┘              │
│  └────────┘ │ Query L) │ └───────────────┘         │                      │
│             └────┬─────┘                            ▼                      │
│                  ▼                          ┌──────────────┐               │
│            ┌───────────┐                    │ Action API   │               │
│            │Quick Sight│                    │ APIGW+Lambda │               │
│            │ (BI)      │                    │ + Bedrock    │               │
│            └───────────┘                    └──────┬───────┘               │
│                                                    ▼                       │
│                                              ┌──────────┐                  │
│                                              │   SNS    │                  │
│                                              └──────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

## コンポーネント

| コンポーネント | 役割 |
|--------------|------|
| FSx for ONTAP quick-workspace ボリューム | SMB 共有。index/analytics/flows をロール別に保持 |
| S3 Access Point | Quick / 基盤からの読み取りパス |
| Data Prep Lambda | S3 AP を走査し、サービス×ロールのマニフェストを生成 |
| Glue Database + Athena WorkGroup | 構造化 CSV のカタログ・クエリ基盤（Quick Sight 用） |
| Athena Query Lambda | 構造化データを Athena で問い合わせ、BI 回答を返す |
| Action API（API Gateway + Lambda） | Quick Flows が呼ぶアクション（要約生成・タスク起票、Bedrock） |
| Quick データソースロール | Amazon Quick が S3 AP を読むための IAM ロール（信頼プリンシパルはパラメータ） |
| SNS | アクション・通知 |

## Quick 機能とデータの対応

| Quick 機能 | S3 AP データ | 基盤 |
|-----------|-------------|------|
| Quick Index / Research | `index/<role>/`（md/pdf/docx） | S3 AP 直接接続（Quick コンソールで設定） |
| Quick Sight（BI） | `analytics/<role>/`（csv） | Glue テーブル → Athena → Athena Query Lambda |
| Quick Flows | `flows/<role>/`（json 入力例） | Action API（IAM 認証） |

## データフロー

```
[投入] 業務ユーザー → Windows ドラッグ&ドロップ → quick-workspace/<service>/<role>/
[索引] Quick Index/Research が S3 AP を読み取り（コンソール設定）
[BI]   analytics CSV → Glue テーブル → Athena Query Lambda → Quick Sight
[行動] Quick Flows → Action API（IAM）→ Bedrock 要約 / タスク起票 → SNS
```

## セキュリティ考慮事項

- データは FSx for ONTAP 上の正本のまま、S3 AP は読み取り
- Action API は IAM 認証（SigV4）。認証なしの公開エンドポイントにしない
- Lambda は最小権限（対象 S3 AP / Athena WG / Glue DB / Bedrock モデル）
- Quick データソースロールの信頼プリンシパルは限定する（既定はアカウント root）
- Athena 結果は SSE-S3/KMS、転送は TLS
- S3 AP のデータソース境界はボリューム/プレフィックス単位（利用者個人ごとの可視範囲制御は対象外）
