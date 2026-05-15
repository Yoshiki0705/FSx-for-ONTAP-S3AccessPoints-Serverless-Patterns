# Data Classification ガイド（公共セクター / 規制業界向け）

## 概要

FPolicy イベントパイプラインでは、ファイル操作のメタデータ（file_path、user_name、protocol 等）がイベントペイロードとして流れる。公共セクター、防衛、医療、金融などの規制業界では、これらのメタデータ自体が機密情報になり得る。

本ガイドでは、イベントペイロードのデータ分類と、各コンポーネントでの取り扱いルールを定義する。

## データ分類レベル

| レベル | 定義 | 例 |
|--------|------|-----|
| **Public** | 公開可能、機密性なし | event_id, operation_type, timestamp |
| **Internal** | 組織内利用、外部非公開 | volume_name, svm_name, client_ip |
| **Confidential** | 業務上必要な者のみアクセス | file_path (プロジェクト名含む場合) |
| **Restricted** | 最小限のアクセス、暗号化必須 | user_name, 機密ファイルパス |

## FPolicy イベントフィールド分類

| フィールド | デフォルト分類 | 備考 |
|-----------|-------------|------|
| `event_id` | Public | UUID、機密性なし |
| `operation_type` | Public | create/write/rename/delete |
| `timestamp` | Public | ISO 8601 |
| `file_size` | Public | バイト数 |
| `volume_name` | Internal | インフラ情報 |
| `svm_name` | Internal | インフラ情報 |
| `client_ip` | Internal | ネットワーク情報 |
| `protocol` | Internal | nfsv3/nfsv4/smb |
| `file_path` | Internal〜Confidential | パスにプロジェクト名や機密情報を含む場合あり |
| `user_name` | Confidential〜Restricted | AD ユーザー名、個人識別可能 |

## コンポーネント別取り扱いルール

### SQS Ingestion Queue

- 暗号化: SSE-SQS または SSE-KMS
- メッセージ保持: 最小限（処理後即削除）
- アクセス: FPolicy Server + Bridge Lambda のみ

### EventBridge Custom Bus

- イベントペイロード: 全フィールドを含む（バス内は暗号化）
- ルール: UC 別にフィルタリング（不要な UC にはイベントが流れない）
- アーカイブ: 有効化する場合は暗号化 + 保持期間を設定

### CloudWatch Logs

- FPolicy Server ログ: file_path は INFO レベルで出力（Confidential 環境では DEBUG に変更）
- Lambda ログ: request body は出力しない（log redaction 実装済み）
- 保持期間: 14 日（規制要件に応じて延長）

### Cross-Account Observability (OAM)

- 転送対象: メトリクス + X-Ray トレースのみ（ログは慎重に）
- file_path を含むログを転送する場合: hash 化または除外
- user_name: Cross-Account 転送しない

### Idempotency Store (DynamoDB)

- pk に file_path を含む: Confidential 環境では hash 化を検討
- TTL: 7 日（最小限の保持）
- 暗号化: AWS owned key（デフォルト）または CMK

### Audit Ledger

- 全フィールドを記録（監査目的）
- 暗号化: KMS CMK 必須
- アクセス: 監査チームのみ（IAM で制限）
- 改ざん防止: S3 Object Lock (Governance or Compliance mode)

## 環境別推奨設定

| 環境 | file_path | user_name | Cross-Account Log 転送 |
|------|-----------|-----------|----------------------|
| 開発 | そのまま | そのまま | 許可 |
| ステージング | そのまま | マスク推奨 | 許可（Internal まで） |
| 本番（一般） | そのまま | マスク | Confidential 除外 |
| 本番（規制業界） | hash 化 | 除外 | メトリクスのみ |
| 本番（防衛/公共） | hash 化 | 除外 | 不可（同一アカウント内のみ） |

## 実装方法

### file_path の hash 化

```python
import hashlib

def hash_file_path(file_path: str, salt: str = "") -> str:
    """file_path を SHA-256 hash 化する（監査用に元パスは Audit Ledger に保存）."""
    return hashlib.sha256(f"{salt}{file_path}".encode()).hexdigest()[:16]
```

### user_name の除外

FPolicy Server の環境変数で制御:

```bash
# user_name をイベントペイロードから除外
REDACT_USER_NAME=true
```

### CloudWatch Logs のフィルタリング

Subscription Filter で Confidential フィールドを含むログを除外:

```json
{
  "filterPattern": "{ $.file_path NOT EXISTS }"
}
```


## Cross-Account Observability Handling Policy

OAM、CloudWatch Logs、SNS、X-Ray、central dashboard にどの情報が流れるかを明確にする。

| フィールド | 感度 | Central Dashboard | Cross-Account Logs | Audit Ledger |
|-----------|------|-------------------|-------------------|-------------|
| `event_id` | Low | ✅ allow | ✅ allow | ✅ allow |
| `operation_type` | Low | ✅ allow | ✅ allow | ✅ allow |
| `timestamp` | Low | ✅ allow | ✅ allow | ✅ allow |
| `correlation_id` | Low | ✅ allow | ✅ allow | ✅ allow |
| `volume_name` | Medium | ✅ allow | ✅ allow | ✅ allow |
| `svm_name` | Medium | ⚠️ mask in shared | ✅ allow | ✅ allow |
| `protocol` | Medium | ✅ allow | ⚠️ depends on classification | ✅ allow |
| `client_ip` | Medium | ❌ exclude | ⚠️ hash | ✅ allow (encrypted) |
| `file_path` | High | ❌ exclude | ⚠️ hash before forwarding | ✅ allow (encrypted) |
| `user_name` | High | ❌ exclude | ❌ exclude | ✅ allow (encrypted) |

### 原則

> In regulated environments, metadata is data.
> File paths, user names, and protocol context should be classified
> before being forwarded to cross-account observability systems.
