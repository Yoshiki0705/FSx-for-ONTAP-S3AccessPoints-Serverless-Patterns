# FlexCache / SnapMirror / SVM ピアの罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-flexcache-snapmirror.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

FlexCache と SnapMirror は、どちらも「作成 API が 202 を返してから非同期ジョブで失敗する」
「アグリゲート配置のフラグが既定 false で FSx for ONTAP では必ず失敗する」「SVM ピアの
`applications` が用途ごとに個別」という同じ 3 つの構造を共有する。片方で踏んだ罠は、
もう片方でも名前を変えて再登場する。

| Pitfall | Solution |
|---------|----------|
| FlexCache 作成が「配置先なし」で失敗 | `use_tiered_aggregate: true` を送る（既定 false）|
| SnapMirror 宛先の自動作成が失敗 | `create_destination.tiering.supported: true` を送る（既定 false）|
| 作成できたのに転送履歴が空 | POST に `state: "snapmirrored"` を含める（含めないと `uninitialized`）|
| ピアが `peered` なのに SnapMirror が拒否される | `applications` に `snapmirror` を追加する（`state` だけを見ない）|
| ボリューム削除が成功を返すのに消えない | offline の PATCH と DELETE の**両方**のジョブを待つ |

## FlexCache: FSx for ONTAP では `use_tiered_aggregate` を明示しないと必ず失敗する（2026-08-14 実測）

`POST /api/storage/flexcache/flexcaches` は、アグリゲートを指定しない**自動プロビジョニング**で
呼ぶと `use_tiered_aggregate` が**既定 false** になる。これは「FabricPool が付いた
アグリゲートを FlexCache に使ってよいか」のフラグで、false のままだと配置が拒否される。

**FSx for ONTAP のアグリゲートは常に FabricPool が付いている**（キャパシティプール階層化が
その仕組み）。したがって既定のままでは 100% 失敗する。

```
Create FlexCache volume <name>.   failure
Complete: No suitable storage can be found for the specified requirements.
Aggregates not matching FabricPool requirements: aggr1 [12]
```

**この失敗は 202 では見えない。** POST はジョブを返して受理され、失敗はジョブの中で起きる。
レスポンスだけを見て成功を報告すると「作成しました」と表示されてボリュームは存在しない。
ジョブ（`/cluster/jobs/{uuid}`）を確認すること。

### 2 つの指定方法は排他

| 指定 | `use_tiered_aggregate` | `constituents_per_aggregate` |
|---|---|---|
| 自動プロビジョニング（`aggregates` なし） | **必要**（FSx では true） | 読まれない（単独指定は 66846871） |
| 明示配置（`aggregates` あり） | 使えない（66846915） | 有効。既定 4 |

FlexGroup のメンバーボリューム数（`constituents_per_aggregate`）を制御したいなら
`aggregates` も渡す必要がある。逆に `aggregates` を渡すなら `use_tiered_aggregate` は
外さないとエラーになる。FSx for ONTAP では利用者がアグリゲートを管理しないので、
自動プロビジョニング + `use_tiered_aggregate: true` が既定として妥当。

出典: [POST /storage/flexcache/flexcaches](https://docs.netapp.com/us-en/ontap-restapi-9161/post-storage-flexcache-flexcaches.html)
（ライセンス条件に合わせて要約）

### 同一 SVM 内の FlexCache は作れる

オリジンと同じ SVM に FlexCache を作る構成は動く（実測: `fsxsvm01:vol1` をオリジンに
`fsxsvm01:flexcache_eda_tokyo` を作成、online）。別クラスタを用意しなくても検証できる。

## SVM ピアの `applications` は用途ごとに個別（2026-08-14 実測）

SVM ピアは `applications` に許可する用途を持ち、**FlexCache 用のピアで SnapMirror は
できない**。ピアが `peered` でも、用途が入っていなければ拒否される。

```
localSvm=fsxsvm02  peerSvm=FSxN_OnPre  state=peered  applications=["flexcache"]
```

この状態で SnapMirror を張ろうとすると、**`SVM peer permission not found.`** という
メッセージで失敗する。文面は「ピアが存在しない」ように読めるので、クラスターピアや
新規 SVM ピア作成の方向に調査が向かう。実際に足りないのは `applications` の 1 要素だけで、
`PATCH /svm/peers/{uuid}` に `{"applications": ["flexcache", "snapmirror"]}` を送れば
解消する（ピアの削除・再作成は不要。相手クラスターでの再 accept も要らない）。

**`state` だけを見て「ピアリング済みだから使える」と判断しない**。`applications` に
目的の用途があるかまで確認する。

対して、`fsxsvm01` 側に**新規**の SVM ピアを作ろうとすると同じ文面で失敗し、こちらは
本当にピアが無い。SVM ピアは相手クラスター側での accept が必要なので、片側からは
完結しない。既存ピアの `applications` を足す方が到達可能である。

## SnapMirror 作成: `create_destination.tiering.supported` も既定 false（2026-08-14 実測）

`POST /snapmirror/relationships` に `create_destination.enabled: true` を渡すと ONTAP が
宛先ボリュームを作るので、`volume create -type DP` を先にやる必要がない。ただし
`create_destination.tiering.supported` が**既定 false** で、これは「FabricPool が付いた
アグリゲートに宛先を置いてよいか」のフラグである。FSx for ONTAP のアグリゲートは
すべて FabricPool 付きなので、既定のままでは置く場所が無く失敗する。
**FlexCache の `use_tiered_aggregate` と完全に同じ罠が、別の API の別の名前で再登場する。**

もう一点、`state: "snapmirrored"` を POST に含めると作成と初期化が同時に走る。含めないと
`uninitialized` のままで、転送履歴は空のままになる（「作成できたのに転送が無い」の原因）。

```json
{
  "source": {"path": "svm_onprem:smtest_src", "cluster": {"name": "FsxIdPeerCluster"}},
  "destination": {"path": "fsxsvm02:vol_dr_test"},
  "policy": {"name": "MirrorAllSnapshots"},
  "create_destination": {"enabled": true, "tiering": {"supported": true}},
  "state": "snapmirrored"
}
```

POST は**宛先クラスター**に対して発行する。ポータルが接続しているのは 1 クラスターなので、
「別ファイルシステムのボリュームを保護する」操作がこちら側だけで完結する一方、宛先が
別クラスターにある関係はこのポータルからは見えない。

宛先作成と初回転送はどちらも Lambda の実行時間より長いので、ジョブが「実行中」で返るのは
受理であって失敗ではない（`_wait_for_job(pending_ok=True)`）。

## ボリューム削除は offline と delete の 2 つのジョブを待つ（2026-08-14 実測）

`DELETE /storage/volumes/{uuid}` の前に `PATCH {"state": "offline"}` が必要だが、この
PATCH も 202 で返る。PATCH の直後に DELETE を投げると、まだ online なのでジョブの中で
拒否され、**ハンドラは 202 を見て成功を返す**。実測では SnapMirror の宛先だったボリュームで
`{"success": true}` が返り、20 秒後の一覧にまだ存在していた。

「成功レスポンスは成功の証拠ではない」がここでも当てはまる。フラグを足して再試行するのでは
なく、offline のジョブを待ってから DELETE し、DELETE のジョブも待つ。回帰テストは
「GET（ジョブ確認）が DELETE より前に出ていること」を順序で固定している。

## ポータルの一覧は書き込み直後に再取得しても古い（2026-08-14 実測）

ONTAP は変更が一覧に反映される前に書き込みを ack する。SnapMirror の関係を削除して
成功が返った直後の再取得に、削除した行がまだ含まれていた。作成側も同じで、`createSnapmirror`
の直後は `uninitialized` が返り、そのまま画面に残る（「作成が無言で失敗した」ように見える）。

対処は 2 つ。書き込み後は**即時 + 数秒後**の 2 回再取得する。加えて、遷移中の状態
（`uninitialized` / `transferring` / `finalizing` / `preparing`）が一覧に 1 つでもある間だけ
ポーリングする。落ち着いた関係を見張り続けるコストは払わない。

## FlexCache は読み取り専用ではない（UI 文言の事故）

ポータルの FlexCache パネルは「FlexCache は読み取りキャッシュなので、データ保護や容量管理の
機能はオリジンボリューム側で設定します」と説明していた。未対応機能の一覧に理由を添えたつもりの
一文だが、**読者には「キャッシュには書き込めない」と読める**。実際は書き込める。

| モード | 動作 | 要件 |
|--------|------|------|
| write-around（既定） | 書き込みをオリジンに転送し、オリジンが確定してから完了を返す | なし |
| write-back | キャッシュで確定して即座に完了を返し、オリジンへ非同期に反映 | キャッシュとオリジンの**両方**が ONTAP 9.15.1 以降 |

NetApp は**どちらのモードでもアクセスするデータは常に整合している**と明記している
（[write-back architecture](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html)）。
書き込み中のファイルはロックされ、オリジンとキャッシュが食い違うことはない。この整合性の担保が
FlexCache を単なるキャッシュと区別する要点なので、「読み取り専用」に読める文言は機能の価値を
そのまま消してしまう。

REST では `writeback.enabled`（`GET .../flexcaches?fields=writeback.enabled` で取得、
`PATCH /storage/flexcache/flexcaches/{uuid}` に `{"writeback": {"enabled": true}}` で変更）。
CLI の手順には「advanced privilege mode が必要」と書かれているが、**REST 経由では不要**
（9.18.1P3D1 で実測）。

**write-back が有効なキャッシュは削除できない。** 先に無効化する必要があり、無効化は
キャッシュにしかない書き込みをオリジンへ反映する。削除の失敗はジョブの中で起きるので、
DELETE のジョブを待たないと「成功したのに消えない」になる。

教訓として一般化できる部分: **制約の一覧に理由を添えるとき、その理由が製品の対応範囲そのものを
狭めて読めないか確認する。** 「A は B なので C ができない」と書くと、読者は B から C 以外の
制約も推論する。ここでは「読み取りキャッシュ」から「書き込み不可」が推論された。
