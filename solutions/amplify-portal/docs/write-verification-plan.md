# 書き込み操作の検証計画

🌐 **Language / 言語**: **日本語** | [English](write-verification-plan.en.md)

> 目的: [検証結果](verification-results.md) で「未実行」に分類した書き込み操作について、
> **実行する前に**前提・影響・戻し方を確定させます。実行順もここで決めます。
>
> この文書は計画であって記録ではありません。実行した操作は
> [検証結果](verification-results.md) の「実機 E2E」へ移し、観測した挙動は
> `docs/agent/pitfalls-*.md` に書きます。

---

## 共通の原則

1. **検証用リソースは自分で作る**。既存のボリューム・共有・ポリシーを対象にしない。
   例外は「その既存リソースでしか確かめられないこと」がある場合に限り、実行前に影響を述べ、
   直後に元の状態へ戻す。
2. **実行前に影響を述べる**。どのリソースが、いつまで、どういう状態になるか。不可逆なものは
   承認を得る。
3. **成功レスポンスは成功の証拠ではない**。202 はジョブの受理でしかなく、ONTAP は変更が一覧に
   反映される前に ack を返す。数十秒後の状態で判定する。
4. **1 操作 1 観測**。まとめて実行して最後に確認すると、どの操作が何を起こしたか分からなくなる。
5. **失敗も記録する**。拒否のエラーコードとメッセージは、次に同じ場所へ来る読者が手にしている
   ものなので、成功より価値があることがある。

---

## グループ A: 安全に実行できる（未実施）

推奨する実行順は A8 → A3 → A2 → A5 → A7 → A4 → A6 → A1 です。前提が少なく、影響が小さく、
戻しやすいものから並べています。A1（QoS）を最後にしているのは、下で述べるとおり**現状では
一巡が完了しない**ためです。

### A1. QoS ポリシー — 一巡が完了しない（実行前に実装が必要）

| 項目 | 内容 |
|------|------|
| 対象 | `createQosPolicy` / `updateQosPolicy` / `assignQosToVolume` / `deleteQosPolicy` |
| 前提 | なし（この環境にはポリシーが 0 件） |
| 影響 | ポリシーを割り当てたボリュームは上限（IOPS / MBps）で**実際に絞られます**。検証用ボリュームに割り当てること |
| 確認 | 一覧に上限が出ること、`volume` の `qos.policy` が変わること |
| 戻し方 | **割り当てを外す手段がポータルにありません**（下記） |

ONTAP は、ストレージオブジェクトに割り当てられているポリシーグループの削除を拒否します
（`-force` を使わない限り。使うと関連するワークロードごと消えます）。出典:
[qos policy-group delete](https://docs.netapp.com/us-en/ontap-cli-9171/qos-policy-group-delete.html)。

一方 `assignQosToVolume` は `policyName` を必須にしているため、「なし」に戻す経路がありません。
つまり **作成 → 割り当て → 削除の一巡が現状のポータルでは完了せず**、検証すると削除できない
ポリシーが 1 件残ります。

先にやること: `assignQosToVolume` が空の `policyName`（または明示的な解除）を受け付け、
`PATCH /storage/volumes/{uuid}` に `{"qos": {"policy": {"name": "none"}}}` 相当を送れるように
します。UI 側は「QoS を外す」を割り当てと同じ場所に置きます。実装してから検証します。

### A2. SMB 共有の作成・削除

| 項目 | 内容 |
|------|------|
| 対象 | `createCifsShare` / `deleteCifsShare` |
| 前提 | SVM で CIFS が有効であること（この環境は有効）。共有するパスが存在すること |
| 影響 | 作成は追加のみ。**削除は、その共有を使っているクライアントの接続先を失わせます**。自分が作った共有だけを削除する |
| 確認 | 一覧に出ること、`path` と暗号化の状態が指定どおりであること |
| 戻し方 | 作成した共有を削除する（データは消えません。共有はボリュームへの入口の定義です） |

検証用の Qtree かディレクトリを作ってそこを共有します。既存の `c$` / `ipc$` は ONTAP の
管理共有なので触りません。

### A3. ローカルグループとメンバー

| 項目 | 内容 |
|------|------|
| 対象 | `createLocalGroup` / `deleteLocalGroup` / `addGroupMember` / `removeGroupMember` |
| 前提 | CIFS が有効であること。**ドメインユーザーを追加する場合は、ONTAP がその名前を SID に解決できること**（AD DC への到達性が必要）。ローカルユーザーの追加なら不要 |
| 影響 | グループのメンバーシップは NTFS ACL の評価に影響します。検証用のグループとユーザーだけを使う |
| 確認 | グループが一覧に出ること、メンバー一覧に追加したユーザーが出ること、削除で消えること |
| 戻し方 | メンバーを外し、グループを削除する |

出典: [ローカルグループのメンバーシップ管理](https://docs.netapp.com/us-en/ontap/smb-admin/manage-local-group-membership-task.html)、
[FSx for ONTAP のローカルグループへのユーザー追加](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/smb-workgroup-add-users-to-group.html)。

ローカルユーザーの作成・変更・削除は 2026-08-14 に確認済みなので、そこで作った形の
throwaway ユーザーを 1 つ作ってメンバーにします。**SID が変わらないこと**は既に確認済みです。

### A4. FlexClone の作成と分割（分割は不可逆）

| 項目 | 内容 |
|------|------|
| 対象 | `createFlexClone` / `splitFlexClone` |
| 前提 | 親ボリュームのスナップショット（省略時は作成時点のものを使用） |
| 影響（作成） | シンプロビジョニングなので容量は親と共有。親のスナップショットが 1 つロックされます |
| 影響（分割） | **不可逆**。分割したクローンは親に戻せません。**クローン上のスナップショットは削除され**、分割完了までクローンに新しいスナップショットを作れません。バックグラウンドの低優先スキャナで処理されるため時間がかかります |
| 確認 | 分割の進捗（ポータルは `分割中 n%` を表示）、完了後に親との関係が消えること |
| 戻し方 | 分割したクローンは**削除するしかありません**（それでよい throwaway クローンで実施する） |

**容量については誤解しやすい点があります**: ONTAP 9.4 以降、クローン分割は容量効率を維持し、
メタデータの更新だけでデータブロックをコピーしません。したがって「分割すると親の使用量と同じ
容量を消費する」は 9.4 以降には当てはまりません。出典:
[FlexClone ボリュームを親から分割する](https://docs.netapp.com/us-en/ontap/volumes/split-flexclone-from-parent-task.html)、
[FlexClone split の FAQ](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/FAQ_-_FlexClone_split)。

この環境には `clone01` / `clone02` / `clone03` が既にあります。**これらは分割しません**
（誰が何のために作ったかが不明で、分割は戻せません）。検証は新規に作ったクローンで行います。

### A5. クォータルールの削除 — 削除しても効き続ける

| 項目 | 内容 |
|------|------|
| 対象 | `deleteQuotaRule` |
| 前提 | 検証用のルールを作ってから削除する（既存の `projects` のルールは消さない） |
| 影響 | **削除は成功しても、そのボリュームの適用を off → on するまで規則は効き続けます** |
| 確認 | 一覧から消えること、そのあと適用を off → on して使用状況レポートから消えること |
| 戻し方 | 作った検証用ルールを削除するだけ（元からあるルールには触らない） |

ONTAP の REST リファレンスは、DELETE の応答として「削除は成功したがルールはまだ適用されて
いる。適用を止めるにはそのボリュームのクォータを無効化して再度有効化する」旨を明記しています。
出典: [Delete a quota policy rule](https://docs.netapp.com/us-en/ontap-restapi-9171/delete-storage-quota-rules-.html)、
[volume quota policy rule delete](https://docs.netapp.com/us-en/ontap-cli/volume-quota-policy-rule-delete.html)。

ポータルは成功だけを返しており、この続きを案内していません。**適用の切り替え自体は実装済み**
なので、削除後のヒントとして案内できます（検証と合わせて実装するのが自然です）。

なお上限の変更（`updateQuotaRule`）は REST では resize 不要で反映されます。2026-08-14 の実測と
一致します。

### A6. SnapMirror の即時更新と転送の中止

| 項目 | 内容 |
|------|------|
| 対象 | `updateSnapmirrorNow` / `abortSnapmirrorTransfer` |
| 前提（更新） | 関係が `snapmirrored` で idle であること |
| 前提（中止） | **転送中であること**。転送中でなければ中止は失敗します |
| 影響 | 宛先に新しいスナップショットが作られ、その分の容量を使います。中止した関係は unhealthy になり idle に戻ります。再開用のチェックポイントが残ることがあり、次の転送がそこから続きます（破棄するには `hard_aborted`） |
| 確認 | 転送履歴に 1 件増えること。中止後の状態遷移と `healthy` の値 |
| 戻し方 | 中止後は再度 update を実行して整合させる |

**中止の検証には「続く長さの転送」が必要です。** 空の検証ボリュームでは転送が一瞬で終わるため
中止できません。ソース側にある程度のデータを書いてから update を打ち、転送中に中止します。
出典: [転送の中止（REST）](https://docs.netapp.com/us-en/ontap-restapi-9111/patch-snapmirror-relationships-transfers-.html)、
[SnapMirror の状態の意味](https://kb.netapp.com/onprem/ontap/dp/SnapMirror/What_are_the_Ontap_SnapMirror_relationship_status_and_SnapMirror_State_meanings%3F)。
「転送中でなければ中止は失敗する」は
[アップグレード準備の手順](https://docs.netapp.com/us-en/ontap-systems-upgrade/upgrade-arl-auto-app-9151/complete-preparation-for-upgrade.html)
に明記があります。

### A7. ファイル操作（S3 Access Point 経由）

| 項目 | 内容 |
|------|------|
| 対象 | `createFolder` / `copyFile` / `moveFile` / `renameFile` / `trashFile` / `restoreFromTrash` / `deleteFileForever` / `createUploadLink` |
| 前提 | S3 AP に到達できること（確認済み）。検証用のファイルを自分でアップロードする |
| 影響 | `deleteFileForever` は取り消せません。ごみ箱経由（`trashFile`）はキーの移動なので戻せます |
| 確認 | NFS / SMB 側からも同じ結果が見えること（S3 AP とファイルプロトコルは同じボリュームを見ています） |
| 戻し方 | 検証用ファイルを削除する |

**5 GB の壁**: 名前変更・移動・コピー・ごみ箱・復元はすべて `copy_object` で実装されています
（`functions/list-files/index.py`）。単発の `CopyObject` は 5 GB までで、それを超えるものは
`UploadPartCopy` を使う必要があります。出典:
[copy-object（AWS CLI リファレンス）](https://docs.aws.amazon.com/cli/latest/reference/s3api/copy-object.html)。
ところが FSx for ONTAP S3 AP の `UploadPartCopy` は Supported と書かれていながら実測で
`NoSuchKey` になります（[S3 AP の罠](../../../docs/agent/pitfalls-s3ap-ontap.md)）。

したがって **5 GB を超えるオブジェクトはポータルから名前変更・移動できない**見込みです。
検証項目は次の 2 つです。

1. 5 GB 未満のファイルで 8 操作すべてが成功すること
2. 5 GB を超えるファイルで名前変更が**どう失敗するか**（エラーの文面を確認し、事前に止めるか
   説明を出すかを決める）

**アップロードリンク**: 署名付き PUT URL は SigV4 を明示する必要があります（boto3 の既定では
presign が v2 になる経路があり、ONTAP 側の v2 対応は 9.16.1 以降）。AWS の互換性表は presigned
URL を「非対応」と記載していますが実測では動作しており、AWS Support がドキュメント修正を提出
済み・**未公開**です。本番前提にはしない扱いを継続します（[S3 AP 互換性メモ](../../../docs/s3ap-compatibility-notes.md)）。

### A8. ARP を dry_run（学習モード）で有効化

| 項目 | 内容 |
|------|------|
| 対象 | `updateArpStateAdmin`（`dry_run`）、`enableArpBulk`（`dry_run`）、`clearArpSuspects` |
| 前提 | ONTAP 9.10.1 以降（この環境は 9.18.1P3D1） |
| 影響 | dry_run は観測と学習だけで、アクセスをブロックしません。ボリュームごとに設定されます |
| 確認 | 状態が `dry_run` になり、UI に「学習モード」と出ること |
| 戻し方 | `disabled` に戻す |

出典: [ボリュームで ARP を有効にする](https://docs.netapp.com/us-en/ontap/anti-ransomware/enable-task.html)。

`enabled`（保護中）への切り替えは、疑い検知でスナップショットが自動作成される動作が入るため
グループ A には含めません。まず dry_run で状態遷移と表示だけを確認します。
`clearArpSuspects` は疑いが 1 件も無い状態では確認できないので、疑いが出た場合のみ実施します。

---

## グループ B: 外部の前提が無いもの

実行できないので「未検証」のまま置きます。何が揃えば実行できるかを明示します。

| 対象 | 揃える必要があるもの |
|------|--------------------|
| Vscan 4 件（`setVscanEnabled` / ポリシーの作成・有効化・削除） | 外部スキャンエンジンと Vscan コネクタ。ポリシー定義だけならポータルから作成できるので、**エンジン無しでポリシー定義まで**は A に移せる可能性があります（ONTAP がポリシー有効化を拒否するかを先に確認） |
| FPolicy 5 件 | 外部 FPolicy エンジン。ただし `engine: native` を選べば外部エンジンなしで定義・有効化できる見込みなので、**native 限定で A に移せる可能性があります** |
| クラスターピア 3 件（作成・承認・削除） | 相手クラスターと intercluster LIF、TCP 11104 / 11105 と ICMP の許可、**相手側での accept**。片側からは完結しません |
| SVM ピアの承認・削除 | 同上。既存ピアの `applications` 変更は 2026-08-14 に確認済み |

> Vscan と FPolicy の「native なら到達できるか」は、環境を変えずに読み取りで判定できます
> （ポリシー作成 → 有効化を試し、拒否されたらその場で削除）。グループ A の最後に置いて確認する
> のが安全です。

---

## グループ C: 実行しないもの

| 対象 | 理由 |
|------|------|
| `updateSnaplockRetention` | SnapLock ボリュームが必要。未満了の WORM がボリューム → SVM → ファイルシステムの削除を連鎖的にブロックします |
| `enableSnapshotLocking` | 一度有効にすると無効化できません |
| `lockSnapshot`（両実装） | 保持期間は延長しかできず、短縮も解除もできません |
| `putS3ObjectLockRetention`（COMPLIANCE） | 保持期間を短縮・解除できません |
| `createSnapshotPolicy` / `assignSnapshotPolicy` | ポリシーの割り当ては `acknowledgeIrreversible` を要求します。ロックを伴う設定の入口になるため、意図的に実行しません |

この方針は [Tamperproof Snapshot 設計](../../../docs/tamperproof-snapshot-design.md) と
`AGENTS.md` の不可逆操作の節に従っています。**検証環境こそ不可逆操作を置いてはいけない場所**
です。削除できない検証リソースは長期の請求になり、同居する他のリソースも動かせなくします。

---

## グループ D: 共有環境に影響が及ぶもの（対応漏れ防止リスト）

実行するかどうかは別の判断ですが、**リストから落とさない**ために全件を挙げます。各行の
「切れるもの」は、その操作が成功したときに実際に停止する経路・セッションです。

| 対象 | 切れるもの | 影響範囲 | 戻し方 | 実行の条件 |
|------|-----------|---------|-------|-----------|
| `setNetworkInterfaceEnabled`（無効化） | その LIF が担う経路。管理 LIF なら**ポータル自身が ONTAP に到達できなくなります** | LIF 単位。データ LIF ならその LIF 経由の NFS / SMB / S3 | 同じ操作で有効化。ただし管理 LIF を落とすとポータルから戻せず、AWS コンソールか別経路が必要 | 対象が管理 LIF でないことを確認。データ LIF は利用者がいない時間帯 |
| `setProtocolServiceEnabled`（無効化） | そのプロトコルのサービス（NFS / CIFS / S3） | SVM 全体。使用中のクライアントは切断されます | 同じ操作で有効化。CIFS は再有効化後に再参加が必要になる場合があります | 検証用 SVM があるならそちらで。既定 SVM では実施しない |
| `updateDnsConfig` | 名前解決。AD 参加 SVM では**ドメインコントローラーを引けなくなり、SMB と AD 認証が止まります** | SVM 全体 | 元の domains / servers に戻す（**実行前に現在値を記録すること**） | 現在値を控えてから。AD 参加 SVM では避ける |
| `breakSnapmirror` | レプリケーションの関係。宛先が read-write になります | その関係のみ | `resyncSnapmirror`（宛先の変更は破棄されます） | DR 演習として、検証用の関係で |
| `resyncSnapmirror` | 宛先側の差分 | その関係のみ | 戻せません（差分は破棄されます） | break の後始末としてのみ |
| `blockNfsIp` / `unblockNfsIp` | 指定 IP からの NFS アクセス | エクスポートポリシーのルール単位。`allSvms` を付けると**全 SVM** | `unblockNfsIp`、または TTL 満了（`vpcRouteTableIds` 未設定だと**満了しません**） | 対象 IP を自分の検証クライアントに限定。`allSvms` は使わない |
| `blockSmbUser` / `unblockSmbUser` | 指定ユーザーの SMB アクセス | ユーザー単位。同上 | `unblockSmbUser`、または TTL 満了 | 検証用ローカルユーザーで |
| `containThreat` | 上記の組み合わせ（IP + ユーザー + セッション切断） | 指定次第で SVM 全体まで広がります | 個別の unblock | 単体の block を先に確認してから |
| `disconnectSessions` | 対象クライアントの SMB セッション | セッション単位 | クライアント側で再接続 | 自分の検証クライアントのみ |

> **TTL が満了しない条件**: 封じ込めの期限管理は EventBridge のスケジュールに依存します。
> `vpcId` を設定していて `vpcRouteTableIds` が無い場合、ブロックは期限切れにならず、応答は
> `expiryTracked: false` を返します。**この状態で封じ込めを実行すると、手で外すまで残ります。**
> 検証の前にこのフラグを確認します。

### 実行前に決めること（D 共通）

1. 対象は検証用に作ったものか。既存の利用者がいないか。
2. 実行前の状態を記録したか（DNS の現在値、LIF の状態、関係の `healthy`）。
3. 戻す操作をポータルから実行できるか。できないなら代替経路（AWS コンソール、ONTAP CLI）を
   用意してあるか。
4. `allSvms` のような**範囲を広げるフラグを使っていないか**。

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [検証結果](verification-results.md) | どこまで実機で確認したかの記録 |
| [管理機能マップ](admin-capability-map.md) | パネルごとの実装状況 |
| [リソース管理デモガイド](resource-management-demo-guide.md) | 操作手順 |
| [S3 AP の罠](../../../docs/agent/pitfalls-s3ap-ontap.md) | 対応オペレーションと実測サイズ上限 |
| [Tamperproof Snapshot 設計](../../../docs/tamperproof-snapshot-design.md) | 不可逆な保持設定の設計 |
