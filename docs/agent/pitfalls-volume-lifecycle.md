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
