# FlexGroup 容量リバランスの実測記録

🌐 **Language / 言語**: 日本語 | [English](flexgroup-rebalance-verification.en.md)

FSx for ONTAP の FlexGroup に対する容量リバランス（capacity rebalancing）を、REST API 経由で
一巡実行して観測した記録です。**ドキュメントに書かれていない制約が 2 つあり、その 2 つが
重なると開始できる時間帯が 1 時間のうち 30 分に限られる**という結論が中心です。

## 結論だけ先に

| 観測 | 内容 |
|---|---|
| 最大実行時間には下限がある | **30 分未満は拒否**（`144182221`）。API リファレンスに記載なし |
| 最大実行時間には上限もある | **次回スナップショット取得時刻までの残り時間より短い**必要がある（`13107433`）。同じく記載なし |
| 既定値では常に失敗する | ONTAP 既定の `max_runtime` は 6 時間。既定スナップショットポリシー（毎時 :05）のボリュームでは**必ず上限に触れる** |
| 開始できる時間帯 | 上記 2 つの帰結として、既定ポリシーでは**毎時 :05〜:35 の間だけ** |
| ボリューム状態に未記載の値がある | `idle`（実行中・移動対象なし）と `scheduled`（予約あり）。REST リファレンスのボリューム側一覧に無い |
| 不可逆性は実測で確認 | 開始で `granular_data` が `true` / `basic` になり、**停止しても戻らない** |
| 拒否された開始は副作用なし | 失敗した開始では `granular_data` は `false` のまま |

## 検証環境

| 項目 | 値 |
|---|---|
| リージョン | ap-northeast-1 |
| ONTAP バージョン | 9.17.1P6 |
| 対象ボリューム | `zz_fg_probe`（検証用に作成し、検証後に削除） |
| ボリューム構成 | FlexGroup 400 GiB / コンスティチュエント 4 個（各 100 GiB） |
| スナップショットポリシー | `default`（毎時 :05 に取得） |
| 実行日 | 2026-08-15 |
| 呼び出し経路 | ポータルの `resource-management` Lambda → ONTAP REST `PATCH /storage/volumes/{uuid}` |

> **注意**: 対象ボリュームは**ほぼ空**です。100 MB 以上のファイルが無いため、実際のファイル
> 移動は発生していません。「偏りが解消される過程」は本記録の対象外で、観測できたのは
> **API の受理条件・状態遷移・診断カウンタ・不可逆性**です。両者を混同しないでください。

## 1. 開始前の状態

```
state=not_running  granular=False/disabled  imbalance=0%  worst=0%  runtime=''
```

ボリューム作成直後で、`granular_data` は無効です。ONTAP がボリュームに保持している設定は
すべて既定値で、ドキュメントの記載と一致しました。

| フィールド | 実測値 |
|---|---|
| `max_runtime` | `PT6H` |
| `min_file_size` | 104857600（100 MB）|
| `max_threshold` / `min_threshold` | 20 / 5 |
| `max_file_moves` | 25 |
| `exclude_snapshots` | `true` |

## 2. 開始が拒否された 4 パターン

### 2-1. スナップショット取得予定との衝突（`13107433` / HTTP 409）

`maxRuntime=PT1H` を 15:59:47 に要求（次回スナップショットは 16:05:00）:

```
The next scheduled snapshot for volume "zz_fg_probe" in SVM "fsxsvm01" is scheduled for
Sat Aug 15 16:05:00 2026, in 0h5m12s. This is within the specified 1h0m0s maximum runtime
for the volume capacity rebalancing operation, which started at Sat Aug 15 15:59:48 2026.
To run the operation, either reduce the "-max-runtime" or disable the snapshot policy for
the volume.
```

**同じ拒否が `PT6H` でも、`maxRuntime` を省略した場合でも起きました**（省略時は ONTAP の
既定 6 時間が適用されるため）。つまり**ポータルが既定として提示していた値では一度も開始
できない**状態でした。この修正がこの検証の直接の成果です。

### 2-2. 境界の確認（A/B）

16:05 のスナップショット取得を待ってから、同じ条件で 2 つ試しました。

| 時刻 | `maxRuntime` | 次回スナップショットまで | 結果 |
|---|---|---|---|
| 16:06:12 | `PT1H`（60 分） | 58m47s | **拒否**（`13107433`）|
| 16:06:13 | `PT30M`（30 分） | 58m46s | **成功** |

判定は「`max_runtime` < 次回スナップショットまでの残り時間」です。60 分 > 58m47s で拒否、
30 分 < 58m46s で成功。1 秒差の 2 リクエストで挟んでいるので、時間経過ではなく
`max_runtime` の値が判定要因であることが確定します。

### 2-3. 下限（`144182221` / HTTP 400）

2-1 を回避するため `PT3M` を試すと:

```
The "-max-runtime" value specified must be 30 minutes or longer.
```

**下限 30 分**。2-1 の上限と組み合わせると、開始可能な条件は次のようになります。

```
30 分 <= max_runtime < （開始時刻から次回スナップショット取得までの残り時間）
```

既定ポリシー（毎時 :05）では右辺が 60 分から始まって減っていくため、**:05〜:35 の間しか
30 分の枠が取れません**。`5min` のような頻繁なスケジュールでは右辺が常に 30 分未満になり、
**ポリシーを外さない限り開始できません**。ONTAP のメッセージ自身が
「reduce the -max-runtime **or disable the snapshot policy**」と両方を挙げているのは
このためです。

### 2-4. 過去時刻の予約（`144182233`）

```
The specified rebalancing start time is not valid. The start time must be set to the
current time or a later time.
```

## 3. 実行中の挙動

`PT30M` で開始した直後からの観測（`/storage/volumes/{uuid}?fields=rebalancing` を約 10 秒間隔）:

```
16:06:15  開始要求 -> success
16:06:18  state=idle    granular=True/basic  runtime=PT3S    moved=0
16:06:30  state=idle                         runtime=PT15S   moved=0
16:07:22  state=idle                         runtime=PT1M7S  moved=0
16:08:26  state=idle                         runtime=PT2M11S moved=0
```

2 回目の実行では開始直後だけ `rebalancing` を観測し、その後 `idle` に落ち着きました。

```
16:17:37  state=rebalancing  runtime=PT6S
16:17:46  state=idle         runtime=PT15S
```

観測された点:

- **`granular_data` は開始と同時に `true` / `basic` になります。** 要求から数秒で反映されました。
- **`idle` はボリューム状態として返ります。** REST リファレンスは `idle` を
  *コンスティチュエントの*状態として説明しており、ボリューム側の値としては挙げていません。
  実際にはボリュームが `idle` を返すため、ボリューム側の一覧だけを実装すると
  **実行中のリバランスが「不明」と表示されます**（実際にそうなり、修正しました）。
- **移動対象が無い実行は、notice を一切出しません。** `notices` は空のまま、
  `imbalance_percent` も `data_moved` も 0 のまま、`runtime` だけが増えます。
  つまり「動いている」と「動くものが無い」は**状態だけでは区別できません**。
- 区別に使えるのは `rebalancing.engine` です（明示要求が必要）。

```json
{ "scanner": { "files_scanned": 0, "blocks_scanned": 0,
    "files_skipped": { "too_small": 0, "too_large": 0, "fast_truncate": 0,
      "in_snapshot": 0, "efficiency_blocks": 0, "efficiency_percent": 0,
      "incompatible": 0, "metadata": 0, "remote_cache": 0, "write_fenced": 0,
      "on_demand_destination": 0, "footprint_invalid": 0, "other": 0 } },
  "movement": { "file_moves_started": 0 } }
```

`files_skipped` の理由名は、ガイドが警告している 2 つの既定除外（`too_small` =
100 MB 未満、`in_snapshot` = スナップショットに含まれる）に直接対応します。
**「実行中なのに減らない」の答えはここにしかありません**。

### コンスティチュエントごとの使用量

`constituents.space` から各メンバーの実測値が取れます。

| コンスティチュエント | サイズ | 使用量 |
|---|---|---|
| `zz_fg_probe__0001` | 100 GiB | 537,300,992 B（512.4 MiB / 0.5%）|
| `zz_fg_probe__0002` | 100 GiB | 537,313,280 B |
| `zz_fg_probe__0003` | 100 GiB | 537,309,184 B |
| `zz_fg_probe__0004` | 100 GiB | 537,305,088 B |

**新規作成直後の FlexGroup は空ではありません。** 各コンスティチュエントがメタデータで
約 537 MB を使い、合計で約 2.1 GB を消費しています（`space.metadata` は各 56 MB、
`total_metadata_footprint` は各 60 MB）。各メンバーには `snapshot.used` も約 795 KB
ありました。

ボリューム全体の偏りは 0%（`imbalance_size` は 12,288 B）で、メンバー間の差は最大でも
約 12 KB です。均等に作られていることが数値で確認できます。

## 4. 実行中の二重開始

実行中（`idle`）に再度開始を要求すると、ONTAP が拒否します（`144182216` / HTTP 409）:

```
The volume capacity rebalancing configuration cannot be updated for volume "zz_fg_probe"
in SVM "fsxsvm01" because a volume capacity rebalancing operation is running on the
FlexGroup. Wait for the operation to complete or stop the running operation before
attempting to update the configuration.
```

**ポータル側のガードはこれを取り逃していました。** 実装が
`state in ("starting", "rebalancing")` を見ていたため、実測で返る `idle` と `scheduled` を
通してしまいます。ONTAP が止めるので害は無かったものの、条件を
「`not_running` / `unknown` 以外はすべて進行中」に反転しました。**状態名を列挙するガードは、
列挙しなかった名前を取り逃し続けます。**

## 5. 停止

```
16:10:02  停止要求 -> success
16:10:08  state=not_running  granular=True/basic  runtime=PT3M49S  stop=16:10:04
16:10:24  （同じ。runtime は PT3M49S で固定）
```

- `runtime` は停止時の値で固定され、`stop_time` が入ります。
- **`granular_data` は `true` / `basic` のまま**です。ここが不可逆性の実測確認です。
  ドキュメントは「有効化後は無効化できない。無効化するには有効化前のスナップショットから
  リストアする」と述べており、その通りの挙動でした。
- 何も動いていない状態で停止すると `Volume capacity rebalancing is not running.` で
  拒否されます。

## 6. 予約実行

```
16:10:39  startTime=16:18:39, maxRuntime=PT30M -> success (scheduled=true)
16:10:45  state=scheduled  start=2026-08-15T16:18:39+09:00
16:10:47  停止要求 -> success（予約の取り消し）
16:10:51  state=not_running  start=16:18:39（残る）  stop=16:10:47
```

- **`scheduled` もボリューム状態として返ります**（リファレンス未記載）。
- 取り消しは `state: stopping` の PATCH、つまり停止と同じ操作です。
- **取り消し後も `start_time` に取り消した予定時刻が残ります。** `stop_time` が併記される
  ため区別は付きますが、`start_time` を無条件に表示すると**実行されない予定を告知する**
  ことになります（UI では `scheduled` のときだけ表示するようにしました）。
- 予約時の衝突判定は**要求時点で行われ、判定の起点は予約時刻**です。16:50 開始・`PT30M` を
  16:11 に要求すると `in 0h15m0s`（16:50 → 17:05）と `0h30m0s` を比較して拒否されました。
  予約が黙って実行されない、という事態は起きません。

## 7. この検証で UI と実装に反映したこと

| 反映内容 | 根拠 |
|---|---|
| 最大実行時間の選択肢を 30 分から始める | 2-1 / 2-3。6 時間を先頭に置いていたため、既定ポリシーのボリュームでは押すたびに失敗していた |
| 2 つの制約と「毎時 :05〜:35」をガイドに明記 | 2-1 / 2-3。どちらも API リファレンスに無い |
| `idle` / `scheduled` の表示を追加 | 3 / 6。実行中が「不明」と出ていた |
| 二重開始のガードを反転 | 4。状態名の列挙をやめ、`not_running` / `unknown` 以外を進行中として扱う |
| コンスティチュエント別の使用量を表示 | 3。偏りは要約された percentage ではなくこの一覧が実体 |
| スキャナのカウンタと除外理由を表示 | 3。「実行中なのに動かない」に答えられるのはこれだけ |
| `start_time` は予約中のみ表示 | 6。取り消し後も残るため |
| 経過時間を時計表記に | 3。ONTAP は `PT1M32S` で返し、そのまま表示していた |
| ONTAP のメッセージは加工せず透過 | 2-1。次回スナップショットの実時刻が入っており、操作者が必要とする情報そのもの |

## 8. 未検証のまま残ること

- **実際に偏りが解消される過程**。100 MB 以上のファイルを偏らせて配置する必要があり、この
  ボリュームには用意できませんでした。`files_scanned` / `file_moves_started` /
  `data_moved` が動く様子、および `rebalancing_source` / `rebalancing_dest` の
  コンスティチュエント状態は観測していません。
- **`max_runtime` 到達時の挙動**。30 分の実行を完走させていません（3 分程度で停止）。
- **SnapMirror 転送との競合**（ドキュメント記載の 24 分再試行）。
- **重複排除されたファイルの移動で総使用量が増える現象**。
- **スナップショットポリシーを外した状態での長時間実行**。

## 参考

- [Rebalance FlexGroup volumes by moving files](https://docs.netapp.com/us-en/ontap/flexgroup/manage-flexgroup-rebalance-task.html)
- [Balance FlexGroup volumes by redistributing file data](https://docs.netapp.com/us-en/ontap/flexgroup/enable-adv-capacity-flexgroup-task.html)（有効化後は無効化できない旨）
- [Update volume attributes（`rebalancing` の全フィールド）](https://docs.netapp.com/us-en/ontap-restapi/ontap/patch-storage-volumes-.html)
- [Is it necessary to manually balance constituents of an S3 bucket hosting flexgroup?](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_it_necessary_to_manually_balance_constituents_of_an_S3_bucket_hosting_flexgroup%3F)
- 関連する罠のまとめ: [FlexGroup の罠](../../../docs/agent/pitfalls-flexgroup.md)
