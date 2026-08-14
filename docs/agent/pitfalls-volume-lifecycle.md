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
| `style: flexvol` でも 918242 で失敗 | アグリゲートを 1 つ指定する。名前は `GET /storage/aggregates` で引く |
| 削除の offline が 524546 で失敗 | 先に unmount する（`{"nas": {"path": ""}}`）|
| ローカルユーザーの有効化に `enabled` を送ると 262179 | `account_disabled` を使う（意味は反転）|

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
