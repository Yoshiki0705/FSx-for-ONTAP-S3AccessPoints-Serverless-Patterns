# Amazon Quick Suiteのデータ基盤としてFSx for ONTAPをS3アクセスポイントで活用する — エージェント型ワークスペース（UC30）

> ドラフト（レビュー用）。公開前にペルソナレビューボードの指摘を反映する。

## TL;DR

業務部門がWindowsのファイル操作で維持するデータを、**Amazon Quick Suite**（エージェント型AIワークスペース）の Index（検索）・Sight（BI）・Flows（アクション）から横断的に活用するパターン（UC30）。データはFSx for ONTAP上の**正本のまま**、S3 Access Point経由で読み取り、サーバーレス基盤（Athena/Glue + Action API）が支える。

UC29（マネージドBedrock KBへのセルフサービス投入）が「非構造化ナレッジの自助運用」に焦点を当てるのに対し、UC30は **Quick Suiteを入口に、検索・BI・アクション自動化を1つのワークスペースに束ねる**ことに焦点を当てる。

## Quick の各機能とS3 APデータの対応

| Quick 機能 | 役割 | S3 AP上のデータ | 本UCの実装 |
|-----------|------|---------------|-----------|
| Quick Index / Research | 非構造化ファイルの横断検索・調査 | `index/<role>/`（md/pdf） | S3 APをデータソース接続 |
| Quick Sight | 構造化データのBI・可視化 | `analytics/<role>/`（csv） | Glue/Athena経由（Athena Query Lambda） |
| Quick Flows | アクション自動化 | `flows/<role>/`（json） | Action API（API Gateway + Lambda + Bedrock） |

ロール構成はUC29と揃え、sales / marketing / finance / information-technology / operations / legal / developers の7ロール。同じAI専用ボリュームを共有・流用できる。

## アーキテクチャ

業務ユーザーは`quick-workspace/`（SMB共有）へドラッグ&ドロップし、index/analytics/flowsをロール別に整理する。S3 Access Point経由で、Quick Index（非構造化）、Athena/Glue（構造化BI）、Action API（アクション）がそれぞれデータを利用する。

## 実機検証で得た学び

### Lake Formation環境でのAthenaアクセス

検証アカウントはLake Formationがデータカタログを統制していた。Athena Query Lambdaの実行ロールに、Glueテーブルへの**Lake Formation権限付与**（DESCRIBE on DB、SELECT/DESCRIBE on tables）が別途必要だった。本番ではLF-TBAC（タグベースアクセス制御）でロール別データ可視性を設計する。

### Quick × FSxN S3 APの統合境界（実機検証で判明した制約）

Amazon QuickのS3ナレッジベースコネクタはFSxN S3 APエイリアスを「有効なURL」として受理するが、
実機検証では**標準手順での接続認可に失敗**した（`You do not have permissions to access the S3 bucket`）。
FSxNのデュアルレイヤー認証（IAM + ファイルシステムレベル権限）が要因で、データアクセスロールへのIAM付与
だけでは不十分、S3 APリソースポリシーへのprincipal追加も`MalformedPolicy`となった。

検証から得た推奨（エビデンスに基づく結論）:

- **FSxN→RAGの本命**: Bedrock KB（UC29、取り込みCOMPLETE実証済み）が素直で確実
- **Quick Index**: 通常S3バケットへステージングするのが確実
- **Quick Sight（BI）**: Athena経由で接続可（QuickSightロールにAthena/Glue/LF/結果バケット権限が前提）
- AD連携（Windows identity）S3 APでの直接接続は本検証では未達。今後の検証課題（hypothesis）として扱う

### Glueテーブルは別途作成

`analytics/<role>/`のCSVを指すGlueテーブル（`sales_pipeline` / `it_incidents`）はAthena DDLで作成する。LOCATIONはS3 APエイリアスを`s3://<alias>/quick-workspace/analytics/<role>/`形式で指定。大規模時はParquet + パーティション化でscanned課金を削減する。

## セキュリティ設計

- **データ移動なし（ソース）**: ソースファイルはFSx ONTAP上の正本のまま、S3 APは読み取りのみ。
  ただしAthenaの**クエリ結果**は暗号化された結果バケット（30日で失効、TLS強制、パブリックアクセスブロック）に保存される
- **Action APIは認証（IAM/SigV4）+ per-action認可**: 認証なしの公開エンドポイントにしない。
  `ACTION_AUTH_MODE=enforce`時は、認証済み呼び出し元（`requestContext.identity`）を
  状態変更アクションは`AUTHORIZED_PRINCIPALS`、管理アクション（approve）は`ADMIN_PRINCIPALS`に照合し、
  不一致は403。監査フィールド（`requested_by`/`created_by`）は本文ではなく認証済み呼び出し元から設定し、なりすましを防ぐ
- **強制 human-in-the-loop**: 高リスク操作はDynamoDB承認ストアで強制的にゲートする。
  `request_approval`（承認要求を永続化）→ `approve`（管理者が承認）→ `execute_approved`
  （承認済みレコードを検証してから実行）。未承認の`execute_approved`は409で拒否。
  承認ストア未設定時は非強制スタブ（`enforced:false`）にフォールバック
- **プロンプトインジェクション対策**: `generate_brief`は取得コンテキストを非信頼データとして扱い、
  埋め込み指示に従わないsystem境界を設定。ただしLLM境界は単層であり、本番では**Bedrock Guardrailsの有効化を推奨**
  （既定はオフ。`BedrockGuardrailId`で設定）
- **任意SQLの既定無効**: Athena Query Lambdaは既定で許可リストクエリのみ実行（`ALLOW_RAW_SQL=false`）。
  ロール別データ境界はLake Formation（LF-TBAC）で強制する前提
- **最小権限**: Lambdaは対象S3 AP / Athena WorkGroup / Glue DBにスコープ。Bedrockは`nova-*` + 推論プロファイルに付与
  （厳密にモデルを絞る場合はResourceをさらに限定）
- **APIスロットリング**: denial-of-wallet対策にレート/バースト制限を設定

## コスト考慮

> 概算であり保証値ではない。Amazon Quickの料金はtime-sensitive。最新は公式情報を確認すること。

- **Amazon Quick本体**: ユーザー/プラン課金（別立て）。停止は手動（ユーザー/アカウントアクセス取り消し）
- Athena: scanned課金（Parquet化で削減）
- Lambda / API Gateway / Bedrock: サーバーレス従量
- AWS Budgetsで予算アラート（NotificationEmail指定時に作成）

## まとめ

UC30は、Windowsで維持する業務データを、Amazon Quickの検索・BI・アクションへ横断接続し、「質問」から「行動」までを1つのワークスペースで完結させる。データはFSx for ONTAPの正本のまま、S3 Access Pointで読み取り、Athena/GlueとAction APIがサーバーレスに支える。

**リポジトリ**: github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

## Governance Note

本記事は技術アーキテクチャガイダンスであり、法的・コンプライアンス・規制上の助言ではない。Amazon Quickの機能・料金・対応リージョンは変更されるため最新の公式情報を確認すること。S3 APのデータソース境界はボリューム/プレフィックス単位であり、利用者個人ごとの可視範囲制御が必要な場合はQuickの文書レベルACLまたはカスタムRAGを検討すること。
