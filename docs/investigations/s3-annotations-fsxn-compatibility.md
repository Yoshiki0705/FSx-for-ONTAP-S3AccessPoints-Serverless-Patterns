# S3 Annotations × FSx for ONTAP S3 Access Points — 互換性調査

- 調査開始日: 2026-06-18
- 対象リリース: Amazon S3 Annotations (GA 2026-06-16, AWS Summit NYC)
- 一次情報: https://aws.amazon.com/blogs/aws/amazon-s3-annotations-attach-rich-queryable-context-directly-to-your-objects/
- AWS ドキュメント: https://docs.aws.amazon.com/AmazonS3/latest/userguide/annotations.html
- S3 Metadata overview: https://aws.amazon.com/s3/features/metadata/

---

## 1. 調査の目的

Amazon S3 Annotations API（PutObjectAnnotation, GetObjectAnnotation, ListObjectAnnotations, DeleteObjectAnnotation）が FSx for ONTAP S3 Access Points 経由で利用可能かを確認する。

利用可能であれば、NAS ファイルに直接 AI 分析メタデータを annotation として付与する新パターンが実現可能になる。利用不可の場合は、AWS サポートへの Feature Request を起票し、代替パターン（標準 S3 出力への annotation 付与）で実装を進める。

---

## 2. 検証計画

### 前提条件

- FSx for ONTAP ファイルシステム（既存検証環境）
- S3 Access Point（Internet Origin）がアタッチ済み
- テスト用ファイルが S3 AP 経由でアクセス可能（GetObject 確認済み）
- AWS CLI v2.35.6+ (S3 Annotations API 対応版)
- boto3 最新版（annotation API サポート確認要）

### 検証ステップ

#### Step 1: AWS CLI 対応確認

```bash
# AWS CLI が put-object-annotation をサポートしているか確認
aws s3api put-object-annotation help 2>&1 | head -5

# boto3 バージョン確認
python3 -c "import boto3; print(boto3.__version__)"
```

#### Step 2: 標準 S3 バケットで動作確認（ベースライン）

```bash
# テスト annotation 作成
cat > /tmp/test-annotation.json << 'EOF'
{"uc_id":"test","data_classification":"INTERNAL","confidence_score":0.95}
EOF

# 標準 S3 バケットで annotation 付与
aws s3api put-object-annotation \
  --bucket ${TEST_BUCKET} \
  --key test-file.txt \
  --annotation-name processing_metadata \
  --annotation-payload /tmp/test-annotation.json

# annotation 取得
aws s3api get-object-annotation \
  --bucket ${TEST_BUCKET} \
  --key test-file.txt \
  --annotation-name processing_metadata \
  /tmp/annotation-output.json

cat /tmp/annotation-output.json
```

#### Step 3: FSxN S3 Access Point で annotation 付与を試行

```bash
# FSxN S3 AP alias を使用
S3AP_ALIAS="<fsxn-volume-alias>-ext-s3alias"

# annotation 付与を試行
aws s3api put-object-annotation \
  --bucket ${S3AP_ALIAS} \
  --key existing-file.txt \
  --annotation-name processing_metadata \
  --annotation-payload /tmp/test-annotation.json

# 期待される結果パターン:
# A) 成功 (HTTP 200) → FSxN S3 AP で annotation サポート確認
# B) AccessDenied → IAM ポリシーに s3:PutObjectAnnotation 追加が必要
# C) NotImplemented / UnsupportedOperation → FSxN S3 AP 未サポート
# D) InvalidAction → S3 API として認識されていない
```

#### Step 4: 結果に応じた対応

| 結果 | 対応 |
|------|------|
| A) 成功 | docs 更新、shared/s3ap_helper.py に annotation メソッド追加 |
| B) AccessDenied | IAM ポリシー修正して再試行 |
| C) NotImplemented | AWS サポート Feature Request 起票 |
| D) InvalidAction | boto3/CLI バージョン確認、再試行 |

---

## 3. AWS サポート Feature Request

### 起票済み

- Case ID: `case-123456789012-muen-2026-22bf69f4797c9848`
- 起票日: 2026-06-17T15:52:05Z
- Service: FSx for NetApp ONTAP - Linux
- Category: Feature Request
- Severity: Low (General guidance)
- Status: unassigned
- Submitted by: yoshiki@netapp.com

### テンプレート（起票時に使用した内容）

### Subject

Feature Request: Support S3 Annotations API (PutObjectAnnotation/GetObjectAnnotation) on FSx for ONTAP S3 Access Points

### Severity

General guidance

### Description

**Current behavior:**
Amazon S3 Annotations (GA 2026-06-16) provides PutObjectAnnotation, GetObjectAnnotation, ListObjectAnnotations, and DeleteObjectAnnotation APIs for attaching mutable metadata to S3 objects. When these APIs are called against an FSx for ONTAP S3 Access Point alias, the operation returns [NotImplemented / error code from investigation].

**Expected behavior:**
S3 Annotations APIs should be supported on FSx for ONTAP S3 Access Points, enabling customers to attach AI-generated metadata (classification labels, processing lineage, confidence scores, summaries) directly to NAS files without modifying the file content.

**Use case:**
We are building serverless AI/ML processing pipelines that read enterprise files from FSx for ONTAP via S3 Access Points, analyze them using Amazon Bedrock, and need to persist the analysis results as metadata on the source objects. Current workaround requires writing results to a separate S3 bucket or DynamoDB table, losing the co-location benefit that S3 Annotations provides.

Specific scenarios:
1. Attaching AI-generated document classification (INTERNAL/RESTRICTED/CUI) to files processed by compliance pipelines
2. Storing processing lineage (model ID, chunking strategy, timestamp) alongside source documents for RAG systems
3. Enabling Athena-based metadata queries across FSxN volumes via S3 Metadata annotation tables
4. Supporting Permission-Aware RAG by storing ACL metadata as annotations queryable at search time

**Business impact:**
- Eliminates need for separate metadata databases (DynamoDB/RDS) to track AI analysis results
- Enables unified metadata queries across FSxN volumes via S3 Metadata + Athena
- Supports agentic AI workflows that need to discover and act on file metadata autonomously (aligned with S3 Annotations' stated GA use case)
- Reduces operational complexity in hybrid NAS + AI architectures

**Workaround currently in use:**
Processing results are written to a standard S3 bucket with annotations attached there. This loses co-location with source files and requires maintaining a separate mapping between FSxN paths and S3 output objects.

**AWS Region:** ap-northeast-1 (Tokyo)
**FSx for ONTAP version:** ONTAP 9.17.1P6

---

## 4. 検証結果

### 実施日: 2026-06-18

### 環境

- AWS CLI version: 2.35.4
- boto3 version: 1.43.31（1.43.29 → upgrade で annotation API サポート確認）
- botocore version: 1.43.31
- FSx for ONTAP version: ONTAP 9.17.1P6
- S3 AP NetworkOrigin: Internet
- S3 AP Alias: `headobj-test-s3a-ezp398gpuiixusfjkbymuqcnhaubaapn1b-ext-s3alias`

### Step 2 結果（標準 S3 バケット）— ✅ 成功

```
PutObjectAnnotation SUCCESS: HTTP 200
ETag: "2ebbe0be9e529efe914b95a9daf1bdff"
Server-side encryption: AES256

GetObjectAnnotation SUCCESS
Retrieved annotation: {"uc_id": "annotation-test", "data_classification": "INTERNAL",
  "confidence_score": 0.95, "human_review_action": "AUTO_APPROVE",
  "model_id": "amazon.nova-pro-v1:0", "processing_timestamp": "2026-06-18T12:00:00Z",
  "annotation_schema_version": "1.0"}
```

### Step 3 結果（FSxN S3 AP）— ❌ 未サポート

```
PutObjectAnnotation FAILED:
  HTTP Status: 501
  Error Code: NotImplemented
  Error Message: An access point you provided implies functionality that is not implemented
  Full error type: ClientError
```

### 判定

- [ ] ~~FSxN S3 AP で S3 Annotations がサポートされている~~
- [x] **FSxN S3 AP で S3 Annotations が未サポート → Feature Request 起票**
- [ ] ~~IAM ポリシー調整で解決可能~~

### 補足事項

1. **boto3 バージョン依存**: boto3 1.43.29 では annotation API メソッドが存在せず、1.43.31 で追加を確認。Lambda Layer 更新時に注意。
2. **API パラメータ**: `PutObjectAnnotation` に `ContentType` パラメータは存在しない。`AnnotationPayload` にバイト列を直接渡す形式。
3. **ListObjectAnnotations のレスポンスキー**: `ObjectAnnotationConfigurations` として返却される（ブログ記事のサンプルとは若干異なる）。
4. **標準 S3 バケットでは全 API が正常動作**: put → get → list → delete の全サイクルが利用可能。

### 次のアクション

- [x] docs/s3ap-compatibility-notes.md の Status 更新（❓ → ❌）
- [ ] AWS サポート Feature Request 起票（下記テンプレート使用）
- [x] shared/s3_annotations.py のフォールバック設計は正しい（API 未サポート時の graceful degradation）
- [ ] shared/s3_annotations.py の `ContentType` パラメータ削除（API が受け付けないため）

---

## 5. 関連する他のリリース（同時調査候補）

| リリース | 日付 | 本プロジェクトとの関連 |
|---------|------|---------------------|
| AWS Transform → FSx for ONTAP (Preview) | 2026-06-16 | 既に docs/screenshots/ に記録済み |
| AutoMQ + FSx for ONTAP (Diskless Kafka) | 2026-06-09 | エコシステム参考。直接統合なし |
| CloudWatch OTel Metrics + PromQL | 2026-06-16 | observability.py 将来強化候補 |
| S3 Metadata annotation tables + Athena | 2026-06-16 | S3 Annotations と連動。Athena UC に活用可能 |

---

## 6. プロジェクトへの取り込みロードマップ

### Phase A（即時・API 未サポートでも実行可能）

1. ✅ `shared/s3_annotations.py` 作成 — annotation ヘルパーモジュール
2. ✅ `shared/tests/test_s3_annotations.py` 作成 — ユニットテスト
3. ✅ `docs/s3ap-compatibility-notes.md` 更新 — annotation セクション追加
4. ✅ 本ドキュメント作成 — 調査計画 + FR テンプレート

### Phase B（検証後）

5. 検証結果に基づくドキュメント更新
6. AWS サポート Feature Request 起票（未サポート時）
7. OutputDestination=STANDARD_S3 パスへの annotation 自動付与統合
8. S3 Metadata annotation tables の Athena クエリ例作成

### Phase C（新 UC / 横断強化）

9. 新 UC 候補: "AI Metadata Enrichment via S3 Annotations"
10. 全 UC の出力に annotation 自動付与（opt-in パラメータ）
11. Annotation tables + Athena による全 UC 横断メタデータダッシュボード
