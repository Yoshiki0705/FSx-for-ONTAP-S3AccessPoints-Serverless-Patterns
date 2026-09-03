# 作業を main に載せるときの順序

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/` 側が読み込み条件だけを持ち、該当する作業をしているときにこの内容へ誘導する。
> `.kiro/` は公開しないため、知識の本体は常にこちら側に置く。

対象は「複数の変更が混ざった作業ツリーを PR に切り分けて main へ載せる」作業。何を検証するか
は [Verification Checklist](../../AGENTS.md#verification-checklist)、依存更新は
[dependency-updates](dependency-updates.md) にある。

## 共有ファイルによる PR の結合

このリポジトリには**内容が複数の変更にまたがるファイル**があり、ファイル単位では切り分けられない。

| ファイル | なぜ結合するか |
|---|---|
| `AGENTS.md` | テストファイル数の主張（`~4,900 Python tests across N files`）を持ち、テストを 1 つ足す変更すべてがこの行に触る |
| `scripts/tests/test_stale_claim_rules.py` | 上の主張を照合するフィクスチャが同じ数値をリテラルで持つ |
| ルート `Makefile` | `drift` のチェック一覧と、各機能の make ターゲットが同居する |

**実測 2026-09-03**: ランタイム検査の追加とデモ環境の追加を別 PR にしたところ、前者だけでは
`AGENTS.md` のテスト数が 286 のままで実体が 287 になり、テストが落ちた。後者だけでは
`Makefile` の `drift` が前者のスクリプトを呼ぶのに `validators.yml` にそれが無く、
「drift で走るが CI で走らないチェックがある」という別の検査に落ちた。

対処は 2 つ。**片方を他方の上に積む**（`git rebase <base-branch>`）か、**各コミットが自己整合
するように数値を段階的に更新する**（1 つ目の PR で 286→287、2 つ目で 287→289）。後者は
rebase 時に同じ行で衝突するが、衝突は 2 行なので解決は容易である。

避けるべきなのは「後で直す」。**各コミットは単体でゲートを通る状態にしておく。** そうでないと
squash マージ後に main が一時的に赤くなり、原因が分割の都合だったのか実際の欠陥だったのかを
後から区別できない。

## スタック PR の base を消す順序

`gh pr merge --squash --delete-branch` は base ブランチを消す。**そのブランチを base に
している PR は GitHub が自動でクローズする。**

**実測 2026-09-03**: `chore/lambda-runtime-agreement` を base にした PR を作り、base 側を
`--delete-branch` でマージしたところ、依存 PR が `CLOSED` になった。`gh pr edit --base main`
は「クローズされた PR の base は変更できない」と拒否するため、**PR を作り直すしかない**。

正しい順序は次のとおり。

```bash
# 1. 依存している PR の base を先に main へ付け替える
gh pr edit <dependent> --base main

# 2. そのうえで base 側をマージする
gh pr merge <base-pr> --squash --delete-branch

# 3. squash マージなので、依存ブランチは元の 2 コミットを持ったままになる。
#    squash 済みの分を除いて main の上に載せ直す
git rebase --onto origin/main <base-branch-tip-sha> <dependent-branch>
```

3 の `--onto` を使うのは、squash マージが base の複数コミットを 1 つに畳んでいるため、素の
`git rebase origin/main` では同じ内容を二重に適用しようとして衝突するからである。

作り直しになった場合、**本文は消える前に保存しておく**。

```bash
gh pr view <number> --json body -q .body > /tmp/body.md
```

## 未コミットの変更が自分のものだとは限らない

作業ツリーに前のセッションの変更が残っていることがある。**コミット前に、どの変更が誰のものかを
`git show HEAD:<path>` との差分で判定する。**

実測: `AGENTS.md` の作業ツリー版には 3 系統の変更が混ざっていた（前セッションの arm64 節の
書き換えとテスト数、ランタイム検査の追記、当セッションの追記）。ファイル単位の切り分けを
「自分の変更だから」で決めると、他人の未完成の変更を一緒に公開する。

## 公開後に誤りが見つかったとき

PR 本文とコミットメッセージは main に載った後も編集できるものとできないものがある。

- **コミットメッセージ**: 変更できない（履歴の書き換えになる）。訂正は後続のコミットで行う
- **PR 本文**: `gh pr edit <number> --body-file <file>` でマージ後も編集できる。誤った主張を
  残さないため、訂正はここに書く

実測 2026-09-03: マージ済み PR の本文に、実装を読み違えたセキュリティ上の主張を書いていた。
本文に訂正を追記し、ドキュメント側は通常のコミットで直した。
