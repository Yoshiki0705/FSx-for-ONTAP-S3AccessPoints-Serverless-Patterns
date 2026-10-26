
🌐 **Language / 言語**: 日本語 | [English](ontap-teardown-guide.en.md)

ポータルの Resource Management に追加した ONTAP リソース削除（teardown）アクションの運用ノートです。
検証環境のクリーンアップで「削除できないリソースを、依存を解きほぐしながら順に削除する」ために
追加しました。各アクションの REST エンドポイント、同期/非同期の前提、依存解消の順序を 1 箇所に
まとめます。

> **検証状態**: 全アクションを fs-002ec851eba809979（ONTAP 9.18.1P6）の使い捨て SVM で
> 一巡実行して確認済みです（2026-10-26）。実機でしか分からなかった差分（SVM 削除は FSx API
> 経由、監査の集約待ち、監査の `log_path`、FPolicy engine 拒否の文面）は実装とこのノートに
> 反映済みです。

## 新規アクション一覧

| アクション | 種別 | 経路 | 同期/非同期 | 検証状態 |
|---|---|---|---|---|
| `listFpolicyEngines` | read | ONTAP REST GET `/protocols/fpolicy/{svm.uuid}/engines` | 同期 | 検証済み |
| `deleteFpolicyEngine` | delete | ONTAP REST DELETE `/protocols/fpolicy/{svm.uuid}/engines/{name}` | 同期 | 検証済み |
| `getAuditConfig` | read | ONTAP REST GET `/protocols/audit/{svm.uuid}`（`log_path`）+ `.../object-store` | 同期 | 検証済み |
| `deleteAudit` | delete | ONTAP REST PATCH（無効化）+ DELETE（集約待ちで再試行） | 非同期（202→job） | 検証済み |
| `deleteObjectStoreAudit` | delete | ONTAP REST PATCH（無効化）+ DELETE `.../object-store` | 非同期（202→job） | 検証済み |
| `listSvms` | read | **AWS FSx API** DescribeStorageVirtualMachines（file-system で絞り込み） | 同期 | 検証済み |
| `getSvmDeletionImpact` | read | ONTAP REST GET `/storage/volumes?...&fields=is_svm_root` | 同期 | 検証済み |
| `deleteSvm` | delete | **AWS FSx API** DeleteStorageVirtualMachine（ONTAP REST ではない） | 非同期 | 検証済み |
| `deleteFlexClone` | delete | ONTAP REST PATCH（offline）+ DELETE `/storage/volumes/{uuid}` | 非同期（202→job） | 検証済み |

これらに加えて、backend に既にあり UI 未露出だった `deleteObjectStoreBucket` /
`listObjectStoreBuckets` / `updateQosPolicy` / `listExpiredRetention` / `assignSnapshotPolicy`
に UI を付けました（挙動は既存のまま）。

## 出典（公式 REST リファレンス）

数値・挙動は NetApp 公式 REST リファレンスの記述を要約しています（逐語引用は避けています。
Content was rephrased for compliance with licensing restrictions）。

- [Delete an FPolicy external engine configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-fpolicy-engines-.html)：
  ポリシーに紐づく engine は削除できない（＝順序の裏付け）。レスポンスは同期。
- [Delete an audit configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-audit-.html) /
  [Delete an S3 audit configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-audit-object-store.html)：
  202 非同期。監査が有効のままだと削除失敗（`140902421`）、最終集約の進行中は `140902422`。
- [Delete an SVM](https://docs.netapp.com/us-en/ontap-restapi/delete-svm-svms-.html)：202 非同期。

## teardown の順序（運用ノート）

### FPolicy

```
ポリシーを無効化 → ポリシーを削除 → イベントを削除 → エンジンを削除
```

engine はポリシーに参照されている間は削除できません。UI の FPolicy パネル（Engines タブ）は
この順序を案内し、各ステップは個別アクションのままです（一括実行ボタンは設けていません）。
`native` engine は ONTAP 組み込みのため削除対象外として非活性化します。

### 監査とボリューム

```
（ボリュームが監査ログ出力先の場合）監査を削除 → ボリュームを削除
```

監査ログの出力先になっているボリュームは削除できません。先に監査を削除（無効化）します。
`deleteAudit` / `deleteObjectStoreAudit` は、監査が有効なら PATCH で無効化してから DELETE する
2 段構成です。**実測（9.18.1P6）で確認した 2 点:**

- **2 段は必要**（1 段には簡約できない）。監査が有効のまま DELETE すると 202 で受理された後、
  job の中で `resource in use` として失敗します。先に無効化すればこの経路に入りません。
- **無効化直後の DELETE は `Final consolidation is in progress` で失敗**し、20 秒ほど待って
  再試行すると成功します。そのため `deleteAudit` は無効化後の DELETE を、集約エラーのときだけ
  短いバックオフで再試行します（他のエラーは即座に返します）。

また、出力先ボリュームは REST の返りでは `log_path`（ジャンクションパス）として報告されます
（`log.volume.name` ではありません。作成時に `log.volume` を渡すと code 262179 で拒否）。

監査の「付け替え（別ボリュームへ再設定）」は本機能の対象外です。出力先・ログ形式・保持などの
設計判断を伴うため、teardown のスコープから外しています。

### SVM

```
配下の非 root ボリュームを全て削除 → SVM を削除（root ボリュームごと、FSx API 経由）
```

SVM は配下に非 root ボリュームが残っている間は削除できません。UI は最も破壊度が高い操作
として、SVM 名の再入力が一致するまで実行ボタンを無効にします。

**実測で判明した 2 つの制約（FSx for ONTAP 特有）:**

1. **SVM 削除は ONTAP REST ではできない。** fs-002 で確認したところ、fsxadmin 権限では
   ONTAP REST の `DELETE /svm/svms/{uuid}` が `not authorized for that command`（code 6）で
   拒否されます（非 root ボリュームが 0 でも）。SVM は AWS が管理するリソースのため、削除は
   **AWS FSx API（`DeleteStorageVirtualMachine`）** で行います。`deleteSvm` は boto3 の fsx
   client を使い、`listSvms` も FSx API から取得して FSx の SVM ID（svm-...）を UI に渡します。
2. **FSx API と ONTAP の 2 つの管理面にラグがある。** FSx API は ONTAP のリカバリキューに
   残るボリュームも「非 root ボリュームあり」とカウントし、さらに ONTAP REST で作成・削除した
   ボリュームは FSx API のインベントリに即座には反映されません。そのため ONTAP 側で
   `getSvmDeletionImpact` が非 root 0 を返しても、FSx API の SVM 削除が
   `Cannot delete storage virtual machine while it has non-root volumes` で拒否されることが
   あります。`deleteSvm` はこの FSx API の拒否をそのまま返し、「ONTAP 側で消しても FSx が
   まだ数えている場合がある」という注記を添えます。

### FlexClone

```
（親が消せない場合）クローンを split（独立化）または delete（削除） → 親ボリュームを削除
```

クローンが存在する間、親ボリュームは削除できません。`deleteFlexClone` はクローンボリューム自体を
既存の volume 削除と同型（unmount → offline → delete、各 job 待ち）で削除します。親の削除が
クローンに阻まれたときは、UI がその親に紐づくクローン一覧を提示します。split 後も親側に残る
ベース Snapshot の削除は運用者の判断に委ねます。

## 共通の設計

- 破壊的削除は backend で `confirm=true` を必須とし、無ければ ONTAP を呼ばずに拒否します。
- 202 非同期は job 完了を待ちます（SVM の root 削除など長時間化するものは pending 許容）。
- 削除後は read-back（GET が 404/空）で消滅を確認します。
- caller 由来の名前が REST パスに入る箇所は `_is_unsafe_path` で検証し、path segment / query 値を
  percent-encode します。
- 認証失敗は即停止し、リトライしません（fsxadmin のロック回避）。
- 保持系（SnapLock / snapshot locking / Object Lock / Tamperproof）を回避・解除する実装は
  一切行いません。`assignSnapshotPolicy` の UI は、保持を伴うポリシーの割り当てのみ既存の
  SnaplockConfirmDialog（`acknowledgeIrreversible`）経路に載せ、plain な confirm にはしません。

### FlexClone 削除と親の削除（補足）

削除したクローンは ONTAP のリカバリキューに残り（最大 12 時間）、その間は親ボリュームの削除が
`because it has one or more clones` で阻まれます。ポータルからの通常運用では時間を置けば解消
しますが、検証環境ですぐ消したい場合はクラスタ管理者が recovery-queue を purge します
（`volume recovery-queue purge`、ポータルの対象外）。親削除がクローンに阻まれたときは、UI が
その親に紐づくクローン一覧を提示します。

## 実機検証の結果（2026-10-26、ONTAP 9.18.1P6）

使い捨ての SVM `teardownprobe` 配下で全アクションを一巡実行し、次を実測しました。

| 項目 | 結果 |
|---|---|
| FlexClone 削除 | unmount→offline→delete で成功、read-back で消滅確認 |
| 親削除のクローン依存 | `because it has one or more clones` で拒否（削除済みクローンが recovery-queue に残る間も） |
| 監査削除 | 2 段必須。無効化直後は集約待ちで失敗 → 再試行で成功。出力先は `log_path` |
| FPolicy engine 削除 | 同期。参照中は code 9764940 `At least one policy is using ...` で拒否 |
| SVM 影響プレビュー | `is_svm_root` で root と非 root を正しく分離 |
| SVM 削除 | ONTAP REST は fsxadmin で不可（code 6）→ **FSx API 経由**で成功。FSx API は recovery-queue のボリュームも数えるため、ONTAP 側削除の反映待ちが要ることがある |

不可逆削除は実行前に対象を 1 件ずつ提示して承認を得たうえで実施し、検証後に全リソースを
削除して環境を元の状態に戻しました。
