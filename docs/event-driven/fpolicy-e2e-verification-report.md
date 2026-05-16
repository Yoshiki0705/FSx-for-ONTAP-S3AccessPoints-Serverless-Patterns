# FPolicy E2E 検証レポート

**日付**: 2026-05-13
**検証者**: Kiro (AI) + Yoshiki Fujiwara
**環境**: AWS ap-northeast-1, FSxN ONTAP 9.17.1P6, ECS Fargate

---

## 1. 検証目的

ONTAP FPolicy External Server を ECS Fargate 上に実装し、FSx for NetApp ONTAP の
ファイル操作イベントを AWS サービス（SQS → EventBridge）に連携する E2E パイプラインの
動作確認を行う。

---

## 2. 検証環境

| コンポーネント | 詳細 |
|---|---|
| FSxN ファイルシステム | fs-09ffe72a3b2b7dbbd |
| ONTAP バージョン | 9.17.1P6 |
| SVM | FSxN_OnPre (UUID: 9ae87e42-068a-11f1-b1ff-ada95e61ee66) |
| SVM 管理 IP | 10.0.3.133 |
| FSxN クラスタ管理 IP | 10.0.3.72 |
| Data LIF (fpolicy_client) | 10.0.9.32 (Node-01), 10.0.2.18 (Node-02) |
| Data LIF (nfs/cifs) | 10.0.3.133 (Node-01) |
| ECS Cluster | fsxn-fpolicy-fsxn-fp-srv |
| Fargate Task IP | 10.0.15.111 |
| FPolicy Engine | fpolicy_aws_engine (async, port 9898, xml format) |
| FPolicy Policy | fpolicy_aws (mandatory=false, priority=1) |
| VPC | vpc-0ae01826f906191af (10.0.0.0/16) |

---

## 3. 検証結果サマリー

| テスト項目 | 結果 | 備考 |
|---|---|---|
| ECS Fargate コンテナ起動 | ✅ 成功 | ARM64, Python 3.12 |
| NLB ヘルスチェック | ✅ 成功 | TCP 9898 |
| ONTAP → Fargate 直接 TCP 接続 | ✅ 成功 | state: connected (2 nodes) |
| NEGO_REQ 受信 | ✅ 成功 | 2 ノードから受信 |
| NEGO_RESP 送信 | ✅ 成功 | Version 1.2 |
| KEEP_ALIVE 受信 | ✅ 成功 | 2 分間隔で安定受信 |
| NLB 経由の FPolicy 接続 | ❌ 失敗 | バイナリフレーミング非互換 |
| NFSv4 ファイル作成 → NOTI_REQ | ❌ 未受信 | 接続維持されるがイベント未到着 |
| NFSv4 open/close イベント | ❌ NFS ハング | mandatory=false でもブロック |

---

## 4. 発見した問題と対策

### 4.1 NLB 経由の FPolicy 接続問題（解決済み）

**問題**: ONTAP FPolicy プロトコルは NLB TCP パススルー経由でハンドシェイクが完了しなかった。

**観測結果**: NLB は TCP 接続を確立するが、FPolicy NEGO_REQ/RESP ハンドシェイクが完了しない。

**推定原因**: ONTAP FPolicy の external-engine セッション管理と NLB/Fargate ターゲットパスの相互作用。
ソース IP 保持設定、ヘルスチェック干渉、接続再利用セマンティクスなどが影響している可能性がある。
これは本検証環境での観測結果であり、NLB の一般的な制限として断言するものではない。

**追加検証（2026-05-14）**: `preserve_client_ip.enabled=true` と `false` の両方でテスト。
いずれの設定でも ONTAP は NLB IP に FPolicy 接続を確立できなかった。
NLB IP からの接続は全てヘルスチェック（TCP 接続→即切断）のみ。
ONTAP data LIF からの FPolicy ハンドシェイクは NLB 経由では発生しなかった。
推定原因: ONTAP FPolicy が primary-servers IP への直接 TCP 接続を前提としており、
NLB のターゲットグループ経由のルーティングでは FPolicy セッション確立条件を満たさない。

**対策**: Fargate タスクの直接 Private IP を ONTAP external-engine に指定。NLB はヘルスチェック用途のみ。

### 4.2 タイムアウト競合（解決済み）

**問題**: サーバーの `conn.settimeout(120s)` が ONTAP の `keep_alive_interval(120s)` と同値。
KEEP_ALIVE が届く前にサーバー側がタイムアウトで切断。

**対策**: `conn.settimeout(300s)` に変更。KEEP_ALIVE を安定受信できるようになった。

### 4.3 NFS バージョン不一致（解決済み）

**問題**: Linux のデフォルト NFS マウントは NFSv4.2 だが、FPolicy イベントは `nfsv3` で設定。

**対策**: `nfsv4` プロトコルのイベントを追加作成。

### 4.4 NFSv4 open/close イベントによる NFS ハング（解決済み）

**問題**: FPolicy イベントに `open: true` / `close: true` を設定すると、
`mandatory: false` + 非同期モードでも NFS ファイル操作がハングする。

**原因**: NFSv4 の open/close は ONTAP 内部で同期的に処理される可能性がある。
または、FPolicy サーバーが SCREEN_RESP を返さないため ONTAP がタイムアウトまで待機。

**対策**: `open`/`close` をイベントから除外し、`create`/`write`/`delete`/`rename` のみ監視。

### 4.5 NOTI_REQ 未受信（未解決）

**問題**: ONTAP は `connected` + KEEP_ALIVE 成功だが、ファイル操作時に NOTI_REQ を送信しない。

**考えられる原因**:
1. NFSv4 の非同期 FPolicy で `create`/`write` イベントが発火する条件が不明
2. Shengyu 氏の検証は SMB (CIFS) プロトコルで実施。NFSv4 での動作は未検証
3. ONTAP の Persistent Store 機能が必要な可能性（ONTAP 9.14.1+）
4. `volume_monitoring: true` の設定が必要な可能性
5. FPolicy の `passthrough-read` 設定が関連する可能性

**次のアクション**:
- Shengyu 氏に NFSv4 での FPolicy 非同期通知の動作条件を確認
- SMB (CIFS) でのテスト（CIFS サーバー設定が必要）
- Persistent Store の設定を試す
- `volume_monitoring: true` を試す

---

## 5. VPC Endpoints 要件

ECS Fargate (Private Subnet) で FPolicy Server を稼働させるには以下が必須:

| Endpoint | Type | 用途 |
|----------|------|------|
| `com.amazonaws.ap-northeast-1.ecr.dkr` | Interface | コンテナイメージプル |
| `com.amazonaws.ap-northeast-1.ecr.api` | Interface | ECR 認証トークン |
| `com.amazonaws.ap-northeast-1.s3` | Gateway | ECR イメージレイヤー |
| `com.amazonaws.ap-northeast-1.logs` | Interface | CloudWatch Logs |
| `com.amazonaws.ap-northeast-1.sts` | Interface | IAM ロール認証 |
| `com.amazonaws.ap-northeast-1.sqs` | Interface | SQS メッセージ送信 |

**Security Group 要件**:
- VPC Endpoint SG: TCP 443 from 10.0.0.0/16
- FPolicy Server SG: TCP 9898 from 10.0.0.0/16（NLB ヘルスチェック + ONTAP data LIF）

---

## 6. NetApp FPolicy 技術資料リンク

### 公式ドキュメント

| 資料 | URL | ポイント |
|------|-----|---------|
| FPolicy 概要 | https://docs.netapp.com/us-en/ontap/nas-audit/two-parts-fpolicy-solution-concept.html | FPolicy の 2 つの構成要素（ネイティブ/外部） |
| 同期/非同期通知 | https://docs.netapp.com/us-en/ontap/nas-audit/synchronous-asynchronous-notifications-concept.html | 非同期モードではレスポンス不要、ネットワーク障害時は最大 10 分バッファ |
| 外部サーバーとの連携 | https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-external-fpolicy-servers-concept.html | 制御チャネル、特権データアクセス、ポリシー処理順序 |
| ノード間通信プロセス | https://docs.netapp.com/us-en/ontap/nas-audit/node-fpolicy-server-communication-process-concept.html | **data LIF 経由で接続確立**、LIF 移行時の再接続動作 |
| 外部エンジン設定計画 | https://docs.netapp.com/us-en/ontap/nas-audit/plan-fpolicy-external-engine-config-concept.html | エンジンパラメータ一覧、タイムアウト設定、keep-alive 間隔 |
| 要件とベストプラクティス | https://docs.netapp.com/us-en/ontap/nas-audit/requirements-best-practices-fpolicy-concept.html | data-fpolicy-client LIF サービス（ONTAP 9.8+） |
| Persistent Store | https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html | 非同期・非必須ポリシー用イベント永続化（ONTAP 9.14.1+） |
| FPolicy 設定手順 | https://docs.netapp.com/us-en/ontap/nas-audit/steps-setup-fpolicy-config-concept.html | 設定フロー全体像 |
| 外部エンジン作成 | https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-external-engine-task.html | CLI コマンド詳細 |
| FPolicy セキュリティ強化 | https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/create-fpolicy.html | Technical Report: セキュリティ観点での FPolicy |

### REST API リファレンス

| 資料 | URL | ポイント |
|------|-----|---------|
| FPolicy Engine API | https://docs.netapp.com/us-en/ontap-restapi-9161/manage_fpolicy_engine_configuration.html | xml/protobuf フォーマット、同期/非同期タイプ |
| FPolicy Event API | https://docs.netapp.com/us-en/ontap-restapi-98/ontap/protocols_fpolicy_svm.uuid_events_endpoint_overview.html | プロトコル別イベント設定 |
| FPolicy Persistent Store API | https://docs.netapp.com/us-en/ontap-restapi-9151/manage_fpolicy_persistent_store_configuration.html | Persistent Store 設定 |

### KB 記事

| 資料 | URL | ポイント |
|------|-----|---------|
| Select Timed out エラー | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Node_failed_to_establish_a_connection_with_the_FPolicy_server_reason_Select_Timed_out_because_Collector_Name_is_wrong | 接続タイムアウトのトラブルシューティング |
| FPolicy FAQ | https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing | FPolicy 全般の FAQ |

### 参考実装

| 資料 | URL | ポイント |
|------|-----|---------|
| Shengyu Fang - FPolicy魔改造① | https://qiita.com/Shengyu/items/e85ef10815c00c79cfcd | Near-real-time + Batch 構成、SMB テスト |
| Shengyu Fang - FPolicy魔改造② | https://qiita.com/Shengyu/items/bb742a7b2507e24aaaad | Request ベースのログクエリ |
| GitHub: ontap-fpolicy-aws-integration | https://github.com/YhunerFSY/ontap-fpolicy-aws-integration | TCP サーバー実装、SQS 連携 |

---

## 7. FPolicy プロトコル仕様の重要ポイント

### 7.1 通信フロー

```
ONTAP Node (data LIF)
  │
  │ TCP connect (port 9898)
  ▼
FPolicy External Server
  │
  ├─ NEGO_REQ → NEGO_RESP (ハンドシェイク、必須)
  ├─ KEEP_ALIVE_REQ (定期、レスポンス不要)
  ├─ STATUS_REQ (定期、レスポンス不要 for async)
  ├─ NOTI_REQ (ファイルイベント、レスポンス不要 for async)
  └─ SCREEN_REQ (ファイルスクリーニング、同期モードのみ)
```

### 7.2 メッセージフレーミング

```
Frame = b'"' + struct.pack('>I', payload_length) + b'"' + payload
Payload = Header_XML + b'\n\n' + Body_XML + b'\x00'
```

### 7.3 エンジンフォーマット

| フォーマット | ONTAP バージョン | 説明 |
|---|---|---|
| xml | 全バージョン | デフォルト、XML 形式の通知 |
| protobuf | 9.15.1+ | Google Protobuf バイナリ形式（高性能） |

### 7.4 非同期モードの動作

- ONTAP はレスポンスを待たずにファイル操作を続行
- ネットワーク障害時は最大 10 分間ストレージノードにバッファ
- Persistent Store（9.14.1+）でイベントを永続化可能
- `mandatory: false` でもサーバー未接続時はイベントをドロップ

### 7.5 LIF サービスの分離（ONTAP 9.8+）

```
data-fpolicy-client サービス: FPolicy 通知送信用 LIF
data-nfs / data-cifs サービス: NFS/SMB データアクセス用 LIF
```

これらは異なる LIF に割り当てられる場合がある。FPolicy 接続は `data-fpolicy-client` LIF から確立される。

### 7.6 NFSv4 の注意事項

- NFSv4 は `open`/`close` セマンティクスを持つ（NFSv3 にはない）
- FPolicy で `open`/`close` を監視すると、非同期モードでも NFS 操作がブロックされる場合がある
- NFSv4 の `create` は `OPEN` RPC の一部として処理される
- `write` イベントは全ての書き込みで発火するため、`first-write` フィルタ推奨

---

## 8. 今後の調査方針

### 優先度 1: SMB (CIFS) でのテスト

Shengyu 氏の実装は SMB で検証済み。CIFS サーバーを設定して SMB 経由でファイル作成し、
NOTI_REQ が受信できるか確認する。これにより NFSv4 固有の問題か、設定全般の問題かを切り分けられる。

### 優先度 2: Persistent Store の設定

ONTAP 9.14.1+ の Persistent Store を設定し、イベントが永続化されるか確認する。
Persistent Store が有効な場合、サーバー接続時にバッファされたイベントが送信される。

```bash
# Persistent Store 作成
fpolicy persistent-store create \
  -vserver FSxN_OnPre \
  -persistent-store fpolicy_store \
  -volume <dedicated_volume>
```

### 優先度 3: volume_monitoring の有効化

```bash
# イベントの volume_monitoring を true に設定
fpolicy policy event modify \
  -vserver FSxN_OnPre \
  -event-name fpolicy_nfsv4_events \
  -volume-monitoring true
```

### 優先度 4: Shengyu 氏との協力

- NFSv4 での FPolicy 非同期通知の動作条件を確認
- ONTAP 9.17.1 での既知の制限事項を確認
- protobuf フォーマットでの動作確認

---

## 9. 検証で確立したインフラ

以下のリソースは検証用に残存（Phase 11 で継続使用）:

| リソース | 識別子 | 用途 |
|----------|--------|------|
| ECS Cluster | fsxn-fpolicy-fsxn-fp-srv | FPolicy Server |
| ECS Service | fsxn-fpolicy-server-fsxn-fp-srv | Fargate タスク管理 |
| NLB | fp-nlb-fsxn-fp-srv | ヘルスチェック |
| ECR Repository | fsxn-fpolicy-server | コンテナイメージ |
| SQS Queue | fsxn-fpolicy-ingestion-fsxn-fpolicy-ingestion | イベント受信 |
| CloudFormation Stack | fsxn-fp-srv | ECS + NLB |
| CloudFormation Stack | fsxn-fpolicy-ingestion | SQS + Lambda |
| 踏み台 EC2 | i-01238b758ee7a28e2 | VPC 内アクセス |
| VPC Endpoints | 5 個 (ECR, S3, Logs, STS) | Fargate 通信 |

---

## 10. E2E 成功検証結果（2026-05-13 最終）

### 10.1 NFSv3 E2E 成功

**完全な E2E パイプラインが動作確認済み:**

```
NFSv3 ファイル作成 (tee /mnt/fsxn/file.txt)
  → ONTAP FPolicy NOTI_REQ 送信
    → Fargate FPolicy Server 受信 [Event] create \file.txt
      → SQS SendMessage 成功 [SQS] Sent
        → SQS メッセージ到達確認
```

**SQS に到達したメッセージ:**
```json
{
  "event_id": "1fc1fb7b-c89b-480b-8c61-92a9e912b0ba",
  "operation_type": "create",
  "file_path": "\\NFSV3-FPOLICY-FINAL.txt",
  "volume_name": "unknown",
  "svm_name": "unknown",
  "timestamp": "2026-05-13T13:53:09.871584+00:00",
  "file_size": 0,
  "client_ip": "10.0.10.67"
}
```

### 10.2 動作確認済み ONTAP 設定

> **Note**: 以下は検証時に使用したコマンド。ONTAP 9.11+ では `vserver` プレフィックスなしの形式を推奨。

```bash
# Engine
fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers 10.0.15.111 \
  -port 9898 \
  -extern-engine-type asynchronous

# Event (NFSv3 — create/write/delete/rename のみ)
fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name nfsv3_file_events \
  -protocol nfsv3 \
  -file-operations create,write,delete,rename

# Policy
fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events nfsv3_file_events \
  -engine fpolicy_aws_engine \
  -is-mandatory false

# Scope
fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include kodera_snowflake_testap

# Enable
fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 10.3 NFSv4 バージョン別検証結果（解決済み）

**根本原因**: `mount -o vers=4` で Linux クライアントが NFSv4.2 にネゴシエートしていた。
FPolicy は NFSv4.2 を非サポート（NetApp KB + ONTAP NFS 管理ドキュメントに明記）。

**決定的テスト（2026-05-14）**:

| NFS バージョン | マウントオプション | NOTI_REQ | 結果 |
|---|---|---|---|
| NFSv3 | `vers=3` | ✅ 即座に受信 | 動作する |
| NFSv4.0 | `vers=4.0` | ✅ 即座に受信 | **動作する** |
| NFSv4.1 | `vers=4.1` | ✅ 即座に受信 | **動作する** |
| NFSv4.2 | `vers=4.2` | ❌ 送信されない | **非サポート（期待動作）** |
| NFSv4 (auto) | `vers=4` | ❌ 送信されない | 4.2 にネゴシエート |

**推奨**: `mount -o vers=4.1` を明示指定。`vers=4` は使用しない。

**参考**: [NetApp KB: FPolicy Auditing FAQ](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing)

### 10.4 SQS VPC Endpoint の必要性

FPolicy Server (Fargate) から SQS にメッセージを送信するには、SQS VPC Endpoint が必須。
これがないと SQS 送信がタイムアウトし、イベントは受信できるが転送できない。

追加した VPC Endpoint: `vpce-01e38c584a1766f3b` (com.amazonaws.ap-northeast-1.sqs)

### 10.5 パス抽出のバグ（軽微）

ONTAP からの NOTI_REQ の body に含まれるパス情報が XML タグ付きで送信される:
```xml
<PathNameType>WIN_NAME</PathNameType><PathName>\NFSV3-FPOLICY-FINAL.txt</PathName>
```

現在の `handle_noti_req` は `<Path>` または `<PathName>` タグを正規表現で抽出するが、
`<PathNameType>` タグも含まれるため、抽出結果に XML が残る。→ **セクション 11.1 で修正済み**

---

## 11. Phase 10 残課題 完了報告（2026-05-14）

### 11.1 FPolicy Server パス抽出バグ修正 ✅

**修正内容**:
- `_extract_xml_value()` ヘルパーメソッドを追加（複数タグ名フォールバック + 残留 XML タグ除去）
- `handle_noti_req()` を全面リファクタリング
- `re.DOTALL | re.IGNORECASE` で堅牢な XML パース

**修正前 SQS メッセージ**:
```json
{"file_path": "<PathNameType>WIN_NAME</PathNameType><PathName>\\NFSV3-CONTROL.txt</PathName>"}
```

**修正後 SQS メッセージ**:
```json
{"file_path": "test-final-1778707759.txt"}
```

### 11.2 volume_name / svm_name 修正 ✅

**修正内容**:
- NEGO_REQ セッションコンテキストから SVM 名を取得
- 環境変数 `SVM_NAME` / `VOLUME_NAME` によるフォールバック
- ECS タスク定義に環境変数追加（revision 3）

**修正後 SQS メッセージ**:
```json
{"volume_name": "vol1", "svm_name": "FSxN_OnPre"}
```

### 11.3 EventBridge 連携テスト ✅

**デプロイ済みスタック**: `fsxn-fpolicy-routing`

**E2E フロー確認**:
```
FPolicy Server → SQS → Bridge Lambda → EventBridge Custom Bus → CloudWatch Logs
```

**EventBridge イベント（実際の出力）**:
```json
{
  "detail-type": "FPolicy File Operation",
  "source": "fsxn.fpolicy",
  "detail": {
    "event_id": "2175e878-1e0c-48ef-a8b3-53664d5d5b06",
    "operation_type": "create",
    "file_path": "test-eb-e2e-1778707951.txt",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-05-13T21:32:37.680626+00:00",
    "client_ip": "10.0.10.67"
  }
}
```

### 11.4 Fargate タスク IP 自動更新 ✅

**実装**:
- Lambda: `shared/lambdas/fpolicy_engine/handler.py`
- CFn テンプレート: `shared/cfn/fpolicy-ip-updater.yaml`
- S3 パッケージ: `s3://fsxn-eda-deploy-178625946981/fpolicy-ip-updater/fpolicy_engine.zip`

**動作フロー**:
```
ECS Task State Change (RUNNING)
  → EventBridge Rule
    → IP Updater Lambda
      → ONTAP REST API: disable policy → update engine → enable policy
```

### 11.5 Persistent Store 検討 ✅

**ドキュメント作成**: `docs/event-driven/fpolicy-persistent-store.md`

**結論**: 現状は IP 自動更新 Lambda により再接続が自動化されているため、
短時間のイベントロスが許容できる場合は Persistent Store 不要。
コンプライアンス要件がある場合のみ導入を推奨。

### 11.6 ECS on EC2 テンプレート ✅

**テンプレート作成**: `shared/cfn/fpolicy-server-ec2.yaml`

**特徴**:
- t4g.micro (ARM64 Graviton) — コスト最適化
- 固定 Private IP — ONTAP engine 更新不要
- SSM 対応 — SSH 不要でリモートアクセス可能
- Docker コンテナとして FPolicy Server を実行

### 11.7 AWS リソースクリーンアップ ✅

**削除済み**:
| リソース | 識別子 | 状態 |
|----------|--------|------|
| AWS Managed AD | d-956793459d | 削除済み |
| 踏み台 EC2 | i-01238b758ee7a28e2 | terminated |
| キーペア | fpolicy-bastion-v2 | 削除済み |
| SG SSH ルール | sg-0de66457f7a14d614 (0.0.0.0/0:22) | revoked |
| SG SSH ルール | sg-027fffe41bcb28111 (0.0.0.0/0:22) | revoked |
| EventBridge テストルール | fsxn-fpolicy-test-rule | 削除済み |

**残存（デモ環境）**:
| リソース | 識別子 | 用途 |
|----------|--------|------|
| ECS Cluster | fsxn-fpolicy-fsxn-fp-srv | FPolicy Server |
| Fargate Task | revision 3 (IP: 10.0.13.33) | 稼働中 |
| SQS Queue | fsxn-fpolicy-ingestion-fsxn-fpolicy-ingestion | イベント受信 |
| EventBridge Bus | fsxn-fpolicy-events | イベントルーティング |
| Bridge Lambda | fsxn-fpolicy-bridge-fsxn-fpolicy-routing | SQS→EB 転送 |
| VPC Endpoints | ECR, S3, Logs, STS, SQS | Fargate 通信 |

---

## 12. 最終アーキテクチャ（Phase 10 完了時点）

```
┌─────────────────────────────────────────────────────────────────┐
│ FSx for NetApp ONTAP (SVM: FSxN_OnPre)                          │
│                                                                 │
│  FPolicy Engine: fpolicy_aws_engine                             │
│  ├─ primary_servers: 10.0.13.33 (Fargate Task IP)              │
│  ├─ port: 9898                                                  │
│  ├─ type: asynchronous                                          │
│  └─ format: xml                                                 │
│                                                                 │
│  FPolicy Policy: fpolicy_aws                                    │
│  ├─ events: nfsv3/nfsv4 create,write,delete,rename             │
│  ├─ mandatory: false                                            │
│  └─ priority: 1                                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ TCP 9898 (NOTI_REQ)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ ECS Fargate (fsxn-fpolicy-fsxn-fp-srv)                          │
│                                                                 │
│  FPolicy Server Container (ARM64, Python 3.12)                  │
│  ├─ XML パース + パス抽出 (_extract_xml_value)                  │
│  ├─ SVM/Volume 名解決 (env var fallback)                        │
│  └─ SQS SendMessage                                             │
└────────────────────────┬────────────────────────────────────────┘
                         │ SQS SendMessage
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ SQS: fsxn-fpolicy-ingestion-fsxn-fpolicy-ingestion              │
└────────────────────────┬────────────────────────────────────────┘
                         │ Event Source Mapping
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Lambda: fsxn-fpolicy-bridge-fsxn-fpolicy-routing                │
│  └─ PutEvents → EventBridge                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ PutEvents
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ EventBridge Custom Bus: fsxn-fpolicy-events                     │
│  ├─ source: fsxn.fpolicy                                        │
│  ├─ detail-type: FPolicy File Operation                         │
│  └─ Rules → UC 別ターゲット (Lambda, Step Functions, etc.)      │
└─────────────────────────────────────────────────────────────────┘
```
