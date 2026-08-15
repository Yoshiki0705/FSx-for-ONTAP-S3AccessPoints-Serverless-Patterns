# Windows ファイルサーバー移行: Backup Operators 特権による ACL 付きデータコピー

> 🌐 **Language / 言語**: 日本語 | [English](smb-acl-migration-backup-operators.en.md)

既存の Windows ファイルサーバーから Amazon FSx for NetApp ONTAP（SMB / NTFS セキュリティスタイル）へ
データを移行する際、**コピー実行ユーザー自身に NTFS ACL 上の権限がないファイル**をどう扱うかが問題になります。

本ドキュメントは、この論点について AWS サポートに確認し**回答を得た内容**をまとめたものです。

## 前提となる課題

Windows ファイルサーバーには、管理者アカウント（Domain Admins メンバーであっても）が NTFS ACL 上
読み取りを許可されていないファイルやフォルダーが存在し得ます。所有者が個人アカウントのままの
ホームディレクトリや、部門固有の制限フォルダーが典型例です。

ACL を保持したまま移行する必要がある場合、単純に robocopy を実行すると、これらのファイルは
アクセス拒否でスキップされます。差分コピー時には、コピー先の既存ファイルに対する上書き権限が
ないという逆方向の問題も発生します。

## 確認済みの挙動

以下 3 点は AWS サポートへの照会に対し、いずれも「認識の通り」との回答を得ています。

| 対象 | 使用する仕組み | 確認された挙動 |
|------|--------------|--------------|
| ソース側（Windows） | Backup Operators + `SeBackupPrivilege` | robocopy の `/B`（バックアップモード）により、ACL 上読み取り権限がないファイルも ACL 込みで読み取れる |
| コピー先（FSx for ONTAP） | `BUILTIN\Backup Operators` + `SeRestorePrivilege` | 差分コピー時に ACL 上書き込み権限がなくても、ACL を含む上書き（リストア）が可能 |
| AWS DataSync | 上記両方への所属 | ソース側 Backup Operators と FSx for ONTAP SVM 側 `BUILTIN\Backup Operators` の双方に所属していれば、初期・差分とも同様に動作する |

### なぜ機能するのか

`SeBackupPrivilege` と `SeRestorePrivilege` は、NTFS ACL の評価を**バイパス**する Windows の特権です。
バックアップソフトウェアがすべてのファイルを読み書きできるようにするために存在します。

ONTAP 側では、`BUILTIN\Backup Operators` グループにこの 2 つの特権が**デフォルトで割り当て済み**です
（[NetApp: SMB 特権の割り当て](https://docs.netapp.com/us-en/ontap/smb-admin/assign-privileges-concept.html)）。
そのため、SVM 上でこのグループにコピー実行ユーザーを追加するだけで有効になります。

重要なのは、robocopy の `/B` は**明示的に指定しないと特権を使わない**点です。Backup Operators に
所属させるだけでは不十分で、`/B` オプションが必要です。

## 移行構成

```
Windows ファイルサーバー                    FSx for ONTAP
（ソース）                                 （コピー先 / NTFS セキュリティスタイル）
  │                                          │
  │ コピー実行ユーザー:                        │ 同一ユーザーを SVM 上の
  │   Domain Admins                          │   BUILTIN\Backup Operators に追加
  │   + Backup Operators ← SeBackupPrivilege │   ← SeRestorePrivilege
  │                                          │
  └──── robocopy /B /COPY:DATSOU /MIR ──────▶│
        または AWS DataSync                   │  SVM は AD ドメイン参加済み
```

### 設定手順

**1. ソース側**: コピー実行ユーザーをローカルまたはドメインの Backup Operators に追加します。

**2. FSx for ONTAP 側**: SVM 上で `BUILTIN\Backup Operators` に同じユーザーを追加します。

```
vserver cifs users-and-groups local-group add-members \
  -vserver <svm-name> \
  -group-name "BUILTIN\Backup Operators" \
  -member-names <DOMAIN>\<user>
```

**3. コピー実行**: robocopy の場合は `/B` を必ず付与します。

```
robocopy <source> <dest> /B /COPY:DATSOU /MIR /R:1 /W:1 /LOG+:migrate.log
```

`/COPY:DATSOU` の各フラグは Data、Attributes、Timestamps、Security（NTFS ACL）、Owner、
aUditing information を意味します。ACL と所有者を保持するには `S` と `O` が必須です。

## 運用上の注意

> **特権の扱いに関する補足**: `SeBackupPrivilege` と `SeRestorePrivilege` は ACL 評価を
> バイパスするため、移行期間中のみ付与し、カットオーバー後は速やかに解除することを推奨します。
> 恒久的に付与したままにすると、ACL による権限分離が実質的に無効なアカウントが残ります。

> **監査に関する補足**: `/COPY` に `U`（aUditing information）を含めると SACL も複製されます。
> 監査要件がある環境では、移行後に SACL が意図通り引き継がれているか確認してください。

> **セキュリティスタイルに関する補足**: 本手順は NTFS セキュリティスタイルのボリュームを前提と
> しています。UNIX または MIXED セキュリティスタイルでは ACL の扱いが異なるため、
> [ONTAP 統合ノート](./ontap-integration-notes.md)の識別情報に関する記述も併せて確認してください。

> **検証範囲に関する補足**: 上記 3 点は AWS サポートに照会し回答を得た内容ですが、当プロジェクトで
> 実機による E2E 測定を実施したものではありません。本番移行の前に、対象データの一部で
> パイロットコピーを実施し、ACL と所有者が意図通り保持されることを確認してください。

## 参考資料

- [NetApp ONTAP: SMB 特権の割り当て](https://docs.netapp.com/us-en/ontap/smb-admin/assign-privileges-concept.html) — `BUILTIN\Backup Operators` のデフォルト特権
- [AWS: FSx for ONTAP SMB ファイル共有](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/smb-config.html)
- [Microsoft: Backup Operators グループ](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-groups#backup-operators)
- [Microsoft: robocopy](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy)

## 関連ドキュメント

- [ONTAP 統合ノート](./ontap-integration-notes.md) — NAS 併存、識別情報、データ保護
- [AD 参加 SVM での S3 AP 前提条件](./ja/ad-joined-svm-s3ap-prerequisites.md) — AD 参加 SVM 固有の考慮点
