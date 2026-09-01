# FSx for ONTAP S3 Access Points — オブジェクトサイズ上限の実測検証

> 🌐 **Language / 言語**: 日本語 | [English](s3ap-object-size-limits-verification.en.md)

**検証日**: 2026-08-02
**リージョン**: ap-northeast-1
**対象**: Amazon FSx for NetApp ONTAP の S3 Access Points（FSx for ONTAP S3 AP）
**目的**: アップロード時のオブジェクトサイズ上限がドキュメント更新で 5 GB → 50 GB に変わった件について、実際にエラーが発生するサイズとエラーメッセージを実測で確定する

---

## エグゼクティブサマリー

**ドキュメントの「5 GB」「50 GB」はいずれも二進表記でした。** 実測値は次のとおりです。

| 検証項目 | 実測値（バイト） | 換算 | 状態 |
|---------|----------------:|------|:---:|
| 単一 `PutObject` の上限 | **5,368,709,120** | 5 GiB | ✅ 実測確定 |
| `UploadPart`（1 パート）の上限 | **5,368,709,120** | 5 GiB | ✅ 実測確定 |
| オブジェクト全体の上限（アップロード） | **53,687,091,200** | 50 GiB | ✅ 実測確定 |
| `UploadPartCopy` | ドキュメントでは Supported だが `NoSuchKey` で失敗 | — | ✅ 実測確定 |

境界は 1 バイト単位で確定しています。

| サイズ（バイト） | 結果 |
|----------------:|------|
| 5,368,709,120（5 GiB） | ✅ 単一 `PutObject` 成功範囲 |
| 5,368,709,121（5 GiB + 1） | ❌ `PutObject` が 400 `EntityTooLarge` |
| 53,687,091,200（50 GiB） | ✅ マルチパートで成功（`ContentLength=53687091200`） |
| 53,687,091,201（50 GiB + 1） | ❌ `CompleteMultipartUpload` が 400 `EntityTooLarge` |

### 運用上、最も重要な発見

**オブジェクト全体の上限は `UploadPart` では検査されず、`CompleteMultipartUpload` でのみ検査されます。** 50 GiB + 1 バイトのテストでは 11 パート（合計 53,687,091,201 バイト）すべてが正常にアップロードされ、**590 秒（約 10 分）かけて全データを転送し終えた後**に初めて拒否されました。

つまり、上限を 1 バイト超えただけのオブジェクトでも、**転送帯域と時間を全量消費してから失敗**します。単一 `PutObject` と `UploadPart` が Content-Length で即座に拒否するのとは対照的です。

さらに `CompleteMultipartUpload` のエラーには、`PutObject` / `UploadPart` では返る `ProposedSize` と `MaxSizeAllowed` が**含まれません**。クライアントがエラーから上限値を知る手段がないため、上限の発見には試行錯誤が必要です。

> **設計への示唆**: 5 GiB を超えるオブジェクトを扱うアプリケーションは、**アップロード開始前にクライアント側で 50 GiB を超えないことを検証すべき**です。サービス側の事前チェックは存在せず、超過分は転送完了後に判明します。

---

## 検証環境

| 項目 | 値 |
|------|-----|
| リージョン | ap-northeast-1 |
| ファイルシステム | FSx for ONTAP, Single-AZ, スループットキャパシティ 128 MBps, SSD 1024 GiB |
| ボリューム | UNIX セキュリティスタイル |
| S3 AP | ONTAP アタッチ型, `FileSystemIdentity` = UNIX (`root`), Internet origin |
| クライアント | boto3 / botocore（SigV4 明示指定、リトライ 1 回） |
| 実行元 | ローカル端末（リージョン外）— 上限拒否は Content-Length で判定されるため帯域に依存しない |

> アカウント ID・ボリューム ID・アクセスポイントエイリアスは公開ドキュメントの方針に従い記載していません。

---

## 検証 1: 単一 `PutObject` の上限

### 手順

Content-Length を明示した上でゼロ埋めストリームを渡し、S3 側が上限判定を行うかを確認します。

```python
s3.put_object(Bucket=<ap-alias>, Key=key, Body=stream, ContentLength=5*1024**3 + 1)
```

### 結果: 5 GiB + 1 バイト（5,368,709,121）→ 拒否

```
RESULT=CLIENT_ERROR elapsed=2.7s
  HTTPStatusCode : 400
  Code           : EntityTooLarge
  Message        : Your proposed upload exceeds the maximum allowed size
  ErrorExtra     : {'ProposedSize': '5368709121', 'MaxSizeAllowed': '5368709120'}
  bytes_streamed : 12582912
```

### 読み取れること

- **`MaxSizeAllowed` = 5,368,709,120 = 5 × 1024³ = 5 GiB**（十進 5 GB = 5,000,000,000 ではない）
- 拒否は**転送開始直後**（約 12 MB 送信時点、2.7 秒）に発生
- エラーコードは Amazon S3 標準の `EntityTooLarge`

---

## 検証 2: `UploadPart`（マルチパートの 1 パート）の上限

### 結果

| 要求サイズ | 結果 | `MaxSizeAllowed` | 実転送量 |
|-----------|------|-----------------|---------|
| 5,368,709,121（5 GiB + 1） | 400 `EntityTooLarge` | 5,368,709,120 | 10,485,760 |
| 6,442,450,944（6 GiB） | 400 `EntityTooLarge` | 5,368,709,120 | 8,388,608 |

```
--- UploadPart 6 GiB: 6442450944 bytes ---
  RESULT=REJECTED status=400
    Code    : EntityTooLarge
    Message : Your proposed upload exceeds the maximum allowed size
    Extra   : {'ProposedSize': '6442450944', 'MaxSizeAllowed': '5368709120'}
```

### 読み取れること

パートサイズ上限も 5 GiB で、Amazon S3 標準のマルチパート仕様（パートサイズ 5 MiB〜5 GiB）と一致します。したがって 50 GiB のオブジェクトを作るには**最低 10 パート**が必要です。

---

## 検証 3: ドキュメント上 Supported な `UploadPartCopy` の失敗

[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) は `UploadPartCopy`（same-Region、同一アクセスポイント内）を Supported と記載していますが、実測では**すべての `CopySource` 表記で `NoSuchKey`** となりました。同一キーに対する `HeadObject` は成功し、`CopyObject` も成功するため、キーの存在やアクセス権の問題ではありません。

| API | `CopySource` 形式 | 結果 |
|-----|------------------|------|
| `UploadPartCopy` | `{Bucket: <alias>, Key: k}` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `{Bucket: <ap-arn>, Key: k}` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `"<alias>/k"` | ❌ 404 `NoSuchKey` |
| `UploadPartCopy` | `"<ap-arn>/object/k"` | ❌ 404 `NoSuchKey` |
| `CopyObject` | `{Bucket: <alias>, Key: k}` | ✅ 成功 |
| `CopyObject` | `"<alias>/k"` | ✅ 成功 |
| `HeadObject`（同一キー） | — | ✅ 成功 |

> **実務上の影響**: サーバーサイドで大きなオブジェクトを組み立てる（小さなオブジェクトを複製してパートとして連結する）手法が使えません。5 GiB を超えるオブジェクトを作るには、クライアントから実データを転送する必要があります。大容量データの検証コストに直接影響するため、AWS Support への確認事項に含める価値があります。

---

## 検証 4: オブジェクト全体の上限 = 50 GiB（マルチパートアップロード）

### 実施方法

150 GiB のテスト専用ボリュームと VPC origin の S3 AP を新規作成し、リージョン内 EC2（`c6in.large`）から最大パートサイズ 5 GiB × 10 パートで 50 GiB のオブジェクトを組み立てました。パートのソースにはスパースファイル（`truncate` で作成、`blocks_on_disk=0`）を使い、送信側のディスク消費をゼロにしています。

> **VPC origin を選んだ理由**: 検証環境の VPC では S3 Gateway エンドポイントが**全ルートテーブル**に関連付けられており、Internet origin の S3 AP は S3 Gateway エンドポイント経由では到達できません。共有アカウントの既存ネットワーク設定を変更しないため、テスト用 AP を VPC origin で作成しました。

### 結果 A: 53,687,091,200 バイト（50 GiB ちょうど）→ 成功

```
target=53687091200 (50.000000000 GiB / 53.687091200 GB)
part_size=5368709120 full_parts=10 tail=0 total_parts=10
  part  1/10 cumulative= 5368709120 ( 5.000 GiB)   53s  97 MiB/s
  part  5/10 cumulative=26843545600 (25.000 GiB)  269s  95 MiB/s
  part 10/10 cumulative=53687091200 (50.000 GiB)  538s  95 MiB/s
calling CompleteMultipartUpload ...
RESULT=SUCCESS ContentLength=53687091200 elapsed=1095s
```

### 結果 B: 53,687,091,201 バイト（50 GiB + 1）→ `CompleteMultipartUpload` で失敗

```
target=53687091201 (50.000000001 GiB / 53.687091201 GB)
part_size=5368709120 full_parts=10 tail=1 total_parts=11
  part 10/11 size=5368709120 cumulative=53687091200 (50.000 GiB) 536s  96 MiB/s
  part 11/11 size=1          cumulative=53687091201 (50.000 GiB) 590s  87 MiB/s
                                    ↑ 1 バイトのパートも正常に受理される

calling CompleteMultipartUpload ...
RESULT=COMPLETE_FAILED
    parts_uploaded : 11
    declared_total : 53687091201
    HTTPStatusCode : 400
    Code           : EntityTooLarge
    Message        : Your proposed upload exceeds the maximum allowed size
```

### 読み取れること

1. **上限は正確に 50 GiB = 53,687,091,200 バイト**。ドキュメントの「50 GB」は十進 50×10⁹（46.57 GiB）ではありません。
2. **`UploadPart` に累積サイズのチェックはありません**。50 GiB + 1 バイト分の 11 パートすべてが受理され、1 バイトのテールパートも正常に登録されました。
3. **拒否は `CompleteMultipartUpload` のみ**。全データ転送（590 秒）を終えた後に発覚します。事前チェックの手段はサービス側に用意されていません。
4. **`CompleteMultipartUpload` のエラーに `MaxSizeAllowed` / `ProposedSize` が含まれません**。検証 1・2 の `PutObject` / `UploadPart` では返るため、API 間で一貫していません。
5. **`CompleteMultipartUpload` 自体に時間がかかります**。成功ケースはアップロード完了が 538 秒、全体が 1095 秒なので、**組み立てだけで約 557 秒（9 分強）**を要しました。クライアントは十分に長い `read_timeout` を設定する必要があります（本検証では 1800 秒）。
6. スループットは全パートで 95〜97 MiB/s と安定し、ファイルシステムのスループットキャパシティ 128 MBps（約 122 MiB/s）が律速でした。

### 副次的な観測: ゼロ埋めデータはほぼ容量を消費しない

約 29 GB を送信した時点でも、ファイルシステムの `StorageUsed`（SSD）の増加は約 0.3 GiB でした。`StorageEfficiencyEnabled=False` で作成したボリュームですが、ゼロブロックは実割り当てされていないと見られます。またボリューム単位の `StorageUsed` は、AWS ドキュメントの記載どおり**進行中のマルチパートパートを反映しません**（親ファイルシステム側に反映される）。進捗を監視する場合はファイルシステム単位のメトリクスか EC2 の `NetworkOut` を使ってください。

### 使用したリソース（検証後すべて削除済み）

| リソース | 内容 |
|---------|------|
| FSx for ONTAP ボリューム | 150 GiB、UNIX セキュリティスタイル、階層化なし |
| S3 AP | VPC origin、`FileSystemIdentity` = UNIX (`root`) |
| EC2 | `c6in.large`、Amazon Linux 2023、IMDSv2 必須、パブリック IP（SSM 到達用） |
| IAM | 専用ロール（`AmazonSSMManagedInstanceCore` + テスト AP のみにスコープしたインラインポリシー） |
| セキュリティグループ | アウトバウンドのみ（インバウンドルールなし） |

実測コストは EC2 約 1 時間分（約 $0.13）とゼロ埋めデータのため無視できる容量課金のみでした。S3 トラフィックは既存の S3 Gateway エンドポイント経由のため転送課金は発生していません。

---

## 再現手順

検証スクリプトは上限超過の即時拒否を利用するため、**ボリュームにデータを書き込みません**。

```python
# 単一 PutObject の上限判定（Content-Length のみで拒否される）
import boto3
from botocore.config import Config

s3 = boto3.client("s3", region_name="ap-northeast-1",
                  config=Config(signature_version="s3v4",
                                retries={"max_attempts": 1, "mode": "standard"}))

class ZeroStream:
    """固定長のゼロ埋めストリーム（メモリ・ディスクを消費しない）"""
    def __init__(self, size): self._size, self._pos, self.sent = size, 0, 0
    def __len__(self): return self._size
    def seek(self, off, whence=0): self._pos = off if whence == 0 else self._pos + off; return self._pos
    def tell(self): return self._pos
    def read(self, amt=None):
        rem = self._size - self._pos
        if rem <= 0: return b""
        n = rem if amt is None or amt < 0 else min(amt, rem)
        self._pos += n; self.sent += n
        return b"\0" * n

size = 5 * 1024**3 + 1          # 5 GiB + 1
s3.put_object(Bucket="<ap-alias>", Key="probe.bin",
              Body=ZeroStream(size), ContentLength=size)
# -> botocore.exceptions.ClientError: EntityTooLarge
#    ProposedSize=5368709121 / MaxSizeAllowed=5368709120
```

---

## まとめ

| 制約 | 実測値 | 検査タイミング | 超過時のエラー |
|------|-------|--------------|--------------|
| 単一 `PutObject` | **5 GiB**（5,368,709,120） | Content-Length（即時） | 400 `EntityTooLarge` + `MaxSizeAllowed` |
| `UploadPart` 1 パート | **5 GiB**（5,368,709,120） | Content-Length（即時） | 400 `EntityTooLarge` + `MaxSizeAllowed` |
| オブジェクト全体（アップロード） | **50 GiB**（53,687,091,200） | `CompleteMultipartUpload`（全転送後） | 400 `EntityTooLarge`（`MaxSizeAllowed` なし） |
| ダウンロード | 上限なし（AWS ドキュメント記載） | — | — |
| `UploadPartCopy` | 実測では利用不可 | — | 404 `NoSuchKey` |

### アプリケーション実装者への推奨

- **アップロード前にサイズを検証する**。50 GiB 超は転送完了後に失敗するため、クライアント側チェックが唯一の早期検出手段です。
- 5 GiB 超は Multipart Upload が必須。パートサイズ上限も 5 GiB です。
- `CompleteMultipartUpload` は 50 GiB で 9 分強かかる場合があります。`read_timeout` を長めに設定してください。
- サーバーサイドでの大容量オブジェクト組み立て（`UploadPartCopy`）には依存しないでください。

---

## AWS Support への提出内容（2026-08-02 提出済み）

本検証結果を添えて、疑問点の確認と機能／ドキュメント改善要望を AWS Support へ提出しました（Service: FSx for NetApp ONTAP、Category: Feature Request）。ケース番号は本リポジトリには記載しません（`.private/` で追跡）。

### 確認事項（質問）

| # | 内容 |
|---|------|
| Q1 | オブジェクト上限が正確に 50 GiB（53,687,091,200）であること、およびドキュメントの「5 GB」「50 GB」が二進表記であることの確認 |
| Q2 | `UploadPartCopy` が Supported と記載されているのに `NoSuchKey` になるのは不具合か、それとも FSx アタッチ AP 固有の `CopySource` 形式が必要なのか |
| Q3 | 50 GiB の `CompleteMultipartUpload` に約 557 秒かかるのは想定内か。所要時間はオブジェクトサイズかパート数のどちらに比例するか。推奨タイムアウト値の指針 |
| Q4 | AWS Transfer Family のドキュメントが依然 5 GB と記載している件は、Transfer Family 固有の制約か、更新漏れか |
| Q5 | 5 GB → 50 GB の変更はどこかで告知されたか。What's New が見つからず、`doc-history` もリダイレクトされ変更履歴を辿れない |

### 機能／ドキュメント改善要望

| # | 内容 |
|---|------|
| FR-A | **オブジェクトサイズ上限をマルチパートの早い段階で検査してほしい**。現状は 1 バイト超過でも全量転送後に失敗する（本検証では 50 GiB・約 10 分が無駄になった）。`UploadPart` で累積サイズが上限を超える時点で拒否する、または `CreateMultipartUpload` で想定総サイズを申告して事前検証できるようにする |
| FR-B | **`CompleteMultipartUpload` の `EntityTooLarge` にも `ProposedSize` / `MaxSizeAllowed` を含めてほしい**。`PutObject` / `UploadPart` は返すため API 間で不一致。現状クライアントは上限値を 50 GiB 単位の試行錯誤でしか知れない |
| FR-C | **ドキュメント改善**: ①上限を二進単位または正確なバイト数で記載 ②検査タイミングが `CompleteMultipartUpload` である旨を明記 ③大容量時の `CompleteMultipartUpload` 所要時間とタイムアウト要件を記載 ④この種の上限変更の変更履歴を公開 |

---

## 関連ドキュメント

- [S3AP Compatibility Notes](s3ap-compatibility-notes.md) — API 互換性と制約の一覧
- [S3AP Performance Considerations](s3ap-performance-considerations.md) — サイズ別の処理戦略
- [Lambda / HealthOmics S3 AP Gaps](aws-feature-requests/lambda-healthomics-s3ap-gaps.md) — 上限変更の時期調査と AWS への確認事項
- [Access point compatibility (AWS)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Uploading objects (Amazon S3 User Guide)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)
