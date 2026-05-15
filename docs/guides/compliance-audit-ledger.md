# Compliance Audit Ledger 設計ガイド

## 概要

規制業界（金融、医療、公共）では、重複排除（deduplication）によってスキップされたイベントも監査証跡として記録する必要がある。Idempotency Store は処理の重複防止に有効だが、「処理しなかったイベント」の記録は別途必要。

## 原則

> Deduplication should not mean disappearance.
> Even skipped duplicate events need an audit trail in regulated environments.

## Audit Ledger スキーマ

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `event_id` | String (UUID) | FPolicy イベント ID |
| `uc_name` | String | 処理対象 UC 名 |
| `file_path` | String | ファイルパス |
| `operation_type` | String | create / write / rename / delete |
| `dedup_decision` | String | `processed` / `skipped_duplicate` / `skipped_error` |
| `correlation_id` | String | 相関 ID（Step Functions execution ARN 等） |
| `idempotency_key` | String | Idempotency Store の pk#sk |
| `source_event_timestamp` | String (ISO 8601) | 元イベントのタイムスタンプ |
| `ingestion_timestamp` | String (ISO 8601) | Audit Ledger への記録時刻 |
| `state_machine_execution_arn` | String | Step Functions 実行 ARN（処理された場合） |

## 保存先候補

| 保存先 | メリット | デメリット |
|--------|---------|----------|
| S3 (Object Lock) | 改ざん防止、長期保管、低コスト | クエリに Athena 必要 |
| DynamoDB Streams → S3 | 自動エクスポート、リアルタイム | 設定が複雑 |
| CloudWatch Logs (長期保持) | 統合検索、Logs Insights | コスト高（大量データ時） |
| CloudTrail Lake | 統合監査、SQL クエリ | コスト高 |

## 推奨アーキテクチャ

```
Step Functions
  │
  ├── IdempotencyCheck (first step)
  │     │
  │     ├── [NEW] → Process → Audit Ledger (dedup_decision: processed)
  │     │
  │     └── [DUPLICATE] → Audit Ledger (dedup_decision: skipped_duplicate)
  │                         → SkipDuplicate (Succeed)
  │
  └── ProcessFile → ... → Audit Ledger (final status)
```

## 実装方針

### Phase 12 候補

1. Idempotency Checker Lambda に audit log 出力を追加
2. CloudWatch Logs に構造化 JSON で出力
3. S3 Object Lock バケットへの長期エクスポート（Subscription Filter → Firehose → S3）

### Idempotency Checker への追加例

```python
# idempotency_checker.py に追加
audit_record = {
    "event_id": event.get("event_id", ""),
    "uc_name": USE_CASE,
    "file_path": file_path,
    "operation_type": operation_type,
    "dedup_decision": "skipped_duplicate" if is_duplicate else "processed",
    "idempotency_key": pk,
    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
}
logger.info("[AuditLedger] %s", json.dumps(audit_record, ensure_ascii=False))
```

## Event Payload Minimization（公共セクター向け）

FPolicy イベントには file_path、user_name、protocol 等が含まれる。
公共・防衛・医療系ワークロードでは、これらのメタデータ自体が機密情報になり得る。

### 推奨対応

1. **分類**: 各フィールドを Public / Internal / Confidential / Restricted に分類
2. **マスク**: Confidential 以上のフィールドは hash 化してから Audit Ledger に記録
3. **除外**: Cross-Account Observability に転送する際は Restricted フィールドを除外
4. **暗号化**: Audit Ledger の保存先は KMS 暗号化必須

### フィールド分類例

| フィールド | 分類 | Cross-Account 転送 | Audit Ledger |
|-----------|------|-------------------|-------------|
| event_id | Public | ✅ | ✅ |
| operation_type | Public | ✅ | ✅ |
| timestamp | Public | ✅ | ✅ |
| file_path | Internal〜Confidential | ⚠️ hash 化推奨 | ✅ (暗号化) |
| user_name | Confidential | ❌ 除外 | ✅ (暗号化) |
| client_ip | Internal | ⚠️ | ✅ |
| volume_name | Internal | ✅ | ✅ |
| svm_name | Internal | ✅ | ✅ |
