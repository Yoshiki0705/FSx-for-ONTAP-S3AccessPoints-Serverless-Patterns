# FlexGroup の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-flexgroup.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

FlexGroup は「大きな FlexVol」ではない。複数のコンスティチュエント（メンバー FlexVol）で
1 つの名前空間を作るため、**作成の配置・容量の偏り・使える機能**が FlexVol と違う。
FSx for ONTAP ではさらに、AWS が管理するアグリゲートの性質が絡む。

作成・削除の一般的な罠は [ボリュームライフサイクル](pitfalls-volume-lifecycle.md)、
FlexCache と SnapMirror は [FlexCache / SnapMirror](pitfalls-flexcache-snapmirror.md) にある。

## FlexGroup の自動配置は FSx for ONTAP では成功しない（2026-08-15 実測）

ONTAP のドキュメントは「FlexGroup はアグリゲートを指定しなくても自動配置される」と書いて
いる。FSx for ONTAP では**この経路は常に失敗する**。

```
No suitable storage can be found for the specified requirements.
Aggregates not matching FabricPool requirements: aggr1
```

FSx for ONTAP のアグリゲートは FabricPool アグリゲートで、自動選択の対象から除外される。
同じリクエストに `aggregates: [{"name": "aggr1"}]` を足すと成功する。つまり**両方の style で
アグリゲートを引いて渡す**のが正しい。

これは新しい発見ではなく、**同じ根本原因が別の API で既に分かっていた**。FlexCache の作成は
`use_tiered_aggregate: true` を送っており、その理由がテストのコメントに書かれている
（`pitfalls-flexcache-snapmirror` の「アグリゲート配置のフラグが既定 false」）。ボリューム
作成側にはその知識が来ていなかったため、ポータルからの FlexGroup 作成は一度も成功して
いなかった。**片方の API で見つけた「FSx では既定値が使えない」は、同種の API を一巡して
確認する。**

## FlexGroup の容量リバランスは、FlexGroup であれば使えるとは限らない（2026-08-15 実測）

`GET /storage/volumes/{uuid}` の `rebalancing` は明示要求フィールドで、要求しないと
オブジェクトごと返らない。要求しても**返らないボリュームがある**。

`fields=**`（56 キー）で確認した結果:

| ボリューム | style | `rebalancing` | 理由 |
|---|---|---|---|
| ONTAP S3 バケットの実体 | flexgroup | **返らない** | `is_object_store: true`。オブジェクトストアの backing volume では容量リバランス非対応（[NetApp KB](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_it_necessary_to_manually_balance_constituents_of_an_S3_bucket_hosting_flexgroup%3F)）|
| FlexCache のキャッシュ | flexgroup | **返らない** | キャッシュ側は常に FlexGroup だが追跡対象外 |
| 通常の FlexGroup | flexgroup | 返る | `state: not_running` |

`rebalancing.state` の `unknown` は「ONTAP が状態を判定できなかった」という別の意味を持つ
ので、**オブジェクトが無いことを `unknown` に丸めてはいけない**。丸めると「均衡している
ボリューム」に見えて、実行できない操作のボタンが出る。

判定に使えるフィールド: `is_object_store`、`granular_data`、`granular_data_mode`。

### 開始が受理される条件（2026-08-15 実測、リファレンス未記載）

```
30 分 <= max_runtime < （開始時刻から次回スナップショット取得までの残り時間）
```

- 下限を割ると `144182221`「must be 30 minutes or longer」
- 上限に触れると `13107433`。メッセージに次回スナップショットの実時刻が入る
- **ONTAP 既定の 6 時間、および `max_runtime` 省略のどちらも上限に触れて失敗する**
- 既定スナップショットポリシー（毎時 :05）では、開始できるのは**毎時 :05〜:35 の間だけ**
- 予約実行でも要求時に判定され、起点は予約時刻

ボリューム状態には**リファレンスのボリューム側一覧に無い値**が返る。`idle`（実行中・移動
対象なし）と `scheduled`（予約あり）。`idle` はリファレンス上コンスティチュエントの状態
として説明されている。状態名を列挙する実装は、この 2 つを取り逃す。

移動対象が無い実行は notice を出さず、`imbalance_percent` も `data_moved` も 0 のまま
`runtime` だけが増える。区別できるのは `rebalancing.engine`（明示要求）の
`scanner.files_scanned` と `scanner.files_skipped`（`too_small` / `in_snapshot` など）。

一巡の観測ログ: [FlexGroup 容量リバランスの実測記録](../../solutions/amplify-portal/docs/flexgroup-rebalance-verification.md)

通常の FlexGroup で実測した既定値（ドキュメントの記載と一致）:

| フィールド | 実測値 |
|---|---|
| `max_runtime` | `PT6H` |
| `min_file_size` | 104857600（100 MB）|
| `max_threshold` / `min_threshold` | 20 / 5 |
| `max_file_moves` | 25 |
| `exclude_snapshots` | true |
| `granular_data` | false（開始すると有効化され、**無効化できない**）|

