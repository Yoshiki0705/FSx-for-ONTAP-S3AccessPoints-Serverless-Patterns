# UC29 PoC 前提条件チェックリスト

デプロイ前に確認すること。再利用環境の落とし穴を事前に潰す。

## 環境前提

- [ ] AWS CLI v2 / 認証情報（対象アカウント・リージョン）
- [ ] 対象リージョンで Amazon Bedrock が利用可能
- [ ] 既存または新規の FSx for ONTAP ファイルシステム
- [ ] **S3 Access Point（NetworkOrigin を確認）**
  - Internet origin: ローカル投入・非VPC Lambda 可
  - VPC origin: バインド VPC 内の Lambda + VPC Endpoint が必要
- [ ] S3 AP 経由の List/Get/Put をローカルから疎通確認（`aws s3 ls s3://<alias>/`）

## Bedrock Knowledge Base 前提

- [ ] KB が用意済み、またはスクリプト/コンソールで作成可能
- [ ] **ベクトルストア種別を確認**
  - **S3 Vectors の場合**: フィルタ可能メタデータ **2048 バイト以内**、メタデータファイル 10KB 以内
  - 既存データに大きい `.metadata.json` があると ingestion 失敗の恐れ → **inclusionPrefixes でデモ用プレフィックスに限定**
- [ ] データソースの inclusionPrefixes をデモ対象（例 `ai-knowledge/`）に設定
- [ ] KB データソースの bucketArn が対象 S3 AP エイリアスを指す

## モデル前提

- [ ] 回答生成モデルの提供形態を確認
  - Nova/一部モデルは **オンデマンド不可 → 推論プロファイル**（例 `apac.amazon.nova-pro-v1:0`）
  - IAM に `bedrock:InvokeModel` + `bedrock:GetInferenceProfile`（inference-profile / foundation-model 両 ARN）

## デプロイ

- [ ] `aws cloudformation package` 用の S3 バケット
- [ ] パラメータ: S3AccessPointAlias / Name / KnowledgeBaseId / DataSourceId / IngestionPrefix / BedrockLlmModelId
- [ ] デプロイ後、AutoSync(force) → ingestion COMPLETE → Query を疎通確認

## セキュリティ

- [ ] Lambda 最小権限（S3 AP / KB のみ）
- [ ] CloudTrail + S3 AP アクセス監査が有効
- [ ] 機密データをログ/プロンプト/会話履歴に残さない

> クリーンアップ手順は [UC29/UC30 クリーンアップ runbook](../../docs/uc29-uc30-cleanup-runbook.md) を参照。
