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

### 4.1 NLB 非互換（解決済み）

**問題**: ONTAP FPolicy プロトコルは NLB TCP パススルー経由で動作しない。

**原因**: FPolicy はバイナリフレーミング（`"` + 4バイト big-endian 長 + `"` + payload）を使用。
NLB が TCP 接続を確立した後、このフレーミングデータを正しく中継できない。

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
vserver fpolicy persistent-store create \
  -vserver FSxN_OnPre \
  -persistent-store fpolicy_store \
  -volume <dedicated_volume>
```

### 優先度 3: volume_monitoring の有効化

```bash
# イベントの volume_monitoring を true に設定
vserver fpolicy policy event modify \
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
