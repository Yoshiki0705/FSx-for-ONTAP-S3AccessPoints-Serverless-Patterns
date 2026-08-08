# Amplify Portal クリーンアップガイド

🌐 **Language / 言語**: [日本語](cleanup-guide.md) | [English](cleanup-guide.en.md)

このガイドでは、Amplify ポータルおよび関連リソースを安全に削除する手順を説明します。

## 前提

- FSx for ONTAP ファイルシステムは削除しません（既存インフラ）
- CDKToolkit スタックは他プロジェクトと共有するため削除しません
- S3 AP（FSx for ONTAP にアタッチ済み）は別途 `detach-and-delete-s3-access-point` で管理します
  - **順序の制約**: ボリュームを削除する場合、**S3 AP のデタッチ・削除を先に完了させる必要があります**。アタッチされたままボリュームを削除しようとすると BadRequest になります。本ガイドはファイルシステムを削除しないため通常は影響しませんが、ボリューム側まで片付ける場合は順序を守ってください

## 削除で失われるもの（実行前に確認）

以下は**復元手段がありません**。

| 対象 | 失われるもの |
|------|------------|
| DynamoDB テーブル 6 件 | ジョブ実行履歴、お気に入り、最近使ったファイル、ファイルタグ、フォルダ監視設定、通知。ポイントインタイムリカバリを有効にしていない場合、テーブル削除でデータは戻りません。必要なら削除前にエクスポートしてください |
| S3 バケット（`rb --force`） | `--force` はバケットを空にしてから削除します。つまり**中身のオブジェクトも消えます**。「他プロジェクトと共有かどうか」以前に、まず中身を確認してください |
| CloudWatch Logs | ロググループごと消えます。監査目的で残す必要があるなら、削除前に S3 へエクスポートしてください |

> **ポータルのデモで作った ONTAP 側の状態は、このクリーンアップでは消えません。** 特に Tamperproof スナップショット（スナップショットロック）を有効化したり、個別スナップショットに `expiry_time` を設定した場合、それらは**短縮も解除もできません**。SnapLock 監査ログボリュームを作成していた場合は、最短 6 か月間ボリューム・SVM・**ファイルシステム**の削除が連鎖的にブロックされます。該当する操作を試した場合は [Tamperproof スナップショット設計](../../../docs/tamperproof-snapshot-design.md) の事前チェックを確認してください。

## クイックリファレンス

```bash
# === Amplify Sandbox 削除（推奨: 最初にこれ） ===
cd solutions/amplify-portal
npx ampx sandbox delete --yes
# → 約 5-10 分。Cognito, AppSync, DynamoDB, Lambda, S3 すべて削除される

# === プロジェクト関連 CloudFormation スタックの一括削除 ===
./scripts/cleanup_stacks.sh --all-project
# → fsxn- プレフィックスのスタックを対話的に削除

# === 個別スタック削除 ===
aws cloudformation delete-stack --stack-name <stack-name> --region ap-northeast-1

# === スタンドアロン Lambda の削除 ===
aws lambda delete-function --function-name agentcore-mcp-eda-tools --region ap-northeast-1
aws lambda delete-function --function-name fsxn-duckdb-query --region ap-northeast-1

# === 削除完了の確認 ===
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_IN_PROGRESS DELETE_FAILED \
  --query 'StackSummaries[?starts_with(StackName, `fsxn-`) || starts_with(StackName, `amplify-fsxn`)].[StackName,StackStatus]' \
  --output table --region ap-northeast-1
```

## 削除対象と所要時間

| リソース | コマンド | 所要時間 |
|----------|---------|---------|
| Amplify Sandbox | `npx ampx sandbox delete --yes` | 5-10 分 |
| VPC Endpoint スタック | `aws cloudformation delete-stack --stack-name fsxn-syslog-vpce-admin-audit` | 1-2 分 |
| EventBridge + Lambda スタック | `aws cloudformation delete-stack --stack-name fsxn-automated-response` | 2-3 分 |
| AgentCore MCP Lambda | `aws lambda delete-function --function-name agentcore-mcp-eda-tools` | 即座 |
| DELETE_FAILED スタック | `./scripts/cleanup_stacks.sh` (自動修復) | 1-3 分 |

## 手順詳細

### 1. Amplify Sandbox の削除

```bash
cd solutions/amplify-portal
npx ampx sandbox delete --yes
```

これにより以下が削除されます：
- Cognito User Pool + Identity Pool
- AppSync GraphQL API
- DynamoDB テーブル（JobExecution, Favorite, RecentFile, FileTag, FolderWatch, FileNotification）
- Lambda 関数（ListFiles, GetPresignedUrl, AskAboutFile, DetectLabels, Textract, Comprehend, Athena, Glue, SearchFiles, ListSnapshots, QueryAuditLog, etc.）
- S3 バケット（コード生成用、デプロイ用）
- IAM ロール + ポリシー
- CloudWatch Logs ロググループ

> **注意**: DynamoDB テーブルの削除に 3-5 分かかる場合があります。タイムアウトした場合は `aws cloudformation describe-stacks` で進捗を確認してください。
>
> **データは戻りません**: 上記 6 つのテーブルの中身（ジョブ履歴・タグ・監視設定など）はこの時点で失われます。残したいものがあれば、削除前に `aws dynamodb scan` などでエクスポートしてください。

### 2. VPC Endpoint スタックの削除

VPC Interface Endpoint は時間課金（~$7.20/月/個）なので、不要なら早めに削除します。

```bash
aws cloudformation delete-stack --stack-name fsxn-syslog-vpce-admin-audit --region ap-northeast-1
```

### 3. EventBridge + Lambda スタックの削除

EventBridge Schedule が ENABLED の場合、Lambda が定期的に呼び出されます。

```bash
aws cloudformation delete-stack --stack-name fsxn-automated-response --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-ar-ttl-e2e --region ap-northeast-1
```

### 4. スタンドアロン Lambda の削除

CloudFormation スタック外で作成された Lambda：

```bash
aws lambda delete-function --function-name agentcore-mcp-eda-tools --region ap-northeast-1
aws lambda delete-function --function-name fsxn-duckdb-query --region ap-northeast-1
```

### 5. DELETE_FAILED スタックの処理

過去に削除失敗して放置されたスタック（リソース自体は存在しない）：

```bash
# 自動修復（ブロッカー検出 + リトライ）
./scripts/cleanup_stacks.sh

# または FORCE_DELETE_STACK で強制削除
aws cloudformation delete-stack --stack-name <stack-name> --region ap-northeast-1 --deletion-mode FORCE_DELETE_STACK
```

> **`FORCE_DELETE_STACK` の副作用**: CloudFormation が削除できなかったリソースを**放棄**してスタックだけを消します。放棄されたリソースは課金が続き、どのスタックにも追跡されなくなるため、後から見つけて手で消す必要があります。まず `./scripts/cleanup_stacks.sh` でブロッカーを解消し、それでも進まないときの最後の手段としてください。

### 6. S3 バケットの確認

Amplify sandbox 削除後も残るバケットがある場合：

```bash
aws s3 ls | grep -i "fsxn\|amplify-fsxn"
# 残っていれば:
# aws s3 rb s3://<bucket-name> --force
```

> **注意**: `rb --force` はバケットを空にしてから削除します。**中のオブジェクトもすべて消えます**。`athena-results-*` や `aws-sam-cli-managed-default-*` は他プロジェクトと共有される場合があるため、共有かどうかに加えて**中身**も確認してから実行してください。`aws s3 ls s3://<bucket-name> --recursive --summarize | tail -2` でオブジェクト数を先に見ておくと安全です。

## 再デプロイ

クリーンアップ後に再度環境を構築する場合：

```bash
cd solutions/amplify-portal
npm install
cp amplify/portal-config.example.ts amplify/portal-config.ts
# portal-config.ts を編集
make sandbox  # 初回 10-15 分、CDK bootstrap 含む
make dev      # ローカル開発サーバー起動
```

## トラブルシューティング

### `npx ampx sandbox delete` がタイムアウトする

CDK のスタック削除は裏で進行しています。以下で確認：

```bash
aws cloudformation list-stacks --stack-status-filter DELETE_IN_PROGRESS \
  --query 'StackSummaries[*].[StackName,StackStatus]' --output table --region ap-northeast-1
```

### DELETE_FAILED で止まる

ブロッカーリソース（非空 S3 バケット、Athena WorkGroup、ECR リポジトリ）を先に削除：

```bash
./scripts/cleanup_stacks.sh <stack-name>
```

### スタック削除後も Lambda が残る

CloudFormation 管理外で作成された Lambda は手動削除が必要：

```bash
aws lambda list-functions \
  --query 'Functions[?starts_with(FunctionName, `fsxn-`) || starts_with(FunctionName, `agentcore-`)].[FunctionName]' \
  --output text --region ap-northeast-1
```
