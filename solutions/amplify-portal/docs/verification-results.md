# ファイルポータル 検証結果

🌐 **Language / 言語**: 日本語 | [English](verification-results.en.md)

このドキュメントは、ファイルポータルの各機能について**どこまで実機で確認されたか**を記録します。実機確認と自動テストのみの状態を明確に分けることが目的です。

> **なぜこの区別が必要か**: 「テストが通る」ことは「本番で動く」ことと同じではありません。ユニットテストはハンドラーのロジックを検証しますが、ONTAP REST API の実際の応答形状、AppSync の認可、VPC の到達性、Cognito グループの伝播は検証しません。実機確認のない機能を「検証済み」と書くと、PoC の現場で最初に壊れる箇所が見えなくなります。

## 検証区分の定義

| 区分 | 意味 |
|------|------|
| **実機 E2E** | 実際の FSx for ONTAP に対してブラウザから操作し、期待した結果を確認した |
| **実機 読み取り** | 実機に対して一覧・参照は確認したが、書き込み / 変更系は未確認 |
| **自動テストのみ** | ユニット / コンポーネントテストは通るが、実機での操作確認はしていない |
| **DemoMode のみ** | FSx for ONTAP 接続なしの状態で描画とエラーハンドリングのみ確認 |

## 検証環境

| 項目 | 値 |
|------|-----|
| リージョン | ap-northeast-1 |
| ONTAP バージョン | 9.17.1（2026-07-26 / 08-07 の確認時）、9.18.1P3D1（2026-08-14 の確認時） |
| ファイルシステム ID | `fs-0123456789abcdef1`（プレースホルダー） |
| 検証日 | 2026-07-26（管理パネル群）、2026-08-07（読み取りと到達性）、2026-08-14（書き込み系） |

> **バージョンが 2 つある理由**: 検証環境の ONTAP は 07-26 以降に更新されました。エラーコードや
> フィールドの挙動を記録した項目には、観測した時点のバージョンを併記しています
> （[ボリュームライフサイクルの罠](../../../docs/agent/pitfalls-volume-lifecycle.md)、
> [FlexCache / SnapMirror の罠](../../../docs/agent/pitfalls-flexcache-snapmirror.md)）。

## 実機 E2E 確認済み

| 機能 | 確認内容 | 出典 |
|------|---------|------|
| FlexCache 作成 / 一覧 / 削除 | 作成（非同期・段階的再取得）、一覧のオリジン表示、3 段階削除（アンマウント → オフライン → 削除） | [admin-resource-management-demo (JA)](../../../docs/ja/admin-resource-management-demo.md) シナリオ 15 |
| AppSync 認可 | Cognito グループ `storage-admin` による管理エンドポイントの許可 / 拒否。パスワードリセット後に動作 | [TROUBLESHOOTING-APPSYNC-AUTH.md](TROUBLESHOOTING-APPSYNC-AUTH.md) |
| File Explorer 一覧 | S3 Access Point から 29 ディレクトリを表示 | 同デモガイド 検証結果表 |
| SMB 共有の暗号化トグル | ON / OFF の切り替えと状態反映 | 同デモガイド シナリオ 6 |
| エクスポートポリシー作成 / 削除 | ポリシー作成、ルール追加、削除 | 同デモガイド シナリオ 7 |
| ONTAP 障害の原因分類 | 認証情報が拒否された実環境で `CREDENTIALS_REJECTED` / HTTP 401 / エラーコードが UI に表示されることを確認。パスワードを揃えた後、同じパネルがスナップショット 13 件を表示することも確認（両方の状態をスクリーンショットで記録） | [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md#実際の画面表示) |
| `make ontap-preflight` | 実環境で 6 段すべてを実行。修復前は段 1〜5 PASS / 段 6 FAIL、修復後は全段 PASS。**段 6 だけが失敗する状態**という、この機能が対象とする事象そのもので確認した | 同ガイド |

### 2026-08-14 に追加（書き込み系、ONTAP 9.18.1P3D1）

いずれも実機で実行し、作成した検証用リソースは削除して元の状態に戻しています。観測したエラー
コードとフィールド値は罠ドキュメント側に記録があります。

| 機能 | 確認内容 | 出典 |
|------|---------|------|
| ボリュームの作成 / リサイズ / 削除 | 作成は `style` とアグリゲートの 2 段階を要求する（787140 / 918242）。削除は unmount → offline → delete で、offline と delete の両ジョブを待つ必要がある（524546）。**この 3 つは以前の記載では未確認でした** | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| FlexCache の write-back 有効・無効 | 作成時指定と既存キャッシュの切り替え。有効なままの削除は DELETE 上で同期的に拒否される（66846980） | [FlexCache / SnapMirror](../../../docs/agent/pitfalls-flexcache-snapmirror.md) |
| FlexCache のサイズ変更 | 100 → 50 → 100 GiB。FlexGroup なので拡大・縮小どちらもジョブが 10 秒を超えて継続する。作成時の下限は縮小には効かない | 同上、[デモガイド](resource-management-demo-guide.md) シナリオ 4 |
| SnapMirror 関係の作成 / 削除 | 宛先ボリュームの自動作成と初期化を 1 回の POST で。`create_destination.tiering.supported` と `state: snapmirrored` が必須 | [FlexCache / SnapMirror](../../../docs/agent/pitfalls-flexcache-snapmirror.md) |
| SnapMirror の一時停止 / 再開 | quiesce → resume が実ジョブ UUID を返し、ジョブ成功後に応答。関係は `snapmirrored` / healthy に復帰 | 同上 |
| SVM ピアの作成試行 / 用途の変更 | `applications` は用途ごとに個別で、`peered` でも `snapmirror` が無ければ拒否される（`SVM peer permission not found.`）。`PATCH /svm/peers/{uuid}` で解消 | 同上 |
| Qtree の作成 / 変更 / 名前変更 / 削除 | security style の変更、名前変更（id は不変、`confirm` 必須）、作成と削除を UI から | [デモガイド](resource-management-demo-guide.md) シナリオ 14 |
| クォータルールの上限変更 | tree クォータの 3 つの上限を変更し復元。REST では resize 不要で反映される | [admin-capability-map](admin-capability-map.md) |
| クォータ適用の開始 / 停止（ボリューム単位） | 書くのは `quota.enabled`、読むのは `quota.state`。ルールが無いボリュームでは ONTAP が開始を拒否 | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| ローカルユーザーの作成 / 変更 / 削除 | パスワード変更と有効・無効（`account_disabled`、262179）。**SID が変わらないこと**を確認 | 同上 |
| 名前マッピングの作成 / 変更 / 削除 / 順序の移動 | `new_index` は間のルールを renumber するが、DELETE は繰り上げない | 同上 |
| EMS イベントの取得 | **修正して初めて動作**。`fields=severity` と `severity=` フィルタはどちらも 262197 で拒否され、`message.severity` が正しい。以前は呼び出すたびに必ず失敗していた | [ARP/AI と EMS](../../../docs/agent/pitfalls-arp-ems.md) |
| ARP/AI の状態変更 | `dry_run` を要求すると `enabled` になる（ARP/AI に学習期間は無い）。無効化は `disable_in_progress` のまま 10 分以上続いた。応答は要求ではなく読み直した状態を返す | 同上 |
| データ保護画面のスコープ（SVM → ボリューム） | ARP / ロック / スナップショットの各画面が環境変数の 1 ボリュームに固定されていた。storage-admin には `SVM › ボリューム` の 2 段セレクターを出し、それ以外は既定のまま。fsxsvm02 の別ボリュームで一覧が入れ替わること、SVM を変えると選択が無効化されることを実機で確認。見出し横のバッジは、選択したボリュームか既定のボリュームかを区別して表示する | 同上 |

### 2026-08-15 に追加（書き込み系グループ A、ONTAP 9.18.1P3D1）

検証計画のグループ A のうち **A3 / A2 / A5 / A7 / A4 / A1 を実行**しました（A6 は保留。理由は
[検証計画](write-verification-plan.md) の A6 に書いています）。
検証用に作ったグループ・ユーザー・共有・Qtree・クォータルール・QoS ポリシー・FlexClone・
S3 オブジェクト、および作業用ボリューム `zz_probe_a` はすべて削除し、元の状態に戻しています。

| 機能 | 確認内容 | 出典 |
|------|---------|------|
| ローカルグループの作成 / 削除（A3） | SID は SVM のローカルドメインから採番される（末尾 -1001）。`sid` 無しの削除要求はハンドラが拒否する | [デモガイド](resource-management-demo-guide.md) |
| グループメンバーの追加 / 削除（A3） | 追加は素の名前 `zz_verify_usr` を受け付け、一覧は CIFS サーバー名付きの `FSXSVM01\zz_verify_usr` を返す。削除は**どちらの形でも通る**（バックスラッシュはハンドラが percent-encode している） | 同上 |
| 名前解決の失敗（A3） | 解決できない名前は、AD ユーザー（DC 不在）でも存在しないローカル名でも同一のメッセージ `Failed to resolve name "X".`（655673 / 400）を返す。**メッセージだけでは綴り間違いと DC 到達性を区別できない** | 同上 |
| SMB 共有の作成 / 削除（A2） | 存在しないパスは 655551 で SVM 名付きで拒否。作成された共有は既定 ACL 1 件を持つ。削除はポータル側が `confirm=true` を要求する。**削除してもボリュームは online のまま**（共有は入口の定義） | 同上 |
| SMB 共有の暗号化トグル（A2） | `updateCifsShare` の ON / OFF が一覧に即反映される | 同上 |
| クォータルールの削除（A5） | Qtree 向け tree ルールを作ると ONTAP が**既定の tree ルール（qtree 名が空）も自動作成する**。Qtree 側だけ削除すると既定ルールが残り、使用状況レポートにその Qtree が出続けるので、削除した規則が残っているように見える。削除された規則の上限はレポートから即座に消える（適用の off → on を待たない）。**適用そのものが続くかは、この 2 つの読み取りでは観測できない** | [Delete a quota policy rule](https://docs.netapp.com/us-en/ontap-restapi-9171/delete-storage-quota-rules-.html) |
| クォータ適用と使用状況レポート（A5） | 適用を off にするとレポートは 0 件になり、on に戻すと再び出る | 同上 |
| ファイル操作 8 種（A7） | `createFolder` / `createUploadLink` / `copyFile` / `renameFile` / `moveFile` / `trashFile` / `restoreFromTrash` / `deleteFileForever` を実機で一巡。上書き拒否、ごみ箱外の完全削除拒否、承認フラグ無しの拒否も確認 | [S3 AP の罠](../../../docs/agent/pitfalls-s3ap-ontap.md) |
| アップロードリンク（A7） | **修正して初めて動作**。`generate_presigned_url` の既定は presign が SigV2（`AWSAccessKeyId` / `Signature`）で、しかもグローバルエンドポイントに対して署名するため、PUT が 301 PermanentRedirect（リージョンエンドポイントを案内）で失敗していた。署名は `host` を含むのでリダイレクトを追えない。`signature_version="s3v4"` と `addressing_style="virtual"` の両方が必要（v4 だけではホストがグローバルのまま）。修正後は HTTP 200 で 27 バイトのオブジェクトが一覧に出る | 同上 |
| 5 GiB を超えるコピー（A7） | **前提を用意できないため未検証**。5 GB を超えるオブジェクトを作るにはマルチパートアップロードが必要で、それはこの Access Point で失敗する操作そのもの。代わりに、コピー前にサイズを見て理由付きで拒否するガードを入れた（単体テストのみ、実機の 5 GiB 超オブジェクトでは未確認） | 同上 |
| フォルダーの削除（A7） | **できない**。`createFolder` はあるが、`trashFile` はフォルダーを拒否し（マーカーだけ複製して中身を取り残すため）、`deleteFileForever` は `.trash/` 配下限定。UI から作ったフォルダーは UI から消せない | 同上 |
| FlexClone の作成（A4） | **修正して初めて動作**。`clone.is_flexclone: true` が無いと ONTAP はこの POST を通常のボリューム作成と読み、787140（`aggregates` か `style` を要求）で止まる。**その 787140 をアグリゲート指定で満たすと成功が返るが、できるのは 20 MB の普通のボリュームで、クローン関係は無く一覧にも出ない**（無視されたクローンブロックがサイズの出どころだった） | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| FlexClone の分割（A4） | ほぼ空のクローンでは数秒で完了し、完了と同時に**クローン一覧から消える**ので `分割中 n%` は実行中しか見えない。20 GiB のクローンが分割後 348 KB で、**容量は倍にならない**（9.4 以降は容量効率を維持。ハンドラの docstring が逆のことを書いていたので修正）。分割後も**親側に残るベーススナップショット**は利用者が削除する | 同上 |
| データ保護系ハンドラのボリューム固定（A4 で判明） | `functions/data-protection` の 9 アクション（`createSnapshot` / `deleteSnapshot` / `updateArpState` / `updateRetentionPolicy` 等）は環境変数のボリュームに固定されていた。UI からの呼び出しは無いため実害は出ていないが、スコープ付きの画面から繋ぐと固定先に効く形。`volumeName` / `svm` を受けるようにし、`zz_probe_a` のスナップショット削除が `vol1` に影響しないことを実機で確認 | 同上 |
| QoS ポリシーの一巡（A1） | 作成 → 割り当て → 割り当て中の上限変更 → `none` で解除 → 削除まで一巡。解除はポリシーを残したままボリュームの上限を 0（無制限）に戻す | [デモガイド](resource-management-demo-guide.md) |
| 割り当て中の QoS ポリシー削除（A1） | **計画の前提が崩れた**。CLI リファレンスは「割り当て中の削除は `-force` なしでは拒否される」と書いているが、9.18.1P3D1 の REST では**受け付けられ、ボリューム側の割り当ても無言で外れる**（上限が全て 0 = 無制限になる）。つまり「一巡が完了せず削除できないポリシーが残る」問題は起きない代わりに、**ポリシーを削除すると使っている全ボリュームの上限が消える**。パネルの確認文でそれを述べるようにした | [qos policy-group delete](https://docs.netapp.com/us-en/ontap-cli-9171/qos-policy-group-delete.html) |
| SnapMirror の即時更新（A6） | 既存関係（ソースが外部クラスタ）に対してアカウント所有者の承認を得て実行。転送履歴が 4 → 5 件、`transferring` を経て 12 秒 / 27,888 バイトで success。ラグは 14h59m → 1m8s、`lastTransferType` は resync → update、状態は snapmirrored / healthy を維持。宛先には新しい `snapmirror.<uuid>_<ts>` が作られ、ソース側の hourly が 7 件流れてきた（古い分は保持期間で入れ替わり、件数は 14 のまま） | [デモガイド](resource-management-demo-guide.md) |
| 転送履歴の並び順（A6 で判明） | ONTAP は順序を保証せず、実行直後の転送が 5 件中 3 番目に返ってきた。履歴として見せる画面で一番上が直前の操作でない状態だったので、ハンドラで新しい順に並べるようにした（実行中の転送は終了時刻が無いので先頭） | 同上 |
| Presign する S3 クライアントの一巡（横断確認） | アップロードリンクの不具合を受けて、presign する 7 つの関数すべてを確認。**壊れていたのは `list-files` だけ**で、他 6 つはリージョナル `endpoint_url` と `s3v4` を明示していた。path-style（明示エンドポイント）と virtual（`addressing_style`）の**両方が S3 AP エイリアスに対して 200 を返す**ことを実測。既定に任せた組み合わせだけが動かないので、それを `make drift` のルールにした | [S3 AP の罠](../../../docs/agent/pitfalls-s3ap-ontap.md) |
| クローン削除後の親ボリューム削除（再確認中に判明） | クローンを削除した直後は**親を削除できない**。API からクローンは見えない（`entry doesn't exist`、クローン一覧にも出ない）のに、親は「has one or more clones」で拒否する。親に残る `clone_<name>.<ts>` の削除ジョブも 10 秒で終わらない。推定は ONTAP の recovery queue（既定 12 時間）だが、確認には ONTAP CLI が必要で未確認 | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| スナップショット削除の 202 を待つ（同上） | `functions/data-protection` にジョブ待ちが 1 つも無く、202 をそのまま成功として返していた。上記のスナップショットは**削除成功と 2 回報告されながら一覧に残っていた**。ジョブを追って失敗理由を返すようにした | 同上 |
| 失敗した削除は親を offline のまま残す（同上） | 削除の 2 段目（offline）は成功するので、ジョブが失敗した親は offline のまま。ポータルに戻す手段が無かったので `bringVolumeOnline` を追加した | 同上 |
| 分割してからクローンを削除すると親をすぐ消せる（A/B 実測） | 同一環境で分割の有無だけを変えて比較。未分割のクローンを削除 → 親の削除は失敗（`has one or more clones`、7 分後・15 分後も同じ）。分割 → 削除 → 親の削除は数秒後に成功。原因は ONTAP の volume recovery queue（RW/DP の削除は既定 12 時間キューに保持され、その間もアグリゲート容量を消費し、親から見るとクローンが存在する） | [Volume Recovery Queue (KB)](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_to_use_the_Volume_Recovery_Queue) |
| recovery queue は REST から読めて purge も `fsxadmin` で通る（**以前の記述を訂正**） | 「`purge` は diag 権限が必要で fsxadmin では到達できない、つまり待つしかない」と書いていたが誤り。`GET /api/private/cli/volume/recovery-queue` で一覧でき、`POST /api/private/cli/volume/recovery-queue/purge` が 202 を返して 20 秒ほどでキューから消える。ブロックしていたクローンを purge した直後に親（`zz_recheck_src`）の削除が成功。キュー上の名前にはサフィックスが付く（`zz_recheck_clone_1106`）ので元の名前では照合できない。`DELETE` はコレクションに無く 405、`fields=*` も拒否される。purge は取り消せないので、自分が削除したと分かっているボリュームにのみ使う | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| 分割の UI 補足（今回追加） | FlexClone パネルに「使いどころ」4 点と「性質」6 点を折りたたみで追加（9.4 以降はメタデータのみでデータをコピーしない / 元に戻せない / 進捗は inode 基準 / 分割中はクローンにスナップショットを作れない / オフラインで中断・オンラインで再開 / アグリゲートは選べず DP 関係のクローンは分割不可）。確認文の「容量を全量消費します」は 9.4 以降では誤りだったため訂正。削除が「クローンがある」で失敗したときは、recovery queue と分割の案内をエラーに添える | [ONTAP docs](https://docs.netapp.com/us-en/ontap/volumes/split-flexclone-from-parent-task.html) / [KB](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/FAQ_-_FlexClone_split) |

### 2026-08-15 に追加（容量とボリュームタイプ、ONTAP 9.17.1P6）

ボリューム一覧の使用率が何を数えていて何を数えていないか、および FlexVol と FlexGroup の
差を実機で確認しました。検証用に作成した FlexGroup `zz_fg_probe` は削除しています。

| 機能 | 確認内容 | 出典 |
|------|---------|------|
| 使用率が数えているもの（読み取り） | `space.used` は**ボリュームによって別の量を指す**。Snapshot リザーブ内の Snapshot は含まず、リザーブを超えた分は含む。実測: 100 GiB のボリュームが `used` 18.1 MiB を報告しながら Snapshot 77.3 MiB を保持（Snapshot リザーブ 5% = 5 GiB の内側）。Snapshot リザーブ 0% のボリュームは `used` 83,677 MiB = 実データ 81,934 MiB + Snapshot 1,743 MiB。**11 ボリューム中 8 本で Snapshot が実データを上回っていた**ので、一覧に実データ / Snapshot / リザーブ超過を分けて出すようにした | [Snapshot リザーブ](https://docs.netapp.com/us-en/ontap/data-protection/manage-snapshot-copy-reserve-concept.html) / [spill (KB)](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_can_impact_snapshot_size_and_cause_snapshot_spill) |
| ボリュームタイプの表示（読み取り） | `style` は以前から取得していたが表示していなかった。実機には両方あり、FlexCache の**オリジンが FlexVol（vol1）・キャッシュが FlexGroup（flexcache_eda_tokyo）**という組み合わせを確認（キャッシュ側は常に FlexGroup） | [FlexCache REST 概要](https://docs.netapp.com/us-en/ontap-restapi-9171/manage_flexcache_volumes.html) |
| FlexGroup の作成 | **修正して初めて動作**。ONTAP の自動配置は FSx for ONTAP では常に失敗する（`Aggregates not matching FabricPool requirements: aggr1`）。アグリゲートを明示すると成功。既定の 4 コンスティチュエント構成では 400 GB 未満が拒否される。**同じ根本原因は FlexCache 側で既知（`use_tiered_aggregate`）だったのにボリューム側へ来ていなかった** | [ボリュームライフサイクル](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| リバランス状態の読み取り | `rebalancing` は明示要求フィールドで、`fields=**`（56 キー）でも**返らないボリュームがある**。ONTAP S3 バケットの実体（`is_object_store: true`）と FlexCache キャッシュはどちらも FlexGroup だが返らない。通常の FlexGroup では返り、既定値はドキュメント記載と一致（`PT6H` / 100 MB / 20% / 5% / 25 / exclude_snapshots true、`granular_data: false`）。**オブジェクト不在を `state: unknown` に丸めると「均衡したボリューム」に見える**ので別のフラグで区別した | [リバランス](https://docs.netapp.com/us-en/ontap/flexgroup/manage-flexgroup-rebalance-task.html) / [S3 バケットは非対応 (KB)](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_it_necessary_to_manually_balance_constituents_of_an_S3_bucket_hosting_flexgroup%3F) |
| リバランス開始の拒否 4 種 | 承認フラグ無し / FlexVol / オブジェクトストアの実体 / ISO-8601 でない `maxRuntime` の 4 つを実機で拒否確認 | 同上 |
| リバランスの開始・停止・予約（アカウント所有者の承認を得て実施） | 一巡を実行し、**API リファレンスに無い 2 つの実行時間制約**を確定。`max_runtime` は 30 分以上（`144182221`）かつ次回スナップショット取得までの残り時間より短い（`13107433`）必要があり、**ONTAP 既定の 6 時間では常に失敗する**。既定ポリシー（毎時 :05）では開始できるのは毎時 :05〜:35 のみ。60 分 / 30 分の 1 秒差 A/B で境界を確定。ボリューム状態に未記載の `idle`（実行中・移動対象なし）と `scheduled` が返り、実行中が「不明」と表示されていた。移動対象が無い実行は notice を出さず `runtime` だけが増える。停止しても `granular_data` は `true` のまま（不可逆性の実測確認）。予約の取り消し後も `start_time` が残る | [FlexGroup 容量リバランスの実測記録](flexgroup-rebalance-verification.md) |
| 二重開始のガード（上記で判明） | ポータルのガードが `starting` / `rebalancing` だけを見ており、実測で返る `idle` / `scheduled` を通していた。ONTAP 側が `144182216` で拒否するため実害は無かったが、`not_running` / `unknown` 以外を進行中として扱う形に反転した | 同上 |
| 新規 FlexGroup は空ではない（同上） | 400 GiB / 4 コンスティチュエント構成で、各メンバーがメタデータで約 537 MB（合計約 2.1 GB）を使用。メンバー間の差は最大約 12 KB | 同上 |
| FlexVol → FlexGroup の変換 | **REST API に無い**（`volume conversion start` は CLI の advanced 権限専用）。AWS は in-place 変換ではなく AWS DataSync での新規 FlexGroup へのコピーを推奨し、変換前に FSx バックアップの削除を求めている。ボタンは作らず、前提条件・不可逆性・Snapshot の扱いを画面の補足に入れた | [AWS docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| 期間ラベルの時間対応（今回判明） | `durationLabel` が日数のみを解釈し、未知の値はそのまま返す設計だったため、リバランスの最大実行時間の選択肢が ONTAP の既定値を `PT6H` という文字列で表示していた | — |

### 2026-08-15 に追加（SnapLock と Snapshot のロック、ONTAP 9.18.1P3D1）

**以前は「不可逆なので実行しない」に分類していた区分 C を、アカウント所有者が保持期間の値を
名指しして承認したうえで実行しました。** 実行できたのは、ONTAP が保持期間を秒単位（0〜65535 秒）
で受け付けるためです。5 分保持なら数分で満了し、その後ボリュームを削除できます。

検証用に作成した `zz_sl_ent` / `zz_sl_comp` / `zz_lock_probe` はすべて削除し、元の 10 本に戻しています。

| 機能 | 確認内容 | 出典 |
|------|---------|------|
| SnapLock enterprise / compliance ボリュームの作成 | `snaplockType` と `retentionMin` / `retentionDefault` / `retentionMax` を指定して作成し、`getSnaplockConfig` で読み戻し。**ONTAP は `PT5M` を受理**（min=`PT0S` / default=`PT5M` / max=`P1D`）。`complianceClockTime` も返る | [保持期間の設定](https://docs.netapp.com/us-en/ontap/snaplock/set-retention-period-task.html) |
| 承認フラグの強制 | `acknowledgeIrreversible` 無しの作成要求は両タイプとも拒否される | 同上 |
| 保持期間の変更 | `updateSnaplockRetention` の `days=1` で volume の default が `PT5M` → `P1D`。**volume の既定値と、確定済みファイルの保持期間は別物**（後者は延長のみ） | 同上 |
| **空の SnapLock ボリュームは削除できる** | compliance でも `deleteVolume` が 90 秒以内に完了し、一覧から消えた。WORM ファイルを 1 つも確定していない状態では削除可能。UI の「作成直後の空のボリュームは削除できます」を実測で裏付け | — |
| Snapshot のロック機能の有効化 | 承認フラグ無しは拒否。有効化後は `snapshotLockingEnabled: true`（不可逆） | [Tamperproof Snapshot 設計](../../../docs/tamperproof-snapshot-design.md) |
| Snapshot のロック実行 | `lockSnapshot` が `expiryTime` を返し、`getSnapshotLockingStatus` の `lockedSnapshotCount` が 1 になる | 同上 |
| **ロック済み Snapshot はボリュームの削除を止めない** | ロック済みの Snapshot を持つボリュームを `deleteVolume` したところ、20 秒後に一覧から消えた。SnapLock の WORM ファイルとは影響範囲が違う。ポータルの文言（`slcSnapshotScope`「他の Snapshot とボリューム本体には影響しません」）と整合する | — |
| **Snapshot 一覧のロック表示が壊れていた（修正済み）** | ONTAP は Snapshot に 2 つの満了フィールドを持つ。`expiry_time` が Snapshot のロック、`snaplock_expiry_time` が SnapLock ボリューム由来。`lockSnapshot` は前者に書くが、一覧を作る `_get_snapshots` は**後者だけを `fields=` に指定して読んでいた**ため、**ポータルでロックした Snapshot は一覧で必ず「ロックされていない」と表示された**。2 つのパネルが同じ Snapshot について食い違ったことで判明。両方を読むよう修正し、旧コードで落ちるテストを 4 件追加 | — |

> **UI からはこの検証手順を再現できません。** ポータルの `asIsoDuration` は日単位（Y/M/W/D）しか
> 受け付けず、`updateSnaplockRetention` は `days` しか取りません。ONTAP 側は秒単位を受けるので、
> これは UI 側の制約です。**利用者は現状 UI から 1 日未満の保持期間を指定できません。**

### 2026-08-16 に再確認（C4 を Lambda 再デプロイ後に再実行）

C4 は Lambda を数回再デプロイしたあとに走らせ直しました。前回と同じ結論に加えて、
ロック表示の修正が実機のロック済み Snapshot で効いていることを確認しています。
検証に使った `zz_lock_probe`（20 GiB）は削除済みで、残っているリソースはありません。

| 確認内容 | 結果 |
|---------|------|
| 承認フラグ無しの有効化 | 拒否（`acknowledgeIrreversible=true is required...`） |
| 有効化後の状態 | `snapshotLockingEnabled: true`、`lockedSnapshotCount` が 1 に増える |
| `retentionDays=1` の満了 | `expiryTime: 2026-08-16T18:54:28Z`（要求の約 24 時間後） |
| **一覧のロック表示** | 同じ Snapshot を一覧側から読み直して `isTamperproof: true` / `snaplockExpiryTime` あり。`expiry_time` を読まずロック表示が壊れていた不具合の修正が、実機のロック済み Snapshot で効いている |
| ロック済み Snapshot とボリューム削除 | 削除は成功し、20 秒後に一覧から消えた（前回と同じ） |

### 2026-08-16 に追加（C5 / C6 / C7）

| 区分 | 確認内容 | 結果 |
|------|---------|------|
| C5 | 保持期間付き Snapshot ポリシーの作成・割り当て・削除 | 承認フラグ無しは拒否。`retentionPeriod: P1D` で作成・割り当て・既定への差し戻し・削除がすべて成功 |
| C5 | 割り当て後のロック状態表示 | **`snapshotLockingEnabled` は `false` のまま**で、変わるのは `snapshotPolicy` だけ。状態パネルだけを見ると「何もロックされない」と読める。詳細は [tamperproof-snapshot-design.md](../../../docs/tamperproof-snapshot-design.md) |
| C6 | Object Lock GOVERNANCE 1 日 | 既定ルール `{Mode: GOVERNANCE, Days: 1}`。オブジェクトは `GOVERNANCE until ...` を継承。bypass 無しの削除は拒否、`--bypass-governance-retention` 付きは**成功** |
| C7 | Object Lock COMPLIANCE 1 日 | 承認フラグ無しは拒否。既定ルール `{Mode: COMPLIANCE, Days: 1}`。**bypass を付けた削除も拒否**され、GOVERNANCE の逃げ道が効かないことを実測 |
| C6/C7 | 2 モードの区別 | **拒否メッセージが同一**（`AccessDenied ... object protected by object lock`）。モードは `get-object-lock-configuration` と `head-object` の `ObjectLockMode` で読む |

検証に使った `zz_policy_probe`（20 GiB）と `zz_lock_1d` は削除済みです。
バケット `zz-objectlock-probe-<下 6 桁>` は COMPLIANCE オブジェクト 1 つのため
**2026-08-16T19:24:41Z まで削除できません**（数十バイト、実質 $0、満了後に削除）。

**未確認**: C5 のスケジュールが発火して生成された Snapshot が実際にロックされるか。
日次スケジュールの発火を待っていません。

> **C6 の実行にはガードの変更が必要でした。** 不可逆操作ガードは
> `putS3ObjectLockRetention` を無条件にブロックしつつ、拒否メッセージで GOVERNANCE を
> 勧めていました。勧めた選択肢を取る手段が存在しなかったため、GOVERNANCE の検証に着手
> できませんでした。有効化はブロック、既定ルールの設定は確認（ask）、厳格モードはブロックの
> まま、に分離して実行しました。段の分け方は
> [tamperproof-snapshot-design.md](../../../docs/tamperproof-snapshot-design.md)。
>
> 副作用として、ガードはシェルコマンドの文字列を見るため、モード名を含むソース編集も
> ブロックします。専用の編集ツールを使えば通ります。

### 2026-08-16〜17 に追加（C8 / C9: WORM 確定、削除ブロック、S3 AP 経由の削除、マウント管理）

**VPC 内に NFS クライアント（t3.micro / AL2023）を立てて、これまで確定できなかった WORM を実際に
確定しました。** 使用したボリュームは `zz_sl_worm`（fsxsvm01、compliance、min `PT0S` / default `PT5M` /
max `PT1H`、20 GiB）と `zz_sl_s3ap`（fsxsvm02、compliance、min `PT0S` / default `PT5M` / max `PT5M`、
20 GiB）。保持 5 分なので数分で満了し、その後削除できます。

| 機能 | 確認内容 |
|------|---------|
| **WORM 確定（NFS）** | `chmod a-w` で `-r--r--r--` になり、**atime が満了日時を保持**する |
| **満了日時は compliance clock 基準** | 壁時計 `03:37:33Z` に確定したファイルの満了が `03:42:14Z`。既定 5 分なので確定時点の clock は `03:37:14`——**壁時計より約 19 秒遅れ**。別ボリュームでも同じ差 |
| 確定後に拒否される操作（NFS） | 上書き（`>`）、`rm`、`chmod u+w`、`truncate`、`mv` がすべて rc=1。読み取りは可 |
| **切り詰めない書き込みは成功を返して無言で捨てられる** | `>>` が rc=0、Python の `open('a').write()` と `open('r+').write()` も rc=0。しかし size 29 と md5 は不変。唯一 `dd` が `close()` で `Read-only file system`（EROFS）を出した。**アプリから見ると書き込みが成功して消えます** |
| **未満了 WORM があるボリュームの削除** | `deleteVolume` がジョブ失敗で理由を返す（`The volume has unexpired WORM files or ...`）。AWS FSx API の無言成功とは別で、ONTAP REST は理由を言う |
| **拒否された削除がボリュームを孤立させる** | 削除は unmount → offline → delete の 3 段で、前 2 段が成功してから拒否される。結果として `nas.path` が消え state が offline になり、クライアントから到達できない。`bringVolumeOnline` は意図的に再マウントしない設計 |
| offline 中の満了列挙 | `listExpiredRetention` が `clockSource: "unavailable"` を返し判定を拒否する（設計どおり）。ただし**拒否された削除が満了列挙を盲目にする**連鎖になる |
| **`retention.maximum` が縛るのは確定時の割り当てだけ** | 2 段階で測りました。**確定前**に atime を max より 1 分先（`PT5M` のボリュームで +6 分）に設定してから `chmod a-w` すると、touch は rc=0 だが確定後の満了は既定の 5 分後になり、**要求した値は残らない**（同じボリュームで既定のまま確定したファイルと同一時刻）。一方**確定後**に同じ +6 分へ延長すると rc=0 で**満了が max を 1 分超えた時刻に変わる**。max `PT1H` のボリュームで +70 分が通ったのと同じ挙動で、こちらはより小さい差で確認しました。短縮は rc=1。**つまり max は確定時の上限であって、その後の延長の天井ではありません** |
| **満了後（NFS）** | `rm` が成功。ただし**上書きは満了後も拒否**され、mode も `-r--r--r--` のまま。**満了は削除を許すだけで、ファイルを普通のファイルに戻しません** |
| **S3 AP は SnapLock ボリュームに attach できる** | `zz_sl_s3ap` に対して `CreateAndAttachS3AccessPoint` が約 15 秒で `AVAILABLE`。SnapLock は attach の障害にならない |
| **ONTAP S3 サーバーがある SVM には attach できない** | fsxsvm01 では `FAILED` になり `existing ONTAP object storage server on SVM ...` と返る。**同一 SVM で ONTAP ネイティブ S3 と FSx for ONTAP S3 AP は共存しない** |
| **ONTAP REST で設定した junction は FSx API に即座に映らない** | マウント直後の attach が `the volume is not mounted` で失敗し、`describe-volumes` の `JunctionPath` は 5 分以上 null。`update-volume` に `JunctionPath` を渡すと**成功を返して値は変わらない**（無言の no-op）。その後収束したが、収束が `update-volume` によるものか自然な同期かは切り分けていない。**エラーメッセージは正しくない原因を名指しします** |
| S3 AP 経由の書き込みと一覧 | `PutObject` / `ListObjectsV2` / `GetObject` が成功。`StorageClass` は `FSX_ONTAP` |
| **満了前の S3 AP 削除・上書き** | `DeleteObject` と `PutObject`（上書き）がともに `AccessDenied`。`GetObject` は成功し ETag も不変 |
| **満了後の S3 AP 削除** | `DeleteObject` が**成功**し、一覧からも NFS 側からも消えた。**上書きは満了後も `AccessDenied`**（NFS 側と同じ挙動） |
| **拒否メッセージが原因を示さない** | S3 AP 側の拒否は `AccessDenied ... Access Denied` だけで、**WORM も保持期間も出てきません。** IAM の問題と区別できないため、最初に確認するのは権限ではなくファイルの WORM 状態 |
| **`listExpiredRetention` を実 WORM データで確認** | `expired` に満了済みの `zz_sl_s3ap`、`pending` に 2027-02-06 満了の監査ログボリューム、`clockSource: "ontap"`。これまで clock 不在時の応答しか確認できていませんでした |

> **S3 AP が残す NAS バケットのブロックは一時的です（2026-08-18 に解消を確認）。** S3 AP を
> detach・delete しても ONTAP 側の `amazon-fsx-<volume-id>` バケットが残り、`deleteVolume` が
> それを名指しして失敗します（FSx 側の attachment は 0 件）。`FAILED` になった attach でも
> 同じ残骸ができ、1 日後も残っていました。**`GET /protocols/s3/buckets` はこの NAS バケットを
> 返しません**——該当 SVM では 0 件、ネイティブ S3 サーバーがある SVM でも `type: s3` の 3 本
> だけです。（以前ここに「このエンドポイントは `fsxadmin` に 401 を返すことがある」と書いて
> いましたが**削除しました**。`6691623 "User is not authorized."` は誤ったパスワードでも
> ロックアウト中でも同一の文言なので、401 をエンドポイント側の制限として読むことはできません。
> 同じ誤りは `/storage/flexcache/flexcaches` について一度撤回しています。）
>
> **ONTAP CLI は不要でした。** 拒否から約 1 日後に `DeleteVolume` を再実行すると `zz_sl_s3ap` /
> `zz_sl_worm` はどちらも 60〜90 秒で削除完了しました（CLI 操作は一切していません）。関連は
> 非同期に解けるので、正しい対処は `vserver object-store-server bucket delete` を探すことでは
> なく**時間を置いて再試行すること**です。解消までの正確な時間は測っていません（約 1 日後に
> 成功したという 1 点のみ）。**WORM のロックではありません。**

### 2026-08-17 に追加（マウント管理: `mountVolume` / `unmountVolume` / `getVolumeMountInfo`）

**拒否された削除が残す「online だが未マウント」の状態を、ポータルから戻せるようにしました。**
`bringVolumeOnline` が offline を戻す一方、junction を戻す手段が無かったためです。

| 機能 | 確認内容 |
|------|---------|
| `bringVolumeOnline` → `mountVolume` の往復 | 拒否された削除で孤立した `zz_sl_worm` を online に戻し、`/zz_sl_worm` に再マウントして復旧。**この経路は以前は存在しませんでした** |
| マウント済みボリュームへの再マウント要求 | 現在のパスを名指しして拒否（`already mounted at "/zz_sl_worm"`）。移動を副作用にしない |
| `getVolumeMountInfo` | データ LIF（`data_nfs` を持つ LIF のみ）、`cifsServerName`、`cifsDomain`、`nfsReady` / `smbReady` を返す。管理 LIF は候補に出ない |
| 未マウント時の提案パス | `suggestedPath` が `/<ボリューム名>` を返し、UI がそれを初期値にする |

### 未確認のまま残るもの（SnapLock）

| 項目 | なぜ未確認か |
|------|------------|
| enterprise の privileged delete | 監査ログボリュームを要求し、それが**最短 6 か月**ボリューム → SVM → ファイルシステムの削除をブロックする。AWS API に監査ログの保持期間を指定するフィールドが無く、既定の 6 か月が適用される。**値を短くする逃げ道が無いため実行しない** |

## 実機 読み取り確認済み（書き込み系は未確認）

| 機能 | 確認できたこと | 未確認 |
|------|--------------|--------|
| SnapMirror | 関係の一覧、状態バッジ、ラグ表示（作成・削除・一時停止・再開は上表で確認済み） | 即時更新 / break / resync / 転送の中止 |
| Storage Efficiency | 9 ボリュームで 1.21x、17.7% 削減 | （読み取り専用機能） |
| Snapshot 管理 | ポリシー一覧、改ざん防止状態の照会 | ロックの実行、ポリシーの作成・割り当て・削除 |
| ARP/AI | 9 ボリュームの状態（すべて disabled） | 状態変更 / 一括有効化 / 疑いのクリア / 脅威封じ込め |
| SnapLock | 全ボリューム non_snaplock | WORM 設定（**不可逆操作のため検証環境では実行しない**） |
| QoS | ポリシー一覧（この環境では 0 件） | 作成 / 変更 / 削除 / ボリュームへの割り当て |
| SMB 共有 | 4 共有の一覧、暗号化トグル | 共有の作成 / 削除 |
| ローカルグループ | 一覧 | 作成 / 削除 / メンバーの追加・削除 |
| FlexClone | 一覧 | 作成 / 分割 |
| FPolicy / Vscan | 3 タブ構成の描画 | ポリシー設定（外部エンジンが前提） |
| クラスターピア | 一覧、intercluster LIF の一覧 | 作成 / 承認 / 削除（相手クラスター側の操作が必要） |
| クラスター情報 | ノード・ライセンス・LIF・プロトコル・DNS・ジョブの一覧 | LIF / プロトコルの無効化、DNS の更新 |

> **SnapLock を検証環境で実行しない理由**: 未満了の WORM ファイルはボリューム → SVM → ファイルシステムの削除を連鎖的にブロックします。監査ログボリュームを作った場合、最短 6 か月はファイルシステムを削除できません。詳細は [Tamperproof Snapshot 設計](../../../docs/tamperproof-snapshot-design.md)。

## 未実行の書き込み操作（理由別）

「まだ実行していない」を 1 つの塊にすると、順番に片付ければ済むものと、前提が無くて実行でき
ないもの、意図的に実行しないものが混ざります。実行できるかどうかで判断できるように分けます。
操作ごとの前提・手順・影響・戻し方は [書き込み操作の検証計画](write-verification-plan.md) にあります。

| 分類 | 対象 | 判断 |
|------|------|------|
| **A. 安全に実行できる** | **2026-08-15 に A1〜A8 をすべて実施**。残る未実行は SnapMirror の**転送中止**と **5 GiB 超のコピー**の 2 点 | 中止は 12 秒の転送窓があるので技術的には狙えるが、自分のものでない関係を unhealthy にするため所有者の承認が必要。5 GiB 超は前提を作れない（マルチパートアップロードが必要で、それがこの Access Point で失敗する操作そのもの） |
| **B. 外部の前提が無い** | Vscan 4 件、FPolicy 5 件、クラスターピア 3 件、SVM ピアの承認・削除 | 外部スキャンエンジン、FPolicy エンジン、相手クラスターでの accept が必要。FPolicy は `engine: native` なら到達できる可能性がある |
| **C. 不可逆だが値を短くして実行した** | SnapLock 保持期間、Snapshot のロック機能、ロックの実行 | **2026-08-15 に実施**（下の 08-15 の表）。ONTAP が保持期間を秒単位で受けるため、5 分保持で満了させてから削除できた。残るのは WORM 確定（NFS/SMB クライアント待ち）と privileged delete（監査ログが最短 6 か月なので実行しない） |
| **D. 共有環境に影響が及ぶ** | LIF の無効化、プロトコルサービスの無効化、DNS 更新、SnapMirror の break / resync、ARP 封じ込め系 6 件 | 経路・セッション・レプリケーションを切ります。対象と時間帯を決めてから実施します |
| **E. ONTAP 非依存** | エージェント / チーム / セッション、ポータル設定、サムネイル | Bedrock・DynamoDB・S3 側の話で、実機 ONTAP の検証対象ではありません |

> **ドキュメント調査で先に見つけた 2 件は、実測でどちらも前提が変わりました**（実行前の予想を
> 残すのは、次に同じ資料を読む人が同じ結論に至るためです）
>
> - 予想: **QoS は使用中のポリシーを削除できないので一巡が完了しない**（CLI リファレンス）。
>   実測: 9.18.1P3D1 の REST では**削除でき、ボリューム側の割り当ても無言で外れます**。
>   一巡は完了する代わりに、削除が「使っている全ボリュームの上限を外す操作」になります。
>   `none` による解除は、ポリシーを残して 1 つのボリュームだけ外す手段として必要です。
> - 予想: **クォータルールを削除しても適用を off→on するまで効き続ける**（REST リファレンス）。
>   実測: 削除した規則の上限は使用状況レポートから即座に消えました。適用そのものが続くかは
>   この 2 つの読み取りでは観測できないため、リファレンスの記述を根拠として扱い、ポータルは
>   削除後に off→on を案内するようにしました。

## 自動テストのみ（実機操作は未確認）

2026-08-07 の時点で到達可能にした機能群です。ハンドラーとコンポーネントのテストは通りますが、実機のブラウザ操作では確認していません。

| 機能 | テスト | 実機で確認すべき点 |
|------|-------|-------------------|
| SnapMirror 転送の中止 | `SnapMirrorStatus` 経路のユニット | ONTAP が `state=aborted` の PATCH を受理するか、中止後の状態遷移。**転送中でなければ中止は失敗する**ので、続く長さの転送を先に作る必要があります |
| ファイル名変更 / ごみ箱 / 復元 | `FileLifecycle.test.tsx` 13 件 | S3 AP 上の CopyObject + DeleteObject の実挙動、大きなファイルでの所要時間。**5 GB を超えるオブジェクトは単発 CopyObject で複製できず**、代替の `UploadPartCopy` はこの環境で `NoSuchKey` になります |
| アップロードリンク | 同上 | 署名付き PUT URL が S3 AP で実際に書き込めるか（**署名バージョンは v4 必須**） |
| エージェント / チームの実行 | `functions/agent-chat/tests/` 21 件 | Bedrock 呼び出し、ツールの積集合、共有エージェントの認可 |
| エージェント定義の編集 | `AgentDirectory.test.tsx` 9 件 | DynamoDB の部分更新、作成者以外の拒否 |
| Glue カタログブラウザー | `CatalogBrowser.test.tsx` 8 件 | Glue Crawler 実行後のデータベース / テーブル / 列の表示 |
| 文書のテキスト抽出 / 解析 | `DocumentAnalysis.test.tsx` 8 件 | Textract / Comprehend の実応答、リージョン間呼び出しの要否 |
| AI メタデータバッジ | `AiMetadataBadges.test.tsx` 9 件 | AI メタデータテーブルに実データがある状態での表示 |
| QR コード生成 | 同上 | 生成した QR から署名付き URL に到達できるか |
| フォルダー監視 / イベント通知 | `functions/list-files/tests/test_notifications.py` 9 件 | FPolicy → EventBridge → ブリッジ Lambda の実配送、実イベントの形状、グループ境界の絞り込み |

### 自動テストの数え方

件数そのものではなく、**数える方法**を書きます。この表は以前 6 スイート分の件数を固定値で
持っていて、そのうち 5 つが古くなっていました（resource-management は 258 と書いて実際は
300、vitest は 321/24 ファイルで実際は 337/26 ファイル、ディスパッチ契約は 173/170 で実際は
180/174）。誰も更新しない数値は、書いた時点でしか正しくありません。

| スイート | 件数を出すコマンド |
|---------|------------------|
| ポータルのコンポーネント / ユーティリティ（vitest） | `cd solutions/amplify-portal && npx vitest run` |
| `functions/*`（pytest） | `python3 -m pytest solutions/amplify-portal/functions/<name>/tests/ -q` |
| ディスパッチ契約（呼び出し箇所とアクション） | `python3 scripts/check_portal_action_params.py` |
| ディスパッチのアクション型 | `python3 scripts/portal_action_types.py --check` |

規模の目安（丸めた総数）は [AGENTS.md](../../../AGENTS.md) にあります。そちらのファイル数は
`make drift` がツリーと照合するので、古くなれば fail します。**件数は照合していない**ため、
上のコマンドが唯一の出典です。

## DemoMode のみ

| 機能 | 内容 |
|------|------|
| Vscan セットアップ案内 | 5 ステップの案内、6 ベンダー比較表、外部リンク |
| S3 Object Lock タブ | ONTAP 非依存で描画されること |
| 管理パネル全般（ONTAP 未接続時） | 「ONTAP 接続が必要です」の穏当な表示 |

## 既存の Cognito User Pool は CloudFormation で更新できない（2026-08-27 実測）

2026-08-11 に作成した sandbox に、2 軸認可（グループ 6 個の宣言、自己サインアップの既定変更）を
デプロイしようとして判明しました。**この User Pool は作成以降に一度も更新されておらず、今回が
初回の更新でした。そして更新は成立しませんでした。**

CFN が触ったのは User Pool のみで、追加予定だったグループ 6 個には到達していません。

| 送った内容 | Cognito の応答 |
|---|---|
| 構築物が既定で出す `Schema`（`AttributeDataType` なし） | `Invalid AttributeDataType input, consider using the provided AttributeDataType enum.` |
| `AttributeDataType: "String"` を明示（Cognito が保持している値と同一） | `Required custom attributes are not supported currently.` |

2 段で拒否される理由が違います。1 つ目は**作成時に推論される属性型が更新時には必須**であるため。
2 つ目は、**更新時の `Schema` が「追加する属性」として解釈される**ためで、既存と同一のものを
再送しても「必須属性を追加しようとしている」と読まれます。つまり**更新で `Schema` を送る方法が
そもそも存在しません**。

CloudFormation はこれを
`User pool attributes cannot be changed after a user pool has been created`
と報告します。**「変更できる項目が限られている」と読めますが、実際は要求が不正だという話**なので、
どの属性を変えたのかを探しても原因に届きません。

> **重要**: 変更した内容が意味的に no-op でも失敗します。今回 `AdminCreateUserConfig.AllowAdminCreateUserOnly`
> を `true` にする override を入れましたが、**プールは既に `true` を保持していました**。それでも
> テンプレート側にプロパティが増えた時点で更新が走り、Schema の再送で落ちます。

**回避手段はありません。** `addPropertyOverride` で Schema を補う案は試して上記のとおり失敗したので、
コードには残していません（効かない対策が対策の形で残るほうが害があるため）。Amplify 自身が案内する
「`defineAuth` を外して deploy し、戻す」も sandbox の作り直しも、**プールの全ユーザーを削除します**。

**新規デプロイは影響を受けません。** プール作成時にすべてが入るためで、この制約は「既存プールに後から
変更を当てる」場合にのみ現れます。

**実務上の帰結**: `defineAuth` に触る変更（グループの追加、MFA、自己サインアップ）は、既存 sandbox に
段階的に当てられません。別 identifier の新しい sandbox（`npx ampx sandbox --identifier <name>`）で
検証するのが、何も壊さずに確認できる唯一の経路です。

## 2 軸認可を実機デプロイして確認（2026-08-27、identifier 付き sandbox）

既存 sandbox の User Pool が更新できないため（前節）、`--identifier phase2auth` で別の sandbox を
作って確認しました。**新規プールでは問題なくデプロイできます**——制約は既存プールへの後追い変更だけに
現れます。

| 確認項目 | 結果 |
|---|---|
| Cognito グループ 6 個（role 4 + scope 2） | 作成された（`auditor` / `contributor` / `external` / `internal` / `storage-admin` / `viewer`） |
| `selfSignUpEnabled: false` | `AdminCreateUserConfig.AllowAdminCreateUserOnly = true` として反映 |
| `enforceRoles: true` の AppSync 規則 | `fileMutation` と `folderMutation` に `cognito_groups: ["contributor","storage-admin"]`、`queryAuditLog` に `["auditor","storage-admin"]`（`viewer` は不在）。デプロイ済みスキーマで確認 |
| IAM 経由の迂回 | **不可**。各フィールドに `@aws_iam` も付くが、Identity Pool の authenticated ロールに appsync 権限が無い（インライン・アタッチ済みの両方を確認） |
| ledger テーブル | 作成、TTL（`ttl`）有効、PITR 有効 |
| `make portal-grant-roles` | 付与・冪等な再実行・拒否（role 2 つ / scope 無し）すべて期待どおり |

### 判明した制約 1: sandbox による `RemovalPolicy.RETAIN` の無効化

デプロイ済みテンプレートでは、**コードで `RETAIN` を指定している全テーブルが `DeletionPolicy: Delete`**
になります。新規の `PortalActivityLedgerTable` だけでなく、既存の `ContainmentBlocksTable` も同じです。
sandbox は `sandbox delete` で残骸を作らないよう一律で上書きします。

**帰結**: 「監査証跡はスタック削除後も残る」という保護は **sandbox には存在しません**。branch
デプロイで `RETAIN` が尊重されるかは**未確認**です（この sandbox でしか測っていません）。

### 判明した制約 2: 2 つの sandbox は同一 VPC で共存できない

同じ VPC・同じルートテーブルに 2 つ目の sandbox を作ると、DynamoDB ゲートウェイエンドポイントが
衝突します:

```
route table rtb-... already has a route with destination-prefix-list-id pl-...
(HandlerErrorCode: AlreadyExists)
```

ゲートウェイエンドポイントはルートテーブル単位で 1 つなので、2 つ目のスタックが自分の分を作れません。
回避は、検証用 sandbox を VPC 無しで動かすこと（`AMPLIFY_PORTAL_VPC_ID` に空白 1 文字を渡すと
`.trim()` で空になります。空文字は `||` に弾かれて既定値へ落ちるため効きません）。認可の確認に VPC は
不要です。

### 判明した制約 3: `JobExecutionTable` の初回作成での競合

`Attempt to change a resource which is still in use: Table is being created` で 1 度失敗しました。
Amplify のテーブル管理カスタムリソースと DynamoDB の競合で、**再試行で解消します**。恒久的な問題では
ありません。

## デプロイ時間の記録

記録されているデプロイ時間はドキュメント間で異なります。数値を平均するのではなく、差の理由を示します。

| 項目 | 記録値 | 出典 | 条件 |
|------|-------|------|------|
| `npx ampx sandbox` 初回 | 3〜5 分 | [README](../README.md) | VPC なし（DemoMode） |
| `npx ampx sandbox` 初回 | 8〜12 分 | [pr-ephemeral-environments.md](pr-ephemeral-environments.md) | — |
| `make sandbox` 初回 | 10〜15 分 | [cleanup-guide.md](cleanup-guide.md) | CDK bootstrap を含む |
| `npx ampx sandbox` 差分 | 2〜3 分 | [pr-ephemeral-environments.md](pr-ephemeral-environments.md) | — |
| `npm run build` | 0.25〜0.51 秒 | 本セッションで実測 | Vite |

> **なぜ差が出るか**: VPC 内 Lambda は ENI の作成 / 削除に時間がかかり、hotswap の対象外です。VPC 設定を入れるとフルデプロイになり、初回は 10 分を超えます（[amplify-gen2-cdk-patterns.md](amplify-gen2-cdk-patterns.md) ケース 2）。VPC なしの DemoMode なら 3〜5 分です。CDK bootstrap 未実施ならさらに加算されます。

| 項目 | 挙動 |
|------|------|
| Lambda Layer の変更反映 | **hotswap ではスキップされる**。`ampx sandbox delete` → 再デプロイ、またはパイプラインデプロイが必要 |

> **Lambda Layer の注意**: `shared/` を変更しても `ampx sandbox` は hotswap で Lambda のみを更新し、LayerVersion の内容変更をスキップします（hotswap 無効化フラグは存在しません）。確実に反映するには sandbox を作り直してください。

## スマートフォン実機で確認（2026-08-16）

iPhone (Safari) をトンネル経由で接続して確認しました。**閲覧・アップロード・ダウンロード・
フォルダー作成・削除**が通っています。手順とスクリーンショットは
[デモガイド](../../../docs/ja/portal-demo-guide.md) にあります。

| 項目 | 結果 |
|------|------|
| サインイン | 成功（HTTPS 必須。`http://<LAN-IP>` では `crypto.subtle` が使えずサインインできない） |
| ファイル一覧・フォルダー移動 | 成功 |
| フォルダー作成 | 成功 |
| アップロード | 成功。狭い画面ではアップロードパネルの列が右端で切れる |
| ダウンロード | 成功。Service Worker 経由でブラウザのダウンロードマネージャーに入る（Safari の保存先、既定は ファイル アプリ → ダウンロード） |
| 削除 | 成功 |
| 管理セクション（storage-admin） | 表示される。表のヘッダーがこの幅では 1 文字ずつ縦に折り返し、行も横に切れる |

> **実機で初めて分かったこと**: Storage Browser のダウンロードは Service Worker 経由で行われ、
> これが配置されていないとメモリ上の blob にフォールバックします。blob はブラウザにとって
> 「ファイルのダウンロード」ではないため、iOS のダウンロードマネージャーに何も残らず、
> 「完了したのに見つからない」状態になります。エミュレーションでは気づけませんでした。

## ブラウザのエミュレーションでのみ確認

以下はレイアウトの実測値で、Chrome の端末エミュレーション（390×844）で確認しています。
上の実機確認は操作の成否を、この区分は寸法を見ています。

| 項目 | 確認内容 |
|------|---------|
| スマートフォン幅のレイアウト | 全操作が画面内にあること、タップ領域が 44px 以上あることを実測。手順は [スマートフォン操作ガイド](../../../docs/ja/portal-mobile-guide.md) |
| 行メニュー（⋮） | 画面外に出ていた操作を修正。ボトムシート化して 5 個すべて到達可能（実測 400px → 画面内） |
| スナップショット一覧 | 画面外に出ていた「閲覧」「ロック」を修正（実測 表幅 585px → 358px、26 操作すべて画面内） |

## 未検証（今後）

- **Android 実機でのスマートフォン操作**（iPhone は 2026-08-16 に確認済み）
- 本番相当の負荷でのスループット共有（NFS/SMB/S3 AP の同時アクセス）
- マルチテナント（Cognito グループごとの S3 AP ルーティング）の実機確認
- 外部 IdP（SAML/OIDC）連携
- SnapMirror の DR フェイルオーバー一連（ブレーク → 昇格 → 再同期）
- AD 参加済み SVM に対する S3 AP データ操作（AD DC 到達性が前提）

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [管理者向けリソース管理 — デモガイド](../../../docs/ja/admin-resource-management-demo.md) | 26 シナリオの手順 |
| [PoC → 本番移行ガイド](../../../docs/ja/portal-poc-to-production.md) | DemoMode から本番接続への移行 |
| [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md) | VPC / シークレット / 管理 LIF の設定 |
| [AppSync 認可のトラブルシューティング](TROUBLESHOOTING-APPSYNC-AUTH.md) | グループ認可が失敗する場合 |
| [書き込み操作の検証計画](write-verification-plan.md) | 未実行の書き込み操作の前提・手順・影響・戻し方 |
