# FPolicy Persistent Store 機能

## 概要

ONTAP 9.14.1 以降で利用可能な **FPolicy Persistent Store** は、FPolicy サーバーが切断された際にイベントを SVM 上のボリュームに永続化し、サーバー再接続時に自動的に送信する機能です。

## 機能詳細

### 問題: イベントロスのリスク

非同期 FPolicy では、外部サーバーが切断されるとイベントが失われる可能性があります:
- ECS タスク再起動時（デプロイ、スケーリング）
- ネットワーク一時障害
- サーバー側の障害

### 解決: Persistent Store

Persistent Store を有効にすると:
1. サーバー切断時、イベントは SVM 上の専用ボリュームに書き込まれる
2. サーバー再接続時、蓄積されたイベントが順番に送信される
3. イベントロスゼロを実現

### 要件

| 項目 | 要件 |
|------|------|
| ONTAP バージョン | 9.14.1 以降 |
| FSx for ONTAP | 第2世代（Gen2）推奨 |
| 専用ボリューム | Persistent Store 用ボリュームが必要 |
| ボリュームサイズ | イベント量に応じて（最小 2GB 推奨） |

### 制限事項

- Persistent Store ボリュームは SVM ごとに 1 つ
- 同期モード（synchronous）では使用不可
- ボリュームが満杯になるとイベントがドロップされる

## 設定手順

### 1. Persistent Store 用ボリューム作成

```bash
# ONTAP CLI
volume create -vserver FSxN_OnPre -volume fpolicy_store \
  -aggregate aggr1 -size 2GB -state online \
  -junction-path /fpolicy_store \
  -security-style unix
```

### 2. Persistent Store 作成

```bash
# ONTAP CLI
fpolicy persistent-store create -vserver FSxN_OnPre \
  -persistent-store fpolicy_ps \
  -volume fpolicy_store
```

### 3. FPolicy ポリシーに Persistent Store を関連付け

```bash
# ポリシーを一度無効化
fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

# Persistent Store を設定
fpolicy policy modify -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -persistent-store fpolicy_ps

# ポリシーを再有効化
fpolicy enable -vserver FSxN_OnPre -policy-name fpolicy_aws \
  -priority-order 1
```

### 4. REST API での設定（代替）

```bash
# Persistent Store 作成
curl -sk -u fsxadmin:PASSWORD -X POST \
  "https://MGMT_IP/api/protocols/fpolicy/SVM_UUID/persistent-stores" \
  -H "Content-Type: application/json" \
  -d '{"name":"fpolicy_ps","volume":"fpolicy_store"}'

# ポリシーに関連付け
curl -sk -u fsxadmin:PASSWORD -X PATCH \
  "https://MGMT_IP/api/protocols/fpolicy/SVM_UUID/policies/fpolicy_aws" \
  -H "Content-Type: application/json" \
  -d '{"persistent_store":"fpolicy_ps"}'
```

## 確認コマンド

```bash
# Persistent Store の状態確認
fpolicy persistent-store show -vserver FSxN_OnPre

# 蓄積イベント数の確認
fpolicy persistent-store show -vserver FSxN_OnPre -fields pending-count

# ボリューム使用量確認
volume show -vserver FSxN_OnPre -volume fpolicy_store -fields used
```

## 本プロジェクトでの推奨

### 現状（Persistent Store なし）

- ECS タスク再起動時に数秒〜数十秒のイベントロスが発生する可能性
- IP 自動更新 Lambda（タスク 4）により、再接続は自動化済み
- 実用上、短時間のロスは許容可能なケースが多い

### Persistent Store 導入が推奨されるケース

1. **コンプライアンス要件**: 全ファイル操作の監査ログが必須
2. **大規模デプロイ**: 頻繁なタスク再起動が発生する環境
3. **長時間メンテナンス**: サーバー側の計画停止が長い場合

### 導入判断フロー

```
イベントロスが許容できるか？
├── YES → Persistent Store 不要（現状維持）
└── NO → FSxN が ONTAP 9.14.1+ か？
    ├── YES → Persistent Store を設定
    └── NO → FSxN アップグレードを検討
```

## 参考リンク

- [NetApp Docs: FPolicy Persistent Store](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores-fpolicy.html)
- [ONTAP 9.14.1 Release Notes](https://docs.netapp.com/us-en/ontap/release-notes/)
