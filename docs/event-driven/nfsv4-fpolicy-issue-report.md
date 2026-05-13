# NFSv4.2 FPolicy 外部サーバーモード — イベント通知未送信の確認 / サポート範囲確認

**報告日**: 2026-05-14
**報告者**: Yoshiki Fujiwara (NetApp Inc.)
**環境**: Amazon FSx for NetApp ONTAP (ONTAP 9.17.1P6)
**ステータス**: 解決済み（NFSv4.2 非サポートによる期待動作と確認）

---

## 概要

FSx for NetApp ONTAP 9.17.1P6 において、FPolicy external engine asynchronous mode で
NFSv4.2 クライアントアクセス時に NOTI_REQ が送信されないことを確認しました。

mount option は `vers=4` でしたが、Linux クライアントでは実際には `vers=4.2` として
マウントされていました。

NFSv3、NFSv4.0、NFSv4.1 では同一ポリシー・同一ボリューム・同一 FPolicy server で
NOTI_REQ が正常に送信されます。

公開ドキュメントでは FPolicy for NFSv4.2 は非サポートと読めるため、本件は**期待動作**です。

---

## 根本原因

**`mount -o vers=4` で Linux クライアントが NFSv4.2 にネゴシエートしていた。**

ONTAP FPolicy は以下をサポート:
- SMB (CIFS) ✅
- NFSv3 ✅
- NFSv4.0 ✅
- NFSv4.1 ✅（ONTAP 9.15.1 以降）
- **NFSv4.2 ❌ 非サポート**

参考:
- [NetApp KB: FPolicy supported protocols](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing)
- [ONTAP NFS Management: FPolicy monitoring of NFSv4.2 not supported](https://docs.netapp.com/us-en/ontap/nfs-admin/index.html)

---

## 検証結果（最終）

| NFS バージョン | マウントオプション | 実際の vers | FPolicy NOTI_REQ | 結果 |
|---|---|---|---|---|
| NFSv3 | `vers=3` | 3 | ✅ 即座に受信 | 動作する |
| NFSv4.0 | `vers=4.0` | 4.0 | ✅ 即座に受信 | **動作する** |
| NFSv4.1 | `vers=4.1` | 4.1 | ✅ 即座に受信 | **動作する** |
| NFSv4.2 | `vers=4.2` | 4.2 | ❌ 送信されない | **非サポート（期待動作）** |
| NFSv4 (auto) | `vers=4` | 4.2 | ❌ 送信されない | 4.2 にネゴシエート |
| SMB | — | — | ✅ 即座に受信 | 動作する |

---

## 推奨設定

### FPolicy を使用する場合の NFS マウントオプション

```bash
# 推奨: NFSv4.1 に明示固定
sudo mount -t nfs -o vers=4.1 <SVM_IP>:/<path> /mnt/fsxn

# または NFSv3
sudo mount -t nfs -o vers=3 <SVM_IP>:/<path> /mnt/fsxn

# NG: vers=4 は NFSv4.2 にネゴシエートされる可能性がある
# sudo mount -t nfs -o vers=4 <SVM_IP>:/<path> /mnt/fsxn  ← 使用しない
```

### SVM 側で NFSv4.2 を無効化する方法

ONTAP ドキュメントでは、FPolicy monitoring を構成する場合は NFSv4.2 を無効化することが推奨されています。

```bash
# ONTAP CLI
vserver nfs modify -vserver <SVM_NAME> -v4.2 disabled

# ONTAP REST API
curl -sk -u fsxadmin:<PASS> -X PATCH \
  'https://<MGMT_IP>/api/protocols/nfs/services/<SVM_UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"protocol":{"v42_enabled":false}}'
```

---

## FSxN ドキュメント改善要望

現在の FSxN ユーザー向けドキュメントには、FPolicy 使用時に NFSv4.2 が非サポートである旨の
明確な記載がありません。以下の改善を要望します:

1. FSxN の FPolicy ドキュメントに「NFSv4.2 は FPolicy monitoring 非サポート」を明記
2. `mount -o vers=4` ではなく `vers=4.1` を推奨する旨のガイダンス追加
3. FPolicy 設定ガイドに NFS バージョン固定の手順を含める

---

## 経緯

1. 初回テスト: `mount -o vers=4` → NFSv4.2 にネゴシエート → NOTI_REQ 来ない → 「NFSv4 が動かない」と誤認
2. NetApp 有識者からのフィードバック: NFSv4.2 非サポートの可能性を指摘
3. 再検証: `vers=4.1` と `vers=4.0` で明示固定 → **両方とも正常動作**
4. 結論: NFSv4.2 非サポートによる期待動作。ドキュメント改善要望として整理。

---

## 参考ドキュメント

- [NetApp KB: FPolicy Auditing FAQ](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing)
- [ONTAP NFS Management](https://docs.netapp.com/us-en/ontap/nfs-admin/index.html)
- [FPolicy event configuration](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-event-task.html)
- [vserver fpolicy policy event create (CLI Reference)](https://docs.netapp.com/us-en/ontap-cli-991/vserver-fpolicy-policy-event-create.html)
