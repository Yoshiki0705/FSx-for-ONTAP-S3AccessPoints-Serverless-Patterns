# NFSv4 FPolicy 外部サーバーモード — イベント通知未送信の報告

**報告日**: 2026-05-14
**報告者**: Yoshiki Fujiwara (NetApp Inc.)
**環境**: Amazon FSx for NetApp ONTAP (ONTAP 9.17.1P6)
**目的**: NFSv4 プロトコルで FPolicy 外部サーバーモードのイベント通知が送信されない事象の報告

---

## 概要

FSx for NetApp ONTAP (ONTAP 9.17.1P6) 環境において、FPolicy 外部サーバーモード（非同期）で
NFSv4 プロトコルのファイル操作イベント通知（NOTI_REQ）が送信されない事象を確認しました。

同一環境・同一ポリシーで NFSv3 プロトコルでは正常にイベント通知が送信されます。
NetApp ドキュメント上は NFSv4 の file_operations（create, write, delete, rename）は
サポートされていると記載されています。

---

## 環境情報

| 項目 | 値 |
|------|-----|
| ファイルシステム | Amazon FSx for NetApp ONTAP |
| ファイルシステム ID | fs-09ffe72a3b2b7dbbd |
| ONTAP バージョン | NetApp Release 9.17.1P6 (Wed Mar 25 15:38:10 UTC 2026) |
| SVM 名 | FSxN_OnPre |
| SVM UUID | 9ae87e42-068a-11f1-b1ff-ada95e61ee66 |
| リージョン | ap-northeast-1 (東京) |
| FPolicy Server | ECS Fargate (Python TCP サーバー, port 9898) |
| FPolicy Server IP | 10.0.15.111 |
| NFS Client | Amazon Linux 2023 (EC2 t4g.nano) |
| NFS Client IP | 10.0.10.67 |
| NFS Data LIF | 10.0.3.133 (Node-01, services: data_nfs) |
| FPolicy Client LIF | 10.0.9.32 (Node-01), 10.0.2.18 (Node-02) |
| ボリューム | kodera_snowflake_testap (junction: /vol1) |

---

## FPolicy 設定

### External Engine

```
Name: fpolicy_aws_engine
Type: asynchronous
Primary Servers: 10.0.15.111
Port: 9898
Format: xml
SSL: no-auth
```

### Events

```
# NFSv3 イベント（動作する）
Name: nfsv3_file_events
Protocol: nfsv3
File Operations: create=true, write=true, delete=true, rename=true

# NFSv4 イベント（動作しない）
Name: nfsv4_file_events
Protocol: nfsv4
File Operations: create=true, write=true, delete=true, rename=true
```

### Policy

```
Name: fpolicy_aws
Enabled: true
Mandatory: false
Engine: fpolicy_aws_engine
Events: nfsv3_file_events, cifs_file_events, nfsv4_file_events
Priority: 1
Scope: include_volumes = [kodera_snowflake_testap]
```

### 接続状態

```
Node-01 → 10.0.15.111: connected
Node-02 → 10.0.15.111: connected
KEEP_ALIVE: 2分間隔で正常受信
```

---

## 再現手順

### 前提条件
- FPolicy ポリシーが有効化され、接続が `connected` 状態
- KEEP_ALIVE が正常に受信されていることを確認

### テスト 1: NFSv3（成功）

```bash
# NFSv3 でマウント
sudo mount -t nfs -o vers=3 10.0.3.133:/vol1 /mnt/fsxn

# ファイル作成
echo "NFSv3 test" | sudo tee /mnt/fsxn/nfsv3-test.txt

# 結果: FPolicy Server が NOTI_REQ を受信し、SQS に送信
# ログ: [SQS] Sent: \nfsv3-test.txt (create)
```

### テスト 2: NFSv4（失敗）

```bash
# NFSv4 でマウント（同じ SVM、同じボリューム）
sudo umount /mnt/fsxn
sudo mount -t nfs -o vers=4 10.0.3.133:/vol1 /mnt/fsxn
# → type nfs4 (vers=4.2) でマウントされる

# ファイル作成
echo "NFSv4 test" | sudo tee /mnt/fsxn/nfsv4-test.txt

# 結果: ファイル作成は成功するが、FPolicy Server に NOTI_REQ が送信されない
# 15秒以上待機しても通知なし
```

### テスト 3: NFSv3 に戻す（成功）

```bash
# NFSv3 に戻してマウント
sudo umount /mnt/fsxn
sudo mount -t nfs -o vers=3 10.0.3.133:/vol1 /mnt/fsxn

# ファイル作成
echo "NFSv3 control" | sudo tee /mnt/fsxn/nfsv3-control.txt

# 結果: 即座に NOTI_REQ 受信 + SQS 送信
# ログ: [SQS] Sent: \nfsv3-control.txt (create)
```

---

## 検証結果

| テスト | NFS バージョン | ファイル作成 | NOTI_REQ 受信 | 備考 |
|--------|--------------|------------|--------------|------|
| 1 | NFSv3 (vers=3) | ✅ 成功 | ✅ 即座に受信 | 正常動作 |
| 2 | NFSv4 (vers=4.2) | ✅ 成功 | ❌ 送信されない | **問題** |
| 3 | NFSv3 (vers=3) | ✅ 成功 | ✅ 即座に受信 | 対照実験 |

---

## 排除した仮説

| 仮説 | 検証方法 | 結果 |
|------|----------|------|
| FPolicy 接続が不安定 | KEEP_ALIVE 受信確認 | ❌ 接続は安定 |
| NFSv4 イベントがポリシーに含まれていない | REST API で確認 | ❌ 含まれている |
| Scope が一致しない | 同じボリュームで NFSv3 は動作 | ❌ Scope は正しい |
| FPolicy Server の実装問題 | NFSv3 + SMB で動作確認済み | ❌ Server は正常 |
| Data LIF の問題 | 同じ LIF (10.0.3.133) で NFSv3/v4 両方テスト | ❌ LIF は同じ |
| 設定ミス | ポリシー内容を REST API で逐一確認 | ❌ 設定は正しい |

---

## ドキュメントとの矛盾

NetApp ONTAP CLI Reference ([vserver fpolicy policy event create](https://docs.netapp.com/us-en/ontap-cli-991/vserver-fpolicy-policy-event-create.html)) には、NFSv4 プロトコルで以下の file_operations がサポートされると記載されています:

```
Supported File Operations for nfsv4:
  close, create, create_dir, delete, delete_dir, getattr, link,
  lookup, open, read, write, rename, rename_dir, setattr, symlink
```

しかし、実際の動作では NFSv4 の `create`/`write`/`delete`/`rename` イベントに対して
NOTI_REQ が送信されません。

---

## 質問事項

1. FSx for NetApp ONTAP (ONTAP 9.17.1) で NFSv4 プロトコルの FPolicy 外部サーバーモード（非同期）は正式にサポートされていますか？
2. NFSv4 で NOTI_REQ が送信されない既知の制限事項はありますか？
3. オンプレミス ONTAP 9.17.1 では NFSv4 FPolicy 外部サーバーモードは動作しますか？
4. FSxN 固有の制約がある場合、ドキュメントに記載される予定はありますか？
5. 回避策として NFSv3 の使用以外に推奨される方法はありますか？

---

## 参考情報

- **動作確認済みプロトコル**: NFSv3 ✅, SMB (CIFS) ✅
- **FPolicy Server 実装**: [GitHub - fsxn-s3ap-serverless-patterns](https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns) の `shared/fpolicy-server/fpolicy_server.py`
- **参考実装**: [Shengyu Fang - ontap-fpolicy-aws-integration](https://github.com/YhunerFSY/ontap-fpolicy-aws-integration)（SMB で動作確認済み）
- **検証レポート全文**: `docs/event-driven/fpolicy-e2e-verification-report.md`

---

## 添付可能なエビデンス

必要に応じて以下を提供可能:
- FPolicy Server の CloudWatch Logs（KEEP_ALIVE 受信 + NFSv3 NOTI_REQ 受信のログ）
- ONTAP REST API レスポンス（ポリシー設定、接続状態）
- パケットキャプチャ（必要であれば取得可能）
