# ボリュームの作成と削除の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-volume-lifecycle.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

FSx for ONTAP のボリュームは、作成も削除も「AWS が管理している部分」に触れるため、
ONTAP の素の API がそのまま使える形になっていない。どちらも 2 段階以上を要求し、
1 段目だけでは 400 で止まる。

| Pitfall | Solution |
|---------|----------|
| 作成が 787140 で失敗 | `style` を送る（`flexvol` / `flexgroup`）|
| **クローン**作成が 787140 で失敗 | `clone.is_flexclone: true` を送る。これが無いと ONTAP は通常のボリューム作成と読む。**アグリゲートを足して 787140 を消すと成功が返るが、できるのは 20 MB の普通のボリュームでクローン関係は無い**（2026-08-15 実測） |
| `style: flexvol` でも 918242 で失敗 | アグリゲートを 1 つ指定する。名前は `GET /storage/aggregates` で引く |
| `style: flexgroup` が「No suitable storage can be found」で失敗 | **FlexGroup でもアグリゲートを指定する**。理由は [FlexGroup の罠](pitfalls-flexgroup.md) |
| FlexGroup 作成が「Size "200GB" is too small」で失敗 | 既定の 4 コンスティチュエント構成では合計 400 GB 以上にする。同上 |
| 削除の offline が 524546 で失敗 | 先に unmount する（`{"nas": {"path": ""}}`）|
| ローカルユーザーの有効化に `enabled` を送ると 262179 | `account_disabled` を使う（意味は反転）|

## クローンを削除した親は、しばらく削除できない（2026-08-15 実測）

クローンを削除してから親を削除しようとすると、ONTAP は次で止まる。

```
Failed to delete volume "X" in SVM "Y" because it has one or more clones.
Only the cluster administrator can delete the clones associated with this volume.
```

このとき **クローンはもう API から見えない**（`GET /storage/volumes/{uuid}` は
`entry doesn't exist`、`clone.is_flexclone=true` の一覧にも出ない）。それでも親は
「クローンがある」と言う。

観測した事実だけを並べると:

- 親に残る `clone_<name>.<timestamp>` スナップショットの削除ジョブが 10 秒で終わらず、
  30 秒後もスナップショットは残っている
- 親の削除は 3 回試して 3 回同じエラー
- 削除の 2 段目（offline）は成功しているので、**失敗した削除は親を offline のまま残す**

**原因**: ONTAP のボリューム recovery queue。RW / DP ボリュームの削除要求は「partially
deleted」状態にして**既定 12 時間**キューに保持する。キューにある間もボリュームは WAFL の
テーブル上に存在し、名前・ID の衝突判定に参加し、**アグリゲートの容量も消費し続ける**。
削除済みクローンがキューにある限り、親から見ればクローンは存在する。

出典: [How to use the Volume Recovery Queue](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_to_use_the_Volume_Recovery_Queue)。

### キューは REST から読めて、purge も `fsxadmin` で通る（2026-08-15 実測）

**この項の以前の記述は誤りだった。**「`purge` は diag 権限が必要で FSx の `fsxadmin` では
到達できない。つまり待つしかない」と書いていたが、実際には REST の private CLI 経由で
`fsxadmin` のまま実行できる。12 時間待つ必要はない。

```
GET  /api/private/cli/volume/recovery-queue
POST /api/private/cli/volume/recovery-queue/purge   body: {"vserver": "...", "volume": "..."}
```

GET は `vserver` と `volume` だけを返す。`fields=*` は拒否され、`deletion-time` /
`deletion-request-time` / `size` はいずれも無効なフィールド名なので、削除時刻は読めない。
コレクションへの `DELETE` は 405（CLI の動詞が `purge` なので存在しない）。purge は 202 と
`[Job N] Job is queued: Delete <name>.` を返し、20 秒ほどでキューから消える。

**キュー上の名前は元のボリューム名ではない。** サフィックスが付く（`zz_recheck_clone` →
`zz_recheck_clone_1106`）。元の名前で照合すると一致しないので、一覧を取って前方一致で探す。

ブロックしていたクローンを purge した直後に親の削除が成功した。順序は「クローンを purge →
親を削除」で、キューにあるクローンの基点スナップショットは親から削除できない（削除ジョブが
完了しない）ため、スナップショットを先に消す経路は無い。

> purge は取り消せない。キューはそもそも誤削除に対する猶予期間なので、消してよいのは
> 自分が削除したと分かっているボリュームだけ。

### 回避策: クローンを削除する前に分割する（実測で A/B 確認）

同一環境・同一手順で、分割の有無だけを変えて比較した。

| 手順 | 親の削除 |
|------|---------|
| クローン作成 → **クローンを削除** → 親を削除 | **失敗**（`has one or more clones`）。15 分後・7 分後の再試行も同じ |
| クローン作成 → **分割** → 分割後のボリュームを削除 → 親を削除 | **成功**（クローン削除の数秒後に完了） |

分割するとクローンは親への依存を失うため、その後の削除は recovery queue に「クローン」を
残さない。親を削除する予定があるなら、**クローンは分割してから削除する**。

実務上の意味:

- 分割せずにクローンを削除したら、**親はその日のうちには消せない**前提で計画する
- 失敗した削除で offline になった親は、`bringVolumeOnline` で戻す（この理由で実装した）
- キューにあるボリュームはアグリゲート容量を消費し続けるので、容量計算でも無視できない

## FlexClone の作成と分割（2026-08-15 実測）

クローンは `POST /storage/volumes` に相乗りしているため、ボリューム作成と同じ入口の罠を踏む。

```
clone.parent_volume だけ                  → 400 / 787140（ボリューム作成と読まれる）
+ aggregates                              → 201。ただし 20 MB の普通のボリューム。
                                             clone ブロックは無視され、一覧にも出ない
+ clone.is_flexclone: true（aggregates なし） → 親のサイズを継いだクローンができる
```

`is_flexclone` を送らないまま 787140 を「置き場所の指定不足」と読んでアグリゲートを足すのが
最も危険な直し方で、**成功レスポンスと使えないボリュームが同時に手に入る**。

分割（`clone.split_initiated`）については 2 点:

- 9.4 以降は容量効率を維持するため、**分割で容量が倍になることはない**。20 GiB のクローンが
  分割後 348 KB だった。「親と同じ容量を消費する」は 9.4 より前の説明
- 分割が完了すると、そのボリュームは `clone.is_flexclone=true` の一覧から消える。進捗
  （`split_complete_percent`）は実行中しか観測できない
- 親側に作られたベーススナップショット `clone_<name>.<timestamp>` は分割後も残る。削除は利用者側

## FSx for ONTAP のボリューム作成は場所を 2 段階で要求する（2026-08-14 実測）

`POST /storage/volumes` は、置き場所の指定を 1 つではなく 2 つ要求する。片方だけでは通らない。

```
style も aggregates も無し   → 400 / 787140
  One of "aggregates.uuid", "aggregates.name", or "style" must be provided.

style: flexvol だけ          → 400 / 918242
  When creating a FlexVol volume, one aggregate must be specified with either
  "aggregates.name" or "aggregates.uuid".

style: flexgroup             → 通る（ONTAP が自動で配置する）
```

FSx for ONTAP ではアグリゲートを AWS が管理するので、利用者はその名前を知らない。
**`GET /storage/aggregates` で引いて最初の 1 つを使う**のが FSx コンソールと同じ振る舞いになる。
ポータルの createVolume はこの 2 段目に到達できておらず、FSx 上で一度も成功していなかった。

## マウント済みボリュームは offline にできない（2026-08-14 実測）

削除は unmount → offline → delete の 3 段階。ONTAP は**マウント済みのボリュームを offline に
してくれないし、代わりに unmount もしてくれない**。

```
PATCH {"state": "offline"} → 400 / 524546
  Volume "..." on SVM "..." must be unmounted before being taken offline or restricted.
```

unmount は `PATCH /storage/volumes/{uuid}` に `{"nas": {"path": ""}}`。ジャンクションパスの
有無を `fields=nas.path` で見て、付いているときだけ送る。

FlexCache も同じで、削除は FlexCache のエンドポイントだが内部でボリュームを offline にするため
同じ 524546 で止まる。**FlexCache の UUID はボリュームの UUID と同じ**なので、
`/storage/volumes/{uuid}` にそのまま使える。

この 2 つは「DP ボリュームだけ削除できていた」という形で隠れていた。SnapMirror の宛先は
ジャンクションパスを持たないので unmount が要らず、そこだけ動いていた。

## ローカルユーザーの有効・無効は `account_disabled`（2026-08-14 実測）

`PATCH /protocols/cifs/local-users/{svm.uuid}/{sid}` に `enabled` を送ると
**400 / 262179 `Unexpected argument "enabled"`**。正しくは `account_disabled`（意味が反転する）。

一覧側（`fields=...,account_disabled,...`）が既に正しいフィールドを読んでいたので、
**同じファイルの隣を見れば分かった**。作成の body の形から類推したのが誤り。
API のフィールド名は、同じリソースを読んでいる既存コードが最も近い出典になる。
## クォータは書くフィールドと読むフィールドが違う（2026-08-14 実測）

ボリューム単位のクォータ適用は `PATCH /storage/volumes/{uuid}` に `{"quota": {"enabled": bool}}`。
ところが**同じ `quota.enabled` を読み返してはいけない**。

```
enable 後の GET /storage/volumes/{uuid}?fields=quota
  → {"quota": {"state": "on", "enabled": false}}
```

`enabled` は「最後に出した要求」、`state` は「ボリュームが実際にしていること」。
`enabled` を一覧やレスポンスに載せると、適用中のボリュームについて逆のことを言う。
`state` には `on` / `off` / `initializing` / `mixed` があり、`initializing` は
ONTAP がボリュームを走査している最中（上限はまだ効いていない）で、`on` とは別の答えである。

ハンドラは PATCH の後に `fields=quota.state` を読み直して返す。要求をそのまま返すと、
呼び出し側に同じ罠を渡すことになる。

**ルールが 1 件も無いボリュームでは開始できない**:
`No valid quota rules found in quota policy default for volume <vol> in SVM <svm>.`
ルールの作成が先で、適用はその後。

## name-mapping の削除は繰り上げないが移動は繰り上げる（2026-08-14 実測）

`PATCH /name-services/name-mappings/{svm.uuid}/{direction}/{index}` に `{"new_index": N}`。
ONTAP は入れ替えではなく**間のルールを renumber する**。

```
移動前: win_unix[1]=PROBE1, win_unix[2]=PROBE2
[2] を new_index=1 へ → win_unix[1]=PROBE2, win_unix[2]=PROBE1
```

一方 DELETE は繰り上げない（`[1]` を消しても `[2]` は `[2]` のまま）。
「index は連番」と仮定したコードは、削除の後で穴の空いた並びを見る。

同じ index への移動は ONTAP も拒否するが、返る理由がどのフィールドの話か分からないので
ハンドラ側で先に弾く。

## FlexGroup のサイズ変更はジョブが 10 秒で終わらない（2026-08-14 実測）

`PATCH /storage/volumes/{uuid}` の `size` はジョブを返す。FlexGroup（FlexCache は必ず
FlexGroup）では**拡大・縮小のどちらも 10 秒を超えて継続する**。にもかかわらず新しいサイズは
すぐ読めるようになる。

厳密に待つと、成功した作業を「まだ running」として**失敗で報告する**。これは
「202 を成功として報告する」の裏返しで、どちらも実際と逆のことを言う。`_await_job` の
`pending_ok=True` がこの区別のために用意されている: 待ち時間内に**失敗したジョブは失敗**、
まだ走っているだけのものは受理として返す。

呼び出し側には `pending` を渡す。パネルが直後に一覧を取り直すと古いサイズが見えるため、
「受理した」と「反映は遅れる」を言い分ける材料が必要になる。

**作成の下限は縮小には効かない**。作成が「50 GB 未満は不可」で止まるファイルシステムで、
既存の 100 GiB キャッシュは 20 GiB へ縮小できた。既存リソースに対して「作成できない値なら
拒否されるはず」を前提に試すと、拒否を期待した操作が通る。他人のリソースで確かめる前に、
拒否の根拠がどちらの操作に紐づくかを確認する（この件では実際に縮小してしまい、戻した）。
