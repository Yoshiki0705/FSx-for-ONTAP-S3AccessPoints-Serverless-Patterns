# ARP/AI と EMS の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/` 側が読み込み条件だけを持ち、該当する作業をしているときにこの内容へ
> 誘導する。`.kiro/` は公開しないため、知識の本体は常にこちら側に置く。

ランサムウェア保護（ARP/AI）とイベント通知（EMS）は、どちらも「要求した状態と実際の状態が
違う」「ドキュメントの例と実際に受け付ける形が違う」という形で裏切ってくる。

| Pitfall | Solution |
|---------|----------|
| `dry_run` を要求すると `enabled` になる | ARP/AI には学習期間が無い。**要求ではなく読み直した状態を返す** |
| 無効化が `disable_in_progress` のまま数分続く | 遷移中は「まだ要求した状態ではない」として扱う。`disabled` と同じ表示にしない |
| EMS の `fields=severity` が 262197 で拒否 | `message.severity` を使う |
| EMS の `severity=` フィルタが「Unexpected argument」 | フィルタも `message.severity=` |

## ARP/AI では `dry_run` を要求しても `enabled` になる（2026-08-15 実測）

`PATCH /storage/volumes/{uuid}` に `{"anti_ransomware": {"state": "dry_run"}}` を送ると、
**200 が返り、状態は `enabled` になる**。エラーも警告も返らない。

```
要求: dry_run
GET /storage/volumes/{uuid}?fields=anti_ransomware.state
  → {"state": "enabled"}
```

理由は ARP/AI（ONTAP 9.16.1 以降）が学習済みモデルを持つことで、入るべき学習期間が存在しない。
古典的な ARP は `disabled → dry_run（30 日の学習）→ enabled` という遷移を要求するので、
**同じ API・同じ値がバージョンによって別の意味になる**。

そのため**要求をそのまま応答に載せてはいけない**。`{"newState": "dry_run"}` を返すと、
実際には能動的に保護している（疑い検知でスナップショットを自動作成する）ボリュームについて
「学習中」と報告することになる。ハンドラは PATCH の後に読み直し、
`state` / `requested` / `differs` を返す。UI は差異があればその旨を添える。

「学習モードだから安全」を前提に検証計画を立てると、この 1 点で前提が崩れる。**dry_run は
この環境では選べない**ので、ARP を触る検証は「有効化してよいか」の判断から始める。

## 無効化は `disable_in_progress` のまま数分続く（2026-08-15 実測）

`disabled` を要求すると状態は即座に `disable_in_progress` になり、**20 GiB の空ボリュームで
10 分以上そのまま**だった。ONTAP は学習済みの状態を破棄する必要があるため、無効化は
フラグの反転ではない。

`disable_in_progress` は列挙に含まれていない値として扱われがちで、UI の `switch` の
`default` に落ちる。落ちた先が「無効」だと、**まだ有効なボリュームを無効と表示する**。
遷移中は第 3 の状態として扱う（`_in_progress` サフィックスで判定する。ONTAP のトークンは
動詞から作られるので `disabled_in_progress` ではなく `disable_in_progress`）。

## EMS は severity をトップレベルに持たない（2026-08-15 実測）

`GET /support/ems/events` で severity を要求すると、フィールドでもフィルタでも拒否される。

```
&fields=time,severity,...    → 400 / 262197
  The value "severity" is invalid for field "fields"
&severity=alert,error        → 400 / 262197
  Unexpected argument "severity"
```

正しくは**両方 `message.severity`**。severity はメッセージの属性である。

```
&fields=index,time,message.name,message.severity,log_message,node.name
&message.severity=alert,error,emergency
```

表示する本文は `log_message`（レンダリング済みの 1 行）。`message.text` はこのエンドポイントの
レコードには無い。

> NetApp の自動化ワークフローのドキュメントには `severity` を裸で書いた例があるが、
> 9.18.1P3D1 では通らない。**ドキュメントの例が現行バージョンで通るとは限らない。**

この 2 つの誤りにより `getEmsEvents` は**呼び出すたびに必ず失敗していた**。気付かれなかったのは
「型の一致だけ確認済み」の分類のまま実機で一度も実行されていなかったからで、
検証区分を正直に持つことが、この種の欠陥を見つける唯一の入口になる。
