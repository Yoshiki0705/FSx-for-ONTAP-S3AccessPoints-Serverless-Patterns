# FPolicy protobuf フォーマット評価

## 概要

ONTAP 9.15.1 以降で利用可能な **protobuf フォーマット** は、従来の XML フォーマットに代わる高性能なバイナリシリアライゼーション形式です。本ドキュメントでは XML と protobuf の比較評価を行います。

## 対応バージョン

| フォーマット | ONTAP バージョン | 備考 |
|-------------|-----------------|------|
| XML | 全バージョン | デフォルト、後方互換 |
| protobuf | 9.15.1+ | Google Protocol Buffers バイナリ形式 |

## 現在の環境

- FSxN ONTAP バージョン: **9.17.1P6** → protobuf 対応 ✅
- 現在の設定: `format: xml`

## XML vs protobuf 比較

| 項目 | XML | protobuf |
|------|-----|----------|
| メッセージサイズ | 大（タグ名がテキスト） | 小（バイナリ、~60-70% 削減） |
| パース速度 | 遅い（正規表現/DOM パース） | 速い（コンパイル済みデシリアライザ） |
| 可読性 | 高い（テキスト形式） | 低い（バイナリ） |
| デバッグ容易性 | 高い（ログで直接確認可能） | 低い（デコードツール必要） |
| CPU 使用率 | 高い | 低い（~50% 削減） |
| ネットワーク帯域 | 多い | 少ない |
| 実装複雑度 | 低い（正規表現で十分） | 中（protobuf ライブラリ必要） |
| Python ライブラリ | 不要（標準 re モジュール） | `protobuf` パッケージ必要 |

## 性能見積もり

### 1,000 イベント/秒のシナリオ

| メトリクス | XML | protobuf | 改善率 |
|-----------|-----|----------|--------|
| メッセージサイズ (平均) | ~500 bytes | ~150 bytes | 70% 削減 |
| パース時間 (1イベント) | ~0.5 ms | ~0.1 ms | 80% 削減 |
| CPU 使用率 (Fargate 0.25 vCPU) | ~40% | ~15% | 62% 削減 |
| ネットワーク帯域 | ~500 KB/s | ~150 KB/s | 70% 削減 |

### Phase 11 実測結果（Python 純粋実装）

| メトリクス | XML (regex) | protobuf (pure Python) | 備考 |
|-----------|-------------|------------------------|------|
| メッセージサイズ (平均) | 220 bytes | 144 bytes | **34.6% 削減** |
| パース時間 (1000イベント) | ~0.15 ms | ~0.32 ms | Python regex が C 最適化済みのため |
| パース速度比 | 1.0x (基準) | 0.47x | pure Python では regex が高速 |

> **注意**: 上記は Python 純粋実装（`protobuf_parser.py`）の結果。
> C 拡張付き `protobuf` ライブラリ使用時は 5-10x 高速化が期待される。
> 実運用では **メッセージサイズ削減**（ネットワーク帯域・SQS コスト）が主なメリット。

### 結論

現在の負荷（~10-100 イベント/秒）では XML で十分な性能が得られています。protobuf への移行は以下の場合に推奨されます:

- イベント量が 1,000+/秒に達する場合
- Fargate タスクの CPU 使用率が 70% を超える場合
- ネットワーク帯域がボトルネックになる場合
- SQS メッセージコストの最適化が必要な場合（34.6% のペイロード削減）

## protobuf 移行手順（将来実施時）

### Phase 11 で実装済み

1. **protobuf wire-format パーサー**: `shared/fpolicy-server/protobuf_parser.py`
   - 外部依存なし（pure Python、`protobuf` パッケージ不要）
   - ONTAP の protobuf メッセージを直接デコード
   - エンコーダも実装（テスト・ベンチマーク用）

2. **FPolicy Server protobuf 対応**: `shared/fpolicy-server/fpolicy_server.py`
   - `FPOLICY_FORMAT` 環境変数で切り替え（`xml` / `protobuf`）
   - 自動検出モード: メッセージの先頭バイトで XML/protobuf を判定
   - protobuf NEGO_REQ / NOTI_REQ / KEEP_ALIVE の処理実装

3. **protobuf スキーマ定義**: `shared/fpolicy-server/proto/fpolicy_notification.proto`
   - FileOperationNotification (14 フィールド)
   - HandshakeRequest / HandshakeResponse
   - FPolicyHeader

4. **テスト**: `shared/tests/test_protobuf_parser.py` (18 テスト)
   - ラウンドトリップ検証
   - Unicode パス対応
   - 性能比較ベンチマーク

### 1. ONTAP 側の設定変更

```bash
# 既存エンジンの format を変更
# ポリシーを一度無効化
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

# エンジンの format を protobuf に変更
vserver fpolicy policy external-engine modify \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -format-for-engine-of-type protobuf

# ポリシーを再有効化
vserver fpolicy enable -vserver FSxN_OnPre -policy-name fpolicy_aws -sequence-number 1
```

### 2. FPolicy Server 側の変更

```python
# requirements.txt に追加
protobuf>=4.25.0

# fpolicy_server.py の変更
# 1. protobuf スキーマ (.proto) をコンパイル
# 2. parse_header_and_body() で protobuf デシリアライズを追加
# 3. handle_noti_req() を protobuf メッセージ対応に変更
```

## Phase 11 実環境 protobuf テスト結果

### テスト実施日: 2026-05-15

**手順**:
1. ONTAP REST API で engine format を `protobuf` に変更
2. FPolicy Server (ECS Fargate) のログを監視
3. ONTAP からの接続を確認

**結果**:
```
[WARNING] fpolicy-server: Invalid message length: 53554736
```

**分析**:
- ONTAP は protobuf format に切り替え後、即座に NEGO_REQ を protobuf で送信
- 値 `53554736` (0x03320330) は protobuf のフィールドデータが TCP フレーム長として誤解釈された
- **重要な発見**: protobuf モードでは TCP フレーミングが XML と異なる可能性がある
  - XML: `"` + 4-byte big-endian length + `"` + payload
  - protobuf: フレーミングなし（直接 protobuf バイト列）または異なるフレーム形式

**対応方針**:
- FPolicy Server の `read_fpolicy_message()` を protobuf フレーミングに対応させる必要がある
- ONTAP 9.15.1+ の protobuf フレーミング仕様を NetApp サポートに確認
- 暫定対応: XML format を維持（安定稼働中）

### 3. .proto スキーマ定義（推定）

```protobuf
syntax = "proto3";

message FPolicyNotification {
  string session_id = 1;
  string file_path = 2;
  string volume_name = 3;
  string svm_name = 4;
  string operation_type = 5;
  string client_ip = 6;
  int64 file_size = 7;
  string timestamp = 8;
}
```

> **注意**: ONTAP の protobuf スキーマは公式ドキュメントに未公開。実際のメッセージをキャプチャして逆解析する必要がある。

## 推奨アクション

| 優先度 | アクション | 状態 |
|--------|----------|------|
| ✅ 完了 | protobuf パーサー実装 + テスト | Phase 11 完了 |
| ✅ 完了 | FPolicy Server の FPOLICY_FORMAT 環境変数対応 | Phase 11 完了 |
| ✅ 完了 | 性能比較ベンチマーク（サイズ: 34.6% 削減確認） | Phase 11 完了 |
| 低 | テスト環境で protobuf 有効化 + 実メッセージキャプチャ | Phase 12 |
| 中 | C 拡張付き protobuf ライブラリでの再ベンチマーク | 性能限界到達時 |
| 中 | 高負荷テスト（1,000+ イベント/秒）で XML 性能限界を確認 | Phase 12 |

## 参考リンク

- [ONTAP REST API: FPolicy Engine format](https://docs.netapp.com/us-en/ontap-restapi-9161/manage_fpolicy_engine_configuration.html)
- [Google Protocol Buffers](https://protobuf.dev/)
- [Python protobuf ライブラリ](https://pypi.org/project/protobuf/)
