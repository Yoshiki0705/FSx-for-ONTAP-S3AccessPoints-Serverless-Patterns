# 長時間自律運用の規律（このリポジトリ固有の接続）

土台はグローバル steering にある（`ai-agent-workflow` の Parallel-by-default 節・
Auditor Sub-Agent 節、`benchmark-and-evidence-standards`）。それらは全 Kiro セッションに
効くので、ここでは**複製しない**。このファイルが持つのは、このリポジトリに固有の接続
（判断記録をどこに置くか、tier 語彙を既存ゲートのどの語に揃えるか、固有の繰り返しタスク型）
だけである。

## 判断記録の置き場所

多段タスク（新パターン追加 / 検証 / IaC 変更）では、実装の記述とは別に 3 節
（`## Decisions` / `## Rejected alternatives` / `## Assumptions`）をタスクごとの記録に残す。
3 節を別ファイルに切り出さず、そのタスクの 1 つの記録に収める。同じ役割の入れ物を乱立させない。

- 置き場所は `.agents/tasks/<task>/`（**gitignore 済み**）。既存の `.agents/tasks/` 慣習に従う。
- 既存ファイル（`report.md` / `plan.md` 等）があれば新名を増やさずそこに 3 節を追記する。
  無ければ `impl-note.md` を 1 つ作る。
- 判断記録は却下案・未検証前提・根拠 tier を含む process metadata なので、**公開しない側に置く**
  のが既定（グローバルの output-standards が review provenance を非公開へ回すのと整合）。

### Decisions 根拠欄の tier 語彙

判断記録の Decisions は「自分が下した設計判断が何に立脚するか」の内部メモで、**ゲート対象外**。
語彙は `verified` / `documented` / `hypothesis` の 3 語に揃える（`open` は根拠がない状態なので
判断の根拠には立たない）。語は `docs/agent/evidence-ledger.json` の tier と同じだが、**Decisions の
tier 注記は ledger への登録を要求しない**。

| 対象 | 語彙 | ゲート |
|---|---|---|
<!-- allow:not-a-claim: 不能主張の文型を例として引用し、どちらのゲートに乗るかを説明している行 -->
| ベンダー能力の主張（「AWS は〜できない」） | ledger の 4 語（documented / verified / hypothesis / open） | `check_evidence_claims.py` が強制。追跡対象文書で根拠なしは `exit 2` |
| 自分の設計判断の根拠（Decisions） | 上記のうち 3 語（documented / verified / hypothesis） | なし（内部メモ） |

混同しない。ベンダー能力の主張を追跡対象文書に書くなら、Decisions とは別に ledger へ `[E-nnn]` を
登録する（手順は [evidence-discipline](evidence-discipline.md)）。

## 監査役を呼ぶ合図

次のいずれかに気づいたら、続行前に `semantic_reviewer`（判断の見直し）か `context-gatherer`
（前提が実装と合うかの確認）を、判断記録と変更差分を渡して呼ぶ。**自動 hook は作らない。**

- 同一アプローチが 2 回失敗した
- 同じファイルを 3 回以上編集し直している
- 多段タスクで同じエラーメッセージが再発している

監査役への指示は「補強」ではなく「疑う」方向で: 判断記録のうち根拠が推測のものはどれか、
却下した代替で今なら復活すべきものはあるか、外れたら作業が無駄になる未検証の前提はどれか。

このリポジトリは evidence-ledger + `check_evidence_claims.py` が既に「未検証前提を声に出して
失敗させる」役を持つ。監査役はそれと別レイヤで、判断記録そのものを疑うために呼ぶ。公開物
コミット直前のレビューは persona review board（グローバル `sa-persona-review-board`）の担当なので、
監査役とは分ける。

## ばらつきを測ってから効果を主張する

性能・スループット・レイテンシ・コストの数値で効果を主張する前に、変更していない構成の
ラン間ばらつきを先に測る。変更の差がばらつきの範囲内ならノイズなので、そう書くか、ばらつきを
超えるまで反復数を増やす。1 回ずつの「A は B より速い」も同じ扱い。手順の土台は
`benchmark-and-evidence-standards`。数値を書くときの必須メタデータ（測定日 / region / 構成 /
object size / 並列度 / throughput capacity）もそちら。

## このリポジトリ固有の繰り返しタスク型

2 回目の同種の失敗は「チェックリストに項目が足りない」兆候として扱い、該当 playbook に 1 項目
ずつ足す。現時点の該当 playbook:

| タスク型 | チェックリストの所在 |
|---|---|
| 新パターンの追加・公開判定 | [new-pattern](new-pattern.md) |
| 検証ランの実施（ポータル性能等） | 変更前構成のばらつきを先に測る（上記）。tier は 3 語 |
| ベンダー能力主張を書く | [evidence-discipline](evidence-discipline.md) + ledger 登録 |
| AGENTS.md に索引行を足す | 足す前に `python3 scripts/check_agent_context_budget.py` をローカルで回す（予算 28,000 B の直前で、1 行で超える） |
