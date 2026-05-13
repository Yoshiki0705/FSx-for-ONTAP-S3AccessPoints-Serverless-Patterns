# FPolicy 設定リファレンス — プロトコル別コマンド例と考慮点

**出典**: [NetApp ONTAP CLI Reference — vserver fpolicy policy event create](https://docs.netapp.com/us-en/ontap-cli-991/vserver-fpolicy-policy-event-create.html)

---

## 1. 外部エンジン作成（全プロトコル共通）

```bash
# 非同期モード（推奨: イベント駆動パイプライン用）
vserver fpolicy policy external-engine create \
  -vserver <SVM_NAME> \
  -engine-name fpolicy_aws_engine \
  -primary-servers <FPOLICY_SERVER_IP> \
  -port 9898 \
  -extern-engine-type asynchronous \
  -ssl-option no-auth

# 同期モード（ファイルブロッキング/スクリーニング用）
vserver fpolicy policy external-engine create \
  -vserver <SVM_NAME> \
  -engine-name fpolicy_sync_engine \
  -primary-servers <FPOLICY_SERVER_IP> \
  -port 9898 \
  -extern-engine-type synchronous \
  -ssl-option no-auth
```

### 考慮点
- `asynchronous`: ONTAP はレスポンスを待たずにファイル操作を続行。イベント駆動パイプラインに最適
- `synchronous`: ONTAP はレスポンスを待つ。ファイルブロッキング/ウイルススキャンに使用
- `-ssl-option no-auth`: 本番環境では `server-auth` または `mutual-auth` を推奨
- `-primary-servers`: 複数指定可能（ラウンドロビン負荷分散）

---

## 2. SMB (CIFS) イベント設定

### 2.1 基本設定例

```bash
# ファイル作成・変更・削除の監視（最小構成）
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name cifs_basic_events \
  -protocol cifs \
  -file-operations create,write,delete,rename

# 全操作監視（監査用）
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name cifs_audit_events \
  -protocol cifs \
  -file-operations open,close,create,delete,read,write,rename,setattr \
  -filters first-read,first-write,close-with-modification
```

### 2.2 サポートされる file-operations と filters

| File Operation | サポートされる Filters |
|---|---|
| `close` | monitor-ads, close-with-modification, close-without-modification, offline-bit, close-with-read, exclude-directory |
| `create` | monitor-ads, offline-bit |
| `create_dir` | (none) |
| `delete` | monitor-ads, offline-bit |
| `delete_dir` | (none) |
| `getattr` | offline-bit, exclude-directory |
| `open` | monitor-ads, offline-bit, open-with-delete-intent, open-with-write-intent, exclude-directory |
| `read` | monitor-ads, first-read, offline-bit |
| `write` | monitor-ads, first-write, offline-bit, write-with-size-change |
| `rename` | offline-bit, monitor-ads |
| `rename_dir` | (none) |
| `setattr` | offline-bit, monitor-ads, setattr-with-owner-change, setattr-with-group-change, setattr-with-sacl-change, setattr-with-dacl-change, setattr-with-modify-time-change, setattr-with-access-time-change, setattr-with-creation-time-change, setattr-with-size-change, setattr-with-allocation-size-change, exclude-directory |

### 2.3 SMB 固有の考慮点

- **`open`/`close` が使用可能**: SMB はステートフルプロトコルのため、open/close セマンティクスが明確
- **`first-read`/`first-write` フィルタ**: CIFS セッション内の最初の read/write のみ通知（通知量削減）
- **`monitor-ads`**: Alternate Data Stream の監視（NTFS 固有機能）
- **Shengyu 氏の検証**: SMB で動作確認済み。`create` イベントでファイル作成を検知
- **AD 必須**: SMB 認証には Active Directory が必要。`fsxadmin` ユーザーでは SMB 認証不可
- **AWS Managed Microsoft AD**: FSxN SVM を AD に参加させる必要がある

#### SMB テスト環境構築手順

```bash
# 1. AWS Managed Microsoft AD 作成
aws ds create-microsoft-ad \
  --name corp.example.com \
  --short-name CORP \
  --password <AD_ADMIN_PASSWORD> \
  --vpc-settings VpcId=vpc-xxx,SubnetIds=subnet-aaa,subnet-bbb \
  --edition Standard \
  --region ap-northeast-1

# 2. FSxN SVM を AD に参加
vserver cifs create \
  -vserver <SVM_NAME> \
  -cifs-server <CIFS_SERVER_NAME> \
  -domain corp.example.com \
  -ou "OU=Computers,DC=corp,DC=example,DC=com"

# 3. SMB 共有作成
vserver cifs share create \
  -vserver <SVM_NAME> \
  -share-name vol1 \
  -path /vol1

# 4. テスト（AD ユーザーで認証）
smbclient //SVM_IP/vol1 -U 'CORP\admin%password' -c 'put test.txt'
```

---

## 3. NFSv3 イベント設定

### 3.1 基本設定例

```bash
# ファイル作成・変更・削除の監視
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name nfsv3_basic_events \
  -protocol nfsv3 \
  -file-operations create,write,delete,rename

# first-write フィルタ付き（通知量削減）
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name nfsv3_filtered_events \
  -protocol nfsv3 \
  -file-operations create,write,delete,rename \
  -filters first-write
```

### 3.2 サポートされる file-operations と filters

| File Operation | サポートされる Filters |
|---|---|
| `create` | offline-bit |
| `create_dir` | (none) |
| `delete` | offline-bit |
| `delete_dir` | (none) |
| `link` | offline-bit |
| `lookup` | offline-bit, exclude-directory |
| `read` | offline-bit, first-read |
| `write` | offline-bit, write-with-size-change, first-write |
| `rename` | offline-bit |
| `rename_dir` | (none) |
| `setattr` | offline-bit, setattr-with-owner-change, setattr-with-group-change, setattr-with-modify-time-change, setattr-with-access-time-change, setattr-with-mode-change, setattr-with-size-change, exclude-directory |
| `symlink` | offline-bit |

### 3.3 NFSv3 固有の考慮点

- **`open`/`close` は非サポート**: NFSv3 はステートレスプロトコルのため open/close セマンティクスがない
- **`first-write` フィルタの動作**: `-file-session-io-grouping-count` と `-file-session-io-grouping-duration` で制御される
- **Write-complete 問題**: NFSv3 では `create` イベント受信時にファイル書き込みが完了していない可能性がある
- **対策**: 遅延処理（数秒待機）または rename パターン（.tmp → 最終名）を使用

---

## 4. NFSv4 イベント設定

### 4.1 基本設定例

```bash
# ファイル作成・変更・削除の監視（open/close なし — 推奨）
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name nfsv4_basic_events \
  -protocol nfsv4 \
  -file-operations create,write,delete,rename

# close イベント付き（ファイル完了検知用）
# 注意: 非同期モードでも NFS 操作がブロックされる場合がある
vserver fpolicy policy event create \
  -vserver <SVM_NAME> \
  -event-name nfsv4_with_close_events \
  -protocol nfsv4 \
  -file-operations create,write,delete,rename,close \
  -filters close-with-modification
```

### 4.2 サポートされる file-operations と filters

| File Operation | サポートされる Filters |
|---|---|
| `close` | offline-bit, exclude-directory |
| `create` | offline-bit |
| `create_dir` | (none) |
| `delete` | offline-bit |
| `delete_dir` | (none) |
| `getattr` | offline-bit, exclude-directory |
| `link` | offline-bit |
| `lookup` | offline-bit, exclude-directory |
| `open` | offline-bit, exclude-directory |
| `read` | offline-bit, first-read |
| `write` | offline-bit, write-with-size-change, first-write |
| `rename` | offline-bit |
| `rename_dir` | (none) |
| `setattr` | offline-bit, setattr-with-owner-change, setattr-with-group-change, setattr-with-sacl-change, setattr-with-dacl-change, setattr-with-modify-time-change, setattr-with-access-time-change, setattr-with-size-change, exclude-directory |
| `symlink` | offline-bit |

### 4.3 NFSv4 固有の考慮点

- **`open`/`close` がサポートされる**: NFSv4 はステートフルプロトコル
- **⚠️ 重要**: `open`/`close` を FPolicy イベントに含めると、`mandatory: false` + 非同期モードでも **NFS 操作がブロックされる場合がある**（Phase 10 検証で確認）
- **⚠️⚠️ 致命的**: Phase 10 最終検証で判明 — NFSv4 では `create`/`write`/`delete`/`rename` のみの設定でも **NFS 操作がブロックされる**。`open`/`close` を除外しても解決しない
- **結論**: **NFSv4 は FPolicy 外部サーバーモードでは使用不可**（少なくとも ONTAP 9.17.1 + 非同期モードの組み合わせでは）
- **推奨**: NFSv3 でマウントする（`mount -t nfs -o vers=3`）
- **`close-with-modification` フィルタ**: close 時に変更があった場合のみ通知（使用する場合）

---

## 5. ポリシー・スコープ・有効化（全プロトコル共通）

### 5.1 ポリシー作成

```bash
# 非同期・非必須ポリシー（イベント駆動パイプライン用）
vserver fpolicy policy create \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -events <EVENT_NAME_1>,<EVENT_NAME_2> \
  -engine fpolicy_aws_engine \
  -is-mandatory false

# 複数プロトコルのイベントを 1 ポリシーに紐付け
vserver fpolicy policy create \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_multiprotocol \
  -events cifs_basic_events,nfsv3_basic_events,nfsv4_basic_events \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 5.2 スコープ作成

```bash
# 特定ボリュームのみ監視
vserver fpolicy policy scope create \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -volumes-to-include vol1,vol2

# 特定拡張子のみ監視
vserver fpolicy policy scope create \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -volumes-to-include "*" \
  -file-extensions-to-include jpg,png,pdf,docx

# 特定拡張子を除外
vserver fpolicy policy scope create \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -volumes-to-include "*" \
  -file-extensions-to-exclude tmp,log,swp
```

### 5.3 有効化

```bash
# 有効化（sequence-number = 優先度、小さいほど高優先）
vserver fpolicy enable \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

---

## 6. Persistent Store 設定（ONTAP 9.14.1+）

```bash
# Persistent Store 用ボリューム作成
volume create \
  -vserver <SVM_NAME> \
  -volume fpolicy_store_vol \
  -aggregate <AGGR_NAME> \
  -size 2GB \
  -state online \
  -junction-path /fpolicy_store

# Persistent Store 作成
vserver fpolicy persistent-store create \
  -vserver <SVM_NAME> \
  -persistent-store fpolicy_ps \
  -volume fpolicy_store_vol

# ポリシーに Persistent Store を紐付け
vserver fpolicy policy modify \
  -vserver <SVM_NAME> \
  -policy-name fpolicy_aws \
  -persistent-store fpolicy_ps
```

### 考慮点
- 非同期・非必須ポリシーのみサポート
- サーバー切断時にイベントを永続化し、再接続時に送信
- 専用ボリュームが必要（他のデータと共有不可）

---

## 7. 確認・トラブルシューティングコマンド

```bash
# FPolicy 全体の状態確認
vserver fpolicy show -vserver <SVM_NAME>

# エンジン接続状態
vserver fpolicy show-engine -vserver <SVM_NAME>

# ポリシー詳細
vserver fpolicy policy show -vserver <SVM_NAME> -policy-name fpolicy_aws -instance

# イベント詳細
vserver fpolicy policy event show -vserver <SVM_NAME> -event-name <EVENT_NAME> -instance

# スコープ詳細
vserver fpolicy policy scope show -vserver <SVM_NAME> -policy-name fpolicy_aws -instance

# 手動接続テスト
vserver fpolicy engine-connect -vserver <SVM_NAME> -policy-name fpolicy_aws -node <NODE_NAME> -server <SERVER_IP>

# 手動切断
vserver fpolicy engine-disconnect -vserver <SVM_NAME> -policy-name fpolicy_aws -node <NODE_NAME> -server <SERVER_IP>
```

---

## 8. プロトコル別推奨設定まとめ

| 項目 | SMB (CIFS) | NFSv3 | NFSv4 |
|------|-----------|-------|-------|
| 推奨 file-operations | create, write, delete, rename, close | create, write, delete, rename | **使用不可** |
| 推奨 filters | first-write, close-with-modification | first-write | **使用不可** |
| open/close 使用 | ✅ 安全 | ❌ 非サポート | ❌ NFS ブロック |
| create/write 使用 | ✅ 安全 | ✅ 動作確認済み | ❌ NFS ブロック |
| Write-complete 保証 | ✅ close イベントで検知可能 | ❌ 保証なし | N/A |
| E2E 検証結果 | 未検証（AD 必要） | ✅ **SQS 到達確認済み** | ❌ ブロック発生 |
| 推奨エンジンタイプ | asynchronous | asynchronous | **使用不可** |
| mandatory 設定 | false | false | N/A |
| NFS マウントオプション | N/A | `mount -o vers=3` | **使用禁止** |

---

## 9. 我々の検証で判明した追加の考慮点

### 9.1 NFS バージョンの自動ネゴシエーション

Linux クライアントはデフォルトで NFSv4.2 を使用する。FPolicy イベントのプロトコル設定は
実際のマウントバージョンと一致させる必要がある。

```bash
# マウントバージョン確認
mount | grep nfs
# → type nfs4 (vers=4.2) の場合は protocol=nfsv4 が必要

# NFSv3 で強制マウント
mount -t nfs -o vers=3 <SVM_IP>:/vol1 /mnt/fsxn
```

### 9.2 LIF サービスの分離

ONTAP 9.8+ では `data-fpolicy-client` サービスが専用 LIF に割り当てられる。
FPolicy 接続はこの LIF から確立されるが、NFS/SMB データアクセスは `data-nfs`/`data-cifs` LIF で処理される。

```bash
# LIF サービス確認
network interface show -vserver <SVM_NAME> -fields service-policy
```

### 9.3 NLB 非互換

ONTAP FPolicy プロトコルのバイナリフレーミング（`"` + 4バイト長 + `"` + payload）は
AWS NLB の TCP パススルーで正しく中継されない。FPolicy サーバーには直接 IP で接続すること。

---

## 10. 参考リンク

- [vserver fpolicy policy event create (CLI Reference)](https://docs.netapp.com/us-en/ontap-cli-991/vserver-fpolicy-policy-event-create.html)
- [Create ONTAP FPolicy external engines](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-external-engine-task.html)
- [Create ONTAP FPolicy events](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-event-task.html)
- [Create ONTAP FPolicy policies](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-policy-task.html)
- [Create ONTAP FPolicy scopes](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-scope-task.html)
- [Enable ONTAP FPolicy policies](https://docs.netapp.com/us-en/ontap/nas-audit/enable-fpolicy-policy-task.html)
- [Create ONTAP FPolicy persistent stores](https://docs.netapp.com/us-en/ontap/nas-audit/create-persistent-stores.html)
- [Plan FPolicy external engine configuration](https://docs.netapp.com/us-en/ontap/nas-audit/plan-fpolicy-external-engine-config-concept.html)
- [FPolicy synchronous and asynchronous notifications](https://docs.netapp.com/us-en/ontap/nas-audit/synchronous-asynchronous-notifications-concept.html)
