# FSx for ONTAP — PowerShell Toolkit Action Catalog

> FSx for ONTAP で利用可能な NetApp.ONTAP PowerShell Toolkit (PSTK) のアクション一覧  
> ONTAP REST API エンドポイントとの対応表付き

---

## 前提条件

| 項目 | 値 |
|------|-----|
| モジュール名 | `NetApp.ONTAP` (PSGallery) |
| 最新バージョン | 9.15.1 (2025-01) |
| 接続先 | FSx for ONTAP ファイルシステム管理エンドポイント |
| 認証 | `fsxadmin` / パスワード |
| プロトコル | HTTPS (TCP 443) |
| 対応 OS | Windows (5.1+), Linux/macOS (PowerShell 7.x) |
| サポート | コミュニティサポート（NetApp公式サポート対象外） |

---

## カテゴリ一覧

| # | カテゴリ | FSx対応 | 主要ユースケース |
|---|---------|:-------:|----------------|
| 1 | [CIFS/SMB 共有管理](#1-cifssmb-共有管理) | ✅ | ファイル共有の作成・権限管理・移行 |
| 2 | [ローカルユーザ/グループ](#2-ローカルユーザグループ) | ✅ | SMBアクセス用ローカルアカウント管理 |
| 3 | [ボリューム管理](#3-ボリューム管理) | ✅ | ボリューム作成・リサイズ・情報取得 |
| 4 | [スナップショット管理](#4-スナップショット管理) | ✅ | スナップショット作成・削除・ポリシー |
| 5 | [エクスポートポリシー (NFS)](#5-エクスポートポリシー-nfs) | ✅ | NFS アクセス制御ルール管理 |
| 6 | [Qtree 管理](#6-qtree-管理) | ✅ | Qtree 作成・クォータ設定 |
| 7 | [FlexClone](#7-flexclone) | ✅ | 即時クローンボリューム作成 |
| 8 | [SnapMirror](#8-snapmirror) | ⚠️ | レプリケーション状態確認（制限付き） |
| 9 | [FPolicy](#9-fpolicy) | ✅ | ファイルアクセスイベント通知設定 |
| 10 | [Vscan (アンチウイルス)](#10-vscan-アンチウイルス) | ✅ | ウイルススキャン設定 |
| 11 | [DNS / Name Services](#11-dns--name-services) | ✅ | DNS・ネームサービス設定 |
| 12 | [ネットワーク情報](#12-ネットワーク情報) | ⚠️ | LIF 情報取得（変更不可） |
| 13 | [パフォーマンス/モニタリング](#13-パフォーマンスモニタリング) | ⚠️ | カウンター取得（一部制限） |
| 14 | [SVM/Vserver 情報](#14-svmvserver-情報) | ✅ | SVM 情報・プロトコル状態 |

---

## 1. CIFS/SMB 共有管理

最も多く利用される操作群。ファイル共有の作成、ACL 設定、プロパティ管理。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcCifsServer` | CIFS サーバー情報取得 | `GET /protocols/cifs/services` | |
| `Get-NcCifsShare` | 共有一覧取得 | `GET /protocols/cifs/shares` | |
| `Add-NcCifsShare` | 共有作成 | `POST /protocols/cifs/shares` | パス=ジャンクションパス |
| `Remove-NcCifsShare` | 共有削除 | `DELETE /protocols/cifs/shares/{svm.uuid}/{name}` | |
| `Set-NcCifsShare` | 共有プロパティ変更 | `PATCH /protocols/cifs/shares/{svm.uuid}/{name}` | |
| `Get-NcCifsShareAcl` | 共有 ACL 取得 | `GET /protocols/cifs/shares/{..}/acls` | |
| `Add-NcCifsShareAcl` | 共有 ACL 追加 | `POST /protocols/cifs/shares/{..}/acls` | Permission: full_control/change/read/no_access |
| `Remove-NcCifsShareAcl` | 共有 ACL 削除 | `DELETE /protocols/cifs/shares/{..}/acls/{..}` | |
| `Get-NcCifsSession` | アクティブセッション一覧 | `GET /protocols/cifs/sessions` | 接続中ユーザ確認 |
| `Get-NcCifsOpenFile` | オープンファイル一覧 | `GET /protocols/cifs/session/files` | ロック調査用 |

### 使用例（ファイル共有移行）

```powershell
# オンプレ → FSx for ONTAP への共有設定移行
Connect-NcController -Name <FSx-Mgmt-IP> -Credential (Get-Credential fsxadmin) -HTTPS

# 共有作成
Add-NcCifsShare -Name "engineering" -Path "/vol_eng" -VserverContext "svm1"

# ACL 設定
Add-NcCifsShareAcl -Share "engineering" -UserOrGroup "DOMAIN\Engineers" `
    -Permission "change" -UserGroupType "windows" -VserverContext "svm1"

# デフォルト Everyone 削除
Remove-NcCifsShareAcl -Share "engineering" -UserOrGroup "Everyone" `
    -UserGroupType "windows" -VserverContext "svm1"
```

**参考**: [Classmethod — PSTK で複数ファイル共有設定を移行](https://dev.classmethod.jp/articles/amazon-fsx-for-netapp-ontap-migrate-multiple-file-share-settings-with-netapp-ontap-powershell-toolkit/)

---

## 2. ローカルユーザ/グループ

AD 無しでも SMB 認証を可能にするローカルアカウント管理。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcCifsLocalUser` | ローカルユーザ一覧 | `GET /protocols/cifs/local-users` | |
| `New-NcCifsLocalUser` | ローカルユーザ作成 | `POST /protocols/cifs/local-users` | ユーザ名 max 20文字 |
| `Remove-NcCifsLocalUser` | ローカルユーザ削除 | `DELETE /protocols/cifs/local-users/{..}` | |
| `Set-NcCifsLocalUser` | ローカルユーザ変更 | `PATCH /protocols/cifs/local-users/{..}` | パスワード変更等 |
| `Get-NcCifsLocalGroup` | ローカルグループ一覧 | `GET /protocols/cifs/local-groups` | |
| `New-NcCifsLocalGroup` | ローカルグループ作成 | `POST /protocols/cifs/local-groups` | |
| `Remove-NcCifsLocalGroup` | ローカルグループ削除 | `DELETE /protocols/cifs/local-groups/{..}` | |
| `Get-NcCifsLocalGroupMember` | グループメンバー一覧 | `GET /protocols/cifs/local-groups/{..}/members` | |
| `Add-NcCifsLocalGroupMember` | メンバー追加 | `POST /protocols/cifs/local-groups/{..}/members` | |
| `Remove-NcCifsLocalGroupMember` | メンバー削除 | `DELETE /protocols/cifs/local-groups/{..}/members/{..}` | |

### 使用例

```powershell
# ユーザ作成
$pw = ConvertTo-SecureString "P@ssw0rd123" -AsPlainText -Force
New-NcCifsLocalUser -VserverContext "svm1" -UserName "appuser1" `
    -FullName "Application User 1" -Password $pw

# グループ作成 + メンバー追加
New-NcCifsLocalGroup -VserverContext "svm1" -GroupName "app-users" -Description "App access"
Add-NcCifsLocalGroupMember -VserverContext "svm1" -GroupName "app-users" -Member "SVM1\appuser1"
```

---

## 3. ボリューム管理

ストレージボリュームのライフサイクル管理。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcVol` | ボリューム情報取得 | `GET /storage/volumes` | サイズ、使用量、ポリシー等 |
| `New-NcVol` | ボリューム作成 | `POST /storage/volumes` | ジャンクションパス指定 |
| `Remove-NcVol` | ボリューム削除 | `DELETE /storage/volumes/{uuid}` | オフライン→削除 |
| `Set-NcVolSize` | サイズ変更 | `PATCH /storage/volumes/{uuid}` | オンラインリサイズ |
| `Set-NcVolOption` | オプション変更 | `PATCH /storage/volumes/{uuid}` | |
| `Mount-NcVol` | マウント（ジャンクション） | `PATCH .../nas.path` | |
| `Dismount-NcVol` | アンマウント | `PATCH .../nas.path = ""` | |
| `Get-NcVolSpace` | スペース詳細 | `GET /storage/volumes/{uuid}?fields=space` | Footprint 情報 |
| `Set-NcVol` | 属性変更 | `PATCH /storage/volumes/{uuid}` | ティアリングポリシー等 |
| `Get-NcVol -Query @{...}` | フィルタ検索 | `GET /storage/volumes?name=*` | クエリオブジェクト |

### 使用例

```powershell
# ボリューム作成（1TB、自動ティアリング）
New-NcVol -Name "vol_reports" -Aggregate "aggr1" -Size "1t" `
    -JunctionPath "/reports" -SecurityStyle "ntfs" `
    -ExportPolicy "default" -VserverContext "svm1"

# サイズ変更
Set-NcVolSize -Name "vol_reports" -NewSize "2t" -VserverContext "svm1"

# スペース確認
Get-NcVol -Name "vol_reports" -VserverContext "svm1" | Select-Object Name, TotalSize, Available, Used
```

---

## 4. スナップショット管理

ポイントインタイム復元のためのスナップショット操作。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcSnapshot` | スナップショット一覧 | `GET /storage/volumes/{uuid}/snapshots` | |
| `New-NcSnapshot` | スナップショット作成 | `POST /storage/volumes/{uuid}/snapshots` | 即時作成 |
| `Remove-NcSnapshot` | スナップショット削除 | `DELETE /storage/volumes/{uuid}/snapshots/{uuid}` | |
| `Rename-NcSnapshot` | リネーム | `PATCH .../snapshots/{uuid}` | |
| `Restore-NcSnapshotVolume` | ボリュームリストア | `POST .../snapshots/{uuid}?action=restore` | **データ上書き注意** |
| `Get-NcSnapshotPolicy` | ポリシー一覧 | `GET /storage/snapshot-policies` | |
| `Set-NcSnapshotPolicy` | ポリシー適用 | `PATCH /storage/volumes/{uuid}` | ボリュームにポリシー紐付け |

### 使用例

```powershell
# 手動スナップショット作成
New-NcSnapshot -Volume "vol_reports" -Snapshot "before-migration-2026" -VserverContext "svm1"

# スナップショット一覧（サイズ付き）
Get-NcSnapshot -Volume "vol_reports" -VserverContext "svm1" |
    Select-Object Name, Created, Total, CumulativeTotal |
    Format-Table -AutoSize

# 古いスナップショット削除
Get-NcSnapshot -Volume "vol_reports" -VserverContext "svm1" |
    Where-Object { $_.Created -lt (Get-Date).AddDays(-30) } |
    Remove-NcSnapshot -Confirm:$false
```

---

## 5. エクスポートポリシー (NFS)

NFS アクセスを制御するエクスポートポリシーとルール管理。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcExportPolicy` | ポリシー一覧 | `GET /protocols/nfs/export-policies` | |
| `New-NcExportPolicy` | ポリシー作成 | `POST /protocols/nfs/export-policies` | |
| `Remove-NcExportPolicy` | ポリシー削除 | `DELETE /protocols/nfs/export-policies/{id}` | |
| `Get-NcExportRule` | ルール一覧 | `GET /protocols/nfs/export-policies/{id}/rules` | |
| `New-NcExportRule` | ルール追加 | `POST /protocols/nfs/export-policies/{id}/rules` | |
| `Remove-NcExportRule` | ルール削除 | `DELETE .../rules/{index}` | |
| `Set-NcExportRule` | ルール変更 | `PATCH .../rules/{index}` | |

### 使用例

```powershell
# エクスポートポリシー作成
New-NcExportPolicy -Name "linux-clients" -VserverContext "svm1"

# ルール追加（特定サブネットに RW 許可）
New-NcExportRule -Policy "linux-clients" -ClientMatch "10.0.0.0/16" `
    -Protocol nfs -ReadOnlySecurityFlavor sys -ReadWriteSecurityFlavor sys `
    -SuperUserSecurityFlavor sys -VserverContext "svm1"

# ボリュームにポリシー適用
Set-NcVol -Name "vol_data" -ExportPolicy "linux-clients" -VserverContext "svm1"
```

---

## 6. Qtree 管理

ボリューム内の論理パーティション（Qtree）管理。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcQtree` | Qtree 一覧 | `GET /storage/qtrees` | |
| `New-NcQtree` | Qtree 作成 | `POST /storage/qtrees` | セキュリティスタイル指定可 |
| `Remove-NcQtree` | Qtree 削除 | `DELETE /storage/qtrees/{volume.uuid}/{id}` | |
| `Set-NcQtree` | Qtree 変更 | `PATCH /storage/qtrees/{volume.uuid}/{id}` | |
| `Get-NcQuota` | クォータ情報 | `GET /storage/quota/reports` | 使用量確認 |
| `Set-NcQuotaOn` | クォータ有効化 | 相当する REST | |
| `Add-NcQuotaPolicy` | クォータポリシー追加 | `POST /storage/quota/rules` | |

---

## 7. FlexClone

即時ゼロコピーのボリュームクローン作成。開発/テスト環境やデータ分析に最適。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `New-NcClone` | FlexClone 作成 | `POST /storage/volumes` (clone指定) | 即時（スペース消費なし） |
| `Get-NcClone` | クローン情報 | `GET /storage/volumes?clone.is_flexclone=true` | |
| `Split-NcClone` | クローン分割 | `PATCH /storage/volumes/{uuid}` (clone.split_initiated) | 独立ボリュームに |

### 使用例

```powershell
# 本番ボリュームの即時クローン（開発環境用）
New-NcClone -CloneVolume "vol_prod_clone" -ParentVolume "vol_prod" `
    -ParentSnapshot "nightly-2026-07-30" -VserverContext "svm1"
```

---

## 8. SnapMirror

データレプリケーション関係の確認・操作（FSx では制限あり）。

| Cmdlet | 動作 | REST API | 制限 |
|--------|------|----------|------|
| `Get-NcSnapmirror` | SnapMirror 関係確認 | `GET /snapmirror/relationships` | 読取のみ推奨 |
| `Invoke-NcSnapmirrorUpdate` | 手動同期 | `POST .../transfers` | |
| `Get-NcSnapmirrorDestination` | 宛先情報 | `GET /snapmirror/relationships` | |

**注意**: FSx for ONTAP の SnapMirror はAWS管理レイヤーで設定するケースが多い。PSTK からの設定変更は注意が必要。

---

## 9. FPolicy

ファイルアクセスイベントの通知設定（監査・DLP・セキュリティ対応）。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcFpolicyPolicy` | FPolicy ポリシー一覧 | `GET /protocols/fpolicy/{svm.uuid}/policies` | |
| `New-NcFpolicyPolicy` | FPolicy ポリシー作成 | `POST /protocols/fpolicy/{svm.uuid}/policies` | |
| `Get-NcFpolicyEvent` | FPolicy イベント定義 | `GET /protocols/fpolicy/{svm.uuid}/events` | |
| `New-NcFpolicyEvent` | FPolicy イベント作成 | `POST /protocols/fpolicy/{svm.uuid}/events` | |
| `Enable-NcFpolicyPolicy` | ポリシー有効化 | `PATCH .../policies/{name}?enabled=true` | |
| `Disable-NcFpolicyPolicy` | ポリシー無効化 | `PATCH .../policies/{name}?enabled=false` | 変更前に必須 |

**参考**: [aws-samples/securing-amazon-fsx-for-ontap-against-viruses](https://github.com/aws-samples/securing-amazon-fsx-for-ontap-against-viruses) — Vscan/FPolicy の PowerShell 設定例

---

## 10. Vscan (アンチウイルス)

SMB ファイルアクセス時のウイルススキャン設定。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcVscan` | Vscan 状態 | `GET /protocols/vscan/{svm.uuid}` | |
| `Enable-NcVscan` | Vscan 有効化 | `PATCH /protocols/vscan/{svm.uuid}` | |
| `New-NcVscanOnAccessPolicy` | オンアクセスポリシー作成 | `POST .../on-access-policies` | |
| `New-NcVscanScannerPool` | スキャナプール作成 | `POST .../scanner-pools` | |
| `Get-NcVscanConnection` | スキャナ接続状態 | `GET .../scanner-pools` | |

---

## 11. DNS / Name Services

名前解決とネームサービス設定。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcNetDns` | DNS 設定取得 | `GET /name-services/dns` | |
| `Set-NcNetDns` | DNS 設定変更 | `PATCH /name-services/dns/{svm.uuid}` | |
| `Get-NcNameMapping` | ネームマッピング | `GET /name-services/name-mappings` | win↔unix |
| `New-NcNameMapping` | マッピング作成 | `POST /name-services/name-mappings` | |

---

## 12. ネットワーク情報

LIF（論理インターフェース）の情報取得。FSx では作成・変更は不可（AWS管理）。

| Cmdlet | 動作 | REST API | 制限 |
|--------|------|----------|------|
| `Get-NcNetInterface` | LIF 一覧 | `GET /network/ip/interfaces` | 読取のみ |
| `Get-NcNetPort` | ポート情報 | `GET /network/ethernet/ports` | 読取のみ |
| `Get-NcNetRoute` | ルーティング | `GET /network/ip/routes` | 読取のみ |

---

## 13. パフォーマンス/モニタリング

パフォーマンスカウンターの取得（CloudWatch との併用推奨）。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcPerfObject` | カウンターオブジェクト一覧 | 内部 API | |
| `Get-NcPerfCounter` | カウンター値取得 | 内部 API | IOPS, レイテンシ等 |
| `Get-NcPerfInstance` | インスタンス一覧 | 内部 API | volume, lif 等 |

**注意**: FSx for ONTAP の場合は CloudWatch メトリクス + ONTAP REST API の `/cluster/counter/tables` を推奨。PSTK のパフォーマンス系コマンドは動作するが一部制限あり。

---

## 14. SVM/Vserver 情報

SVM レベルの情報取得とプロトコル状態確認。

| Cmdlet | 動作 | REST API | 備考 |
|--------|------|----------|------|
| `Get-NcVserver` | SVM 情報取得 | `GET /svm/svms` | |
| `Get-NcCifsService` | CIFS サービス状態 | `GET /protocols/cifs/services` | |
| `Get-NcNfsService` | NFS サービス状態 | `GET /protocols/nfs/services` | |
| `Get-NcIscsiService` | iSCSI サービス状態 | `GET /protocols/san/iscsi/services` | |

---

## FSx for ONTAP で使用不可（制限対象）

以下のカテゴリは FSx for ONTAP の `fsxadmin` ロールでは権限不足またはAWS管理レイヤーのため使用不可:

| カテゴリ | Cmdlet 例 | 理由 |
|---------|----------|------|
| クラスタ管理 | `Get-NcCluster`, `Get-NcNode` | AWS 管理レイヤー |
| アグリゲート管理 | `Get-NcAggr`, `New-NcAggr` | AWS 管理レイヤー |
| ライセンス | `Get-NcLicense` | AWS 管理レイヤー |
| ネットワーク作成 | `New-NcNetInterface` | AWS 管理レイヤー |
| ディスク管理 | `Add-NcDisk` | AWS 管理レイヤー |
| クラスタピアリング | `New-NcClusterPeer` | AWS API 経由で設定 |
| AutoSupport | `Get-NcAutoSupportConfig` | AWS 管理レイヤー |
| セキュリティ証明書 | `Install-NcSecurityCertificate` | 一部制限 |

---

## 接続パターン比較

| 観点 | PSTK (PowerShell) | REST API (curl/Python) | ONTAP CLI (SSH) |
|------|:--:|:--:|:--:|
| OS 要件 | Windows/Linux/Mac (PS7) | 任意 | 任意 |
| 自動化適性 | PowerShell スクリプト | 任意言語 | expect/ansible |
| 既存スクリプト互換 | ✅ オンプレ流用可 | ❌ 書き直し | △ コマンド同一 |
| バルク操作 | ループ | bulk-import API | ループ |
| Lambda 統合 | ✅ Custom Runtime | ✅ Python/Node | ❌ |
| CI/CD 統合 | ✅ GitHub Actions | ✅ | △ |
| サポート | コミュニティ | NetApp 公式 | NetApp 公式 |
| 将来性 | メンテナンスモード寄り | ✅ 推奨方向 | 安定 |

---

## 関連リソース

- [NetApp ONTAP PowerShell Toolkit — 公式ドキュメント](https://docs.netapp.com/us-en/ontap-automation/pstk/learn-about-pstk.html)
- [TR-4577: Manage Windows File Services with PSTK](https://www.netapp.com/media/16860-tr-4577.pdf)
- [TR-4475: PSTK Best Practices Guide](https://www.netapp.com/pdf.html?item=/media/16861-tr-4475.pdf)
- [NetApp/FSx-ONTAP-samples-scripts (GitHub)](https://github.com/NetApp/FSx-ONTAP-samples-scripts)
- [NetApp/fsxn-iscsisetup-ps (GitHub)](https://github.com/NetApp/fsxn-iscsisetup-ps)
- [aws-samples/securing-amazon-fsx-for-ontap-against-viruses (GitHub)](https://github.com/aws-samples/securing-amazon-fsx-for-ontap-against-viruses)
- [aws-samples/amazon-fsx-for-netapp-ontap-python-client-examples (GitHub)](https://github.com/aws-samples/amazon-fsx-for-netapp-ontap-python-client-examples)
- [awslabs/aws-lambda-powershell-runtime (GitHub)](https://github.com/awslabs/aws-lambda-powershell-runtime)
- [Classmethod — PSTK で複数ファイル共有移行](https://dev.classmethod.jp/articles/amazon-fsx-for-netapp-ontap-migrate-multiple-file-share-settings-with-netapp-ontap-powershell-toolkit/)
- [Classmethod — FSx for ONTAP 実行可能な ONTAP CLI コマンド一覧](https://dev.classmethod.jp/articles/list-of-ontap-cli-commands-supported-by-amazon-fsx-for-netapp-ontap)
- [ONTAP Cyber Vault with PowerShell](https://docs.netapp.com/us-en/netapp-solutions/cyber-vault/ontap-cyber-vault-powershell-creation.html)
