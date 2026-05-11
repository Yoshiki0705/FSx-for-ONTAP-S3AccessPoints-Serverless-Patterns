# UC16 デモスクリプト（30 分枠）

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 前提

- AWS アカウント、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `government-archives/template-deploy.yaml` をデプロイ（`OpenSearchMode=none` でコスト抑制）

## タイムライン

### 0:00 - 0:05 イントロ（5 分）

- ユースケース: 自治体・行政の公文書管理デジタル化
- FOIA / 情報公開請求の法定期限（20 営業日）の負荷
- 課題: PII 検出・墨消しは手動で数時間かかる

### 0:05 - 0:10 アーキテクチャ（5 分）

- Textract + Comprehend + Bedrock の組み合わせ
- OpenSearch の 3 モード（none / serverless / managed）
- NARA GRS 保存期間の自動管理

### 0:10 - 0:15 デプロイ（5 分）

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 処理実行（7 分）

```bash
# サンプル PDF（機密情報含む）アップロード
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

結果を確認:
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt`（生テキスト）
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json`（分類結果）
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json`（PII 検出）
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt`（墨消し版）
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json`（sidecar）

### 0:22 - 0:27 FOIA 期限トラッキング（5 分）

```bash
# FOIA 請求登録
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 手動実行
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

SNS 通知メールを確認。

### 0:27 - 0:30 Wrap-up（3 分）

- OpenSearch 有効化（`serverless` で本格検索）のパス
- GovCloud 移行（FedRAMP High 要件）
- 次ステップ: Bedrock エージェントで対話型 FOIA 回答生成

## よくある質問と回答

**Q. 日本の情報公開法（30 日）に対応可能？**  
A. `REMINDER_DAYS_BEFORE` と 20 営業日のハードコードを修正すれば対応可（US 連邦祝日→日本の祝日へ）。

**Q. 原文 PII はどこに保存される？**  
A. どこにも保存しません。`pii-entities/*.json` は SHA-256 hash のみ、`redaction-metadata/*.json` も hash + offset のみ。復元は原文から再実行が必要。

**Q. OpenSearch Serverless のコスト削減方法？**  
A. 最低 2 OCU = 月 $350 ほど。本番以外は停止推奨。
A. `OpenSearchMode=none` で skip、または `OpenSearchMode=managed` + `t3.small.search × 1` で ~$25/月に抑制。

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

UC16 government-archives は 2026-05-11 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: OCR テキスト / 文書分類 / PII 検出 / 墨消し / OpenSearch 前段ドキュメント

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${AWS::StackName}-output-${AWS::AccountId}`）を作成し、
AI 成果物をそこに書き込みます。Discovery Lambda の manifest のみ S3 Access Point
に書き込まれます（従来通り）。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" パターン）
OCR テキスト、分類結果、PII 検出結果、墨消し済み文書、墨消しメタデータを、FSxN S3 Access Point
経由でオリジナル文書と**同一の FSx ONTAP ボリューム**に書き戻します。
公文書担当者が SMB/NFS の既存ディレクトリ構造内で AI 成果物を直接参照できます。
標準 S3 バケットは作成されません。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**チェーン構造の読み戻し**:

UC16 は前段の成果物を後段 Lambda が読み戻すチェーン構造（OCR → Classification →
EntityExtraction → Redaction → IndexGeneration）のため、`shared/output_writer.py` の
`get_bytes/get_text/get_json` で書き込み先と同じ destination から読み戻します。
これにより `OutputDestination=FSXN_S3AP` 時も FSxN S3 Access Point からの
読み戻しが成立し、チェーン全体が一貫した destination で動作します。

**注意事項**:

- `S3AccessPointName` の指定を強く推奨（Alias 形式と ARN 形式の両方で IAM 許可する）
- 5GB 超のオブジェクトは FSxN S3AP では不可（AWS 仕様）、マルチパートアップロード必須
- ComplianceCheck Lambda は DynamoDB のみを使用するため `OutputDestination` の影響を受けません
- FoiaDeadlineReminder Lambda は DynamoDB + SNS のみを使用するため影響を受けません
- OpenSearch インデックスは `OpenSearchMode` パラメータで別途管理されます（`OutputDestination` とは独立）
- AWS 仕様上の制約は
  [プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
  および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ✅ **E2E 検証**: SUCCEEDED（Phase 7 Extended Round, commit b77fc3b）
- 📸 **UI/UX 撮影**: ✅ 完了（Phase 8 Theme D, commit d7ebabd）

### 既存スクリーンショット（Phase 7 検証時）

![Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc16-demo/step-functions-graph-succeeded.png)

![S3 出力バケット](../../docs/screenshots/masked/uc16-demo/s3-output-bucket.png)

![DynamoDB retention テーブル](../../docs/screenshots/masked/uc16-demo/dynamodb-retention-table.png)
### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（ocr-results/、classified/、redacted/、compliance/）
- Textract OCR 結果 JSON プレビュー（Cross-Region us-east-1）
- 墨消し（Redaction）済みドキュメントプレビュー
- DynamoDB retention テーブル（FOIA 期限管理）
- FOIA リマインダー SNS メール通知
- OpenSearch インデックス（IndexGeneration 結果、OpenSearchMode 有効時）
- FSx ONTAP ボリューム上の AI 成果物（FSXN_S3AP モード時）

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=government-archives bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC16` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `archives/` プレフィックスにサンプル PDF/画像をアップロード
   - Step Functions `fsxn-government-archives-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-government-archives-demo-output-<account>` の俯瞰
   - OCR / Classification / Redaction 各段階の出力 JSON プレビュー
   - DynamoDB retention テーブルのアイテム一覧
   - SNS FOIA リマインダーメール

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py government-archives-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC16` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
