> 🌐 Language: [日本語](design-considerations.md) | [English](design-considerations-en.md)

# FSx for ONTAP S3 Access Points — 設計考慮事項

本ドキュメントは、FSx for ONTAP S3 Access Points（以下「S3 AP」）を活用したサーバーレスパターンを設計・実装する際に考慮すべき技術ポイントを体系的にまとめたものである。

Lambda / Step Functions からの S3 API アクセスに最適化されたディレクトリ設計、性能特性の理解、機能互換性の把握、セキュリティ設計を網羅する。

---

## 目次

1. [ディレクトリ設計](#1-ディレクトリ設計)
2. [オブジェクトキーとパス長の制約](#2-オブジェクトキーとパス長の制約)
3. [性能特性](#3-性能特性)
4. [ListObjectsV2 の設計パターン](#4-listobjectsv2-の設計パターン)
5. [マルチプロトコルアクセスの整合性](#5-マルチプロトコルアクセスの整合性)
6. [機能互換性](#6-機能互換性)
7. [セキュリティ設計](#7-セキュリティ設計)
8. [PoC チェックリスト](#8-poc-チェックリスト)

---

## 1. ディレクトリ設計

### 問題: 単一ディレクトリへの大量ファイル集中

ONTAP ファイルシステムでは、1 ディレクトリ内のファイル数が増加すると以下の影響が観測される:

| 影響 | 原因 | 閾値目安 |
|------|------|---------|
| `readdir` 応答時間の増加 | ディレクトリエントリの線形走査 | ~10 万件超 |
| `maxdir-size` 到達によるファイル作成失敗 | ディレクトリメタデータ領域の上限 | デフォルト上限に依存 |
| FlexGroup constituent 間の偏り | ハッシュ分散がディレクトリ単位のため | 大量ファイル集中時 |
| ListObjectsV2 レスポンス遅延 | インメモリソートのコスト増加 | ~10 万件超 |

**参考**: [How do I avoid maxdir-size issues (NetApp KB)](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)

### 推奨パターン

#### Hive-style 階層パーティション

```
s3://<ap-alias>/data/year=2026/month=07/day=22/sensor_001.json
s3://<ap-alias>/data/year=2026/month=07/day=22/sensor_002.json
```

S3 AP では「/」がディレクトリセパレータとして解釈されるため、階層パーティションは自動的にディレクトリ構造にマッピングされる。

#### ハッシュバケット

```
s3://<ap-alias>/objects/a3/b2/object-uuid-001.bin
s3://<ap-alias>/objects/f7/e1/object-uuid-002.bin
```

ファイル名の先頭 2-4 文字をハッシュバケットとして使用し、ディレクトリ当たりのファイル数を分散。

#### テナント + 日付ハイブリッド

```
s3://<ap-alias>/tenant-a/2026/07/22/report.pdf
s3://<ap-alias>/tenant-b/2026/07/22/invoice.csv
```

マルチテナントシナリオで、テナント分離と時系列アクセスパターンの両方を満たす。

### 1 ディレクトリ内のファイル数目安

| シナリオ | 推奨上限 | 根拠 |
|---------|---------|------|
| 一般的なワークロード | 10 万件以下 | ListObjectsV2 レスポンスとディレクトリ走査の実用的な上限 |
| 高頻度書き込み（IoT/ログ） | 1 万件以下 | 書き込み頻度が高い場合、パーティション分割を細かくする |
| FlexGroup 利用時 | 5 万件以下 / constituent | constituent 間の均等分散を維持 |

### FlexVol vs FlexGroup の選択基準

| 判断基準 | FlexVol | FlexGroup |
|---------|---------|-----------|
| 単一ボリューム最大サイズ | ~100 TB（実用的上限） | PB スケール |
| ファイル数上限 | ~20 億 | constituent 数 × 20 億 |
| FlexCache Origin 対応 | 9.12.1+ | 9.13.1+（制約あり） |
| SnapMirror 対応 | フル対応 | フル対応 |
| S3 AP 対応 | ✅ | ✅ |
| 推奨用途 | 単一ワークロード / PoC | 大規模データ / マルチテナント |

**参考**: [FlexGroup volumes overview (NetApp Docs)](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)

---

## 2. オブジェクトキーとパス長の制約

### 長さ制限

| 制約 | 上限 | 備考 |
|------|------|------|
| S3 オブジェクトキー全長 | 1,024 バイト | UTF-8 バイト長。日本語 1 文字 = 3-4 バイト |
| ディレクトリ名 / ファイル名 | 255 文字 | ONTAP ファイルシステムの制約 |
| パスの深さ | 制限なし（実用的には ~30 レベル） | ネスト深度に明示的制限はないが深すぎると運用性低下 |

### マルチバイト文字の注意点

```
# 日本語ファイル名の例
"レポート_2026年07月.pdf"
→ UTF-8: 31 バイト（「レ」= 3B × 7文字 + ASCII = 31B）
→ 255 文字制限内だが、1,024B キー上限ではパス全体で計算
```

### S3 と NFS/SMB の両方で安全な文字セット

| カテゴリ | 安全な文字 | 避けるべき文字 |
|---------|-----------|--------------|
| ASCII | `a-z`, `A-Z`, `0-9`, `-`, `_`, `.` | `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` |
| Unicode | CJK 統合漢字、ハングル、ラテン拡張 | 制御文字 (U+0000-U+001F), BOM |
| 特殊 | `/`（S3 デリミタ = ディレクトリセパレータ） | 先頭/末尾の空白、連続スラッシュ `//` |

**設計指針**: Lambda からのキー生成では、ファイル名を正規化（NFKC）してから使用する。NFS/SMB で作成されたファイルをS3 AP で読む場合、クライアント OS のエンコーディングに依存する文字は避ける。

---

## 3. 性能特性

### ファイルサイズ別の性能傾向

| ファイルサイズ | 特性 | Lambda パターンへの影響 |
|-------------|------|----------------------|
| < 64 KB | メタデータ処理のオーバーヘッドが相対的に大きい | バッチ処理で集約が有利な場面がある |
| 64 KB – 1 MB | 一般的なドキュメント / JSON サイズ | 多くのサーバーレスパターンで最適なレンジ |
| > 1 MB | データ転送が支配的。大きいほど Amazon S3 との性能差が縮小する傾向 | Multipart Upload の利用を検討 |
| > 5 GB | S3 AP の PutObject 上限（5 GB）に注意 | Multipart Upload 必須（ONTAP 9.16.1+） |

### スループット設計

FSx for ONTAP のスループット容量は NFS/SMB/S3 AP で共有される。S3 AP トラフィックが増加すると、同一ボリュームへの NFS/SMB 性能に影響する場合がある。

**設計ポイント**:
- バッチ処理（大量の S3 API コール）は NFS/SMB ピーク時間帯を避ける
- EventBridge Scheduler でオフピーク時間にジョブを実行
- スループット容量のモニタリング（CloudWatch `TotalThroughputUtilization`）

### 対策パターン

| 課題 | 対策 |
|------|------|
| 小ファイル大量書き込みの効率 | TAR/ZIP 集約後に単一 PutObject、または Kinesis Data Firehose で結合 |
| ListObjectsV2 の遅延 | Prefix 限定、外部カタログ（DynamoDB / Glue Data Catalog）活用 |
| 読み取りレイテンシ | FlexCache で読み取り加速（同一クラスタ: ~6 秒伝搬、クロスリージョン: <3 秒） |

---

## 4. ListObjectsV2 の設計パターン

### ONTAP 内部での動作

S3 AP の ListObjectsV2 は ONTAP 内部で以下のように処理される:

1. 指定された Prefix に対応するディレクトリを `readdir` で走査
2. エントリをインメモリでソート（S3 API の辞書順保証のため）
3. MaxKeys に基づいて結果を返却

ソートコストはディレクトリ内のファイル数に比例するため、大量ファイルが存在するディレクトリでの LIST は応答時間が増加する。

### 推奨パターン

| パターン | 説明 | 適用場面 |
|---------|------|---------|
| Prefix 限定 LIST | `Prefix=data/2026/07/22/` で日次パーティションに絞る | バッチ処理の入力ファイル特定 |
| MaxKeys 制限 | `MaxKeys=100` で必要最小限のみ取得 | ストリーミング処理 |
| LIST を使わない設計 | SQS/EventBridge で新規ファイルの S3 キーを受け取る | イベント駆動パターン |
| 外部カタログ | DynamoDB / Glue Data Catalog にメタデータを登録 | 大規模データレイク |

### アンチパターン

| アンチパターン | 問題 | 代替案 |
|-------------|------|--------|
| ルート (`/`) での全件 LIST | ボリューム全体を走査。数十万件で数十秒〜タイムアウト | Prefix 必須 |
| Recursive LIST (Delimiter なし) | 全サブディレクトリを再帰走査 | 階層ごとに LIST |
| ポーリングによるファイル検出 | LIST の繰り返し実行 | EventBridge / FPolicy イベント駆動 |
| 全件取得後のクライアント側フィルタ | 不要なデータ転送 | Prefix + StartAfter で絞り込み |

---

## 5. マルチプロトコルアクセスの整合性

### 同時アクセスシナリオ

S3 AP を通じたデータアクセスは、同一ボリュームへの NFS/SMB アクセスと共存する。以下の競合パターンに注意が必要:

| シナリオ | 動作 | リスク |
|---------|------|--------|
| NFS 書き込み中に S3 AP GET | 書き込み途中のデータが読まれる可能性（部分読み取り） | データ不整合 |
| S3 AP PutObject 完了後に NFS read | 即座に一貫したデータが読める（WAFL の原子的コミット） | なし |
| NFS rename 直後に S3 AP GET（旧キー） | 旧キーでは NotFound（rename は即座に反映） | アプリケーション側のキー管理 |
| S3 AP 書き込み + FlexCache write-back 同一ファイル | Cache のダーティデータが破棄される（XLD revoke） | データ競合 |

### 推奨設計

1. **書き込みプロトコルを 1 つに限定**: 同一ファイルへの S3 AP 書き込みと NFS/SMB 書き込みを同時に行わない
2. **一時ディレクトリ → rename パターン**: S3 AP で `/tmp/processing/` に書き込み、処理完了後に NFS で `/data/final/` に移動
3. **ファイルレベルの分離**: S3 AP は新規ファイルの作成のみ、NFS/SMB は既存ファイルの読み取りのみ、のように役割を分ける
4. **ONTAP Snapshot による一貫性ポイント**: バッチ処理の入力データを Snapshot で固定し、処理中の変更を排除

---

## 6. 機能互換性

FSx for ONTAP S3 AP は「S3 互換」だが「Amazon S3 と同一」ではない。以下の差分を設計時に考慮すること。

### 対応状況一覧

| 機能 | S3 AP 対応 | 代替手段 | 備考 |
|------|:----------:|---------|------|
| GetObject / PutObject | ✅ | — | 最大 5 GB/オブジェクト |
| Multipart Upload | ✅ | — | ONTAP 9.16.1 以上 |
| ListObjectsV2 | ✅ | — | Prefix / Delimiter / MaxKeys 対応 |
| HeadObject | ✅ | — | |
| DeleteObject | ✅ | — | |
| CopyObject | ✅ | — | 同一 AP 内のみ |
| Versioning | ❌ | ONTAP Snapshot（ボリューム単位） | バージョン管理は Snapshot + FlexClone で代替 |
| 条件付き書き込み (If-None-Match) | ❌ | アプリケーションレベルのロック | 501 Not Implemented が返る |
| S3 Event Notification | ❌ | FPolicy + EventBridge | FPolicy で ONTAP 層のファイル操作イベントを取得 |
| Lifecycle Rules | ❌ | FabricPool / ONTAP Tiering Policy | `AUTO` / `SNAPSHOT_ONLY` で自動階層化 |
| Object Lock / WORM | ❌ | SnapLock | コンプライアンス要件には SnapLock Compliance |
| S3 Select | ❌ | Athena + Glue Data Catalog | 外部分析エンジンで処理 |
| Server-Side Encryption (SSE-S3/KMS) | ❌ | NAE / NVE (ONTAP ボリューム暗号化) | at-rest は ONTAP 層で暗号化。in-transit は TLS |
| Presigned URL | ⚠️ | — | 動作するケースあり（非公式）。本番依存は非推奨 |
| Cross-AP Copy | ❌ | DataSync / rsync | 異なる AP 間のコピーは不可 |

**参考**: [Accessing data via S3 Access Points (AWS Docs)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

### 影響を受けるサーバーレスパターン

| パターン | 影響する機能制約 | 対策 |
|---------|----------------|------|
| Delta Lake / Iceberg テーブル | 条件付き書き込み非対応 | アプリケーション側の排他制御、または標準 S3 にメタストア配置 |
| イベント駆動処理 | S3 Event Notification 非対応 | FPolicy + EventBridge で同等機能を実現 |
| ライフサイクル管理 | Lifecycle Rules 非対応 | ONTAP Tiering Policy + Snapshot 自動削除ポリシー |
| コンプライアンス保持 | Object Lock 非対応 | SnapLock Compliance ボリューム |

---

## 7. セキュリティ設計

### Access Point の用途別分割

単一ボリュームに対して複数の S3 AP を作成し、用途・権限を分離する:

```
Volume: vol_production_data
├── S3 AP: prod-readonly     → GET/LIST のみ (分析 Lambda 用)
├── S3 AP: prod-ingestion    → PUT のみ (データ収集 Lambda 用)
├── S3 AP: prod-training     → GET のみ (ML トレーニング用)
└── S3 AP: prod-audit        → GET/LIST のみ (監査 Lambda 用、別 UNIX ユーザー)
```

### 二層認可モデル

S3 AP のアクセスは二層で制御される。両層の AND 条件が必要:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: AWS IAM + AP Resource Policy                        │
│ - IAM Identity Policy (Lambda 実行ロール)                     │
│ - S3 AP Resource Policy (オプション、クロスアカウント時に必須)    │
│ - 制御対象: 誰が / どのリソースに / どの API を呼べるか         │
└─────────────────────────────────────────────────────────────┘
                            ↓ (両方 Allow で通過)
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: NAS ファイルシステム権限                              │
│ - FileSystemIdentity (UNIX UID/GID or Windows AD user)       │
│ - UNIX パーミッション / POSIX ACL / NTFS ACL                  │
│ - 制御対象: ファイル・ディレクトリ単位のアクセス制御             │
└─────────────────────────────────────────────────────────────┘
```

### IAM ポリシーのベストプラクティス

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3APReadOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/prod-readonly",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/prod-readonly/object/*"
      ]
    }
  ]
}
```

**設計ポイント**:
- 各 Lambda 関数に専用の IAM ロールを付与（共有ロール禁止）
- S3 AP ARN にはリージョンとアカウント ID が必須（バケット ARN 形式は不可）
- 同一アカウント内では AP Resource Policy は不要（IAM Identity Policy のみで認可可能）
- クロスアカウントアクセス時のみ AP Resource Policy を追加

---

## 8. PoC チェックリスト

FSx for ONTAP S3 AP を使用するサーバーレスパターンの PoC で確認すべき項目:

### アーキテクチャ

- [ ] S3 AP の NetworkOrigin を決定（Internet / VPC）
- [ ] Lambda の配置を決定（VPC 内 = ONTAP REST API 用 / VPC 外 = Internet-origin S3 AP 用）
- [ ] スループット容量が NFS/SMB + S3 AP の合計トラフィックを賄えるか確認
- [ ] AD-joined SVM の場合: AD DC の可達性が S3 AP データオペレーションの前提条件であることを確認

### 名前空間

- [ ] ディレクトリ階層のパーティション設計を決定
- [ ] 1 ディレクトリ当たりのファイル数が 10 万件を超えないことを確認
- [ ] オブジェクトキーが 1,024 バイト以内に収まることを確認
- [ ] マルチバイトファイル名の扱いを決定（NFKC 正規化の要否）

### 性能

- [ ] 対象ファイルサイズの分布を確認（小ファイル集約の要否）
- [ ] ListObjectsV2 の実行パターンを確認（Prefix 限定 / 全件走査の有無）
- [ ] NFS/SMB ワークロードとの共存時のスループット配分を確認
- [ ] FlexCache 利用時のキャッシュヒット率とデータ伝搬レイテンシを計測

### 機能

- [ ] 条件付き書き込みへの依存有無を確認（Delta Lake / Iceberg 等）
- [ ] S3 Event Notification への依存有無を確認（FPolicy 代替の要否）
- [ ] Multipart Upload の要否を確認（ONTAP バージョン要件: 9.16.1+）
- [ ] Presigned URL への依存有無を確認（本番非推奨）

### セキュリティ

- [ ] 用途別 S3 AP 分割設計を確認
- [ ] IAM ロールの最小権限を確認
- [ ] FileSystemIdentity（UNIX ユーザー）の選定と NAS パーミッションの整合性
- [ ] Secrets Manager によるクレデンシャル管理パターンの確認

### 運用

- [ ] CloudWatch メトリクス（TotalThroughputUtilization, S3APIRequests）のアラーム設定
- [ ] S3 AP のライフサイクル管理（ボリューム削除前に AP をデタッチ）
- [ ] SnapMirror DR 時の S3 AP 再作成手順の文書化
- [ ] Teardown 順序の文書化（SM-VAL-011 準拠）

---

## FlexCache / SnapMirror 利用時の追加考慮事項

S3 AP で収集したデータを FlexCache（読み取り加速）や SnapMirror（DR）で配信する場合の追加設計ポイント:

| 考慮事項 | 詳細 | 参照 |
|---------|------|------|
| S3 AP metadata は SnapMirror で転送されない | 宛先に新規 S3 AP 作成が必要 | [SnapMirror DR パターン](../solutions/flexcache/snapmirror-cross-region-dr/) |
| FlexCache Cache Volume への S3 AP | ONTAP 9.18.1 以上が必要 | [FlexCache Same-Region パターン](../solutions/flexcache/same-region-s3ap/) |
| write-back + S3 AP 同一ファイル競合 | XLD revoke により Cache ダーティデータ破棄 | [FlexCache Cross-Region パターン](../solutions/flexcache/cross-region-s3ap/) |
| DP Volume は FSx API で作成必須 | SM-VAL-009: ONTAP REST API のみでは S3 AP アタッチ不可 | [SnapMirror DR パターン](../solutions/flexcache/snapmirror-cross-region-dr/) |
| Teardown 順序 | SM-VAL-011: VPC Peering 削除前に SVM Peer 削除完了必須 | 各 FlexCache/SnapMirror パターンの Clean Up セクション |

詳細な互換性テーブル・バージョンマトリクス: [FlexCache / SnapMirror 考慮事項（fsxn-lakehouse-integrations）](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/ja/s3ap-flexcache-snapmirror-considerations.md)

---

## 参考資料

- [AWS Docs: Accessing data via S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [AWS Docs: Optimizing S3 Performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: How do I avoid maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp KB: Performance impacts of changing maxdirsize](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/What_are_the_performance_impacts_of_changing_the_size_of_maxdirsize)
- [NetApp Docs: FlexGroup volumes](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
- [NetApp Docs: S3 multiprotocol](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
