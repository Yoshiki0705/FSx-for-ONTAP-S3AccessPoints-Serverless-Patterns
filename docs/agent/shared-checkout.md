# 作業ツリーは自分専用ではない

このクローンで別のエージェントが同時に作業している前提で操作する。強制は
`scripts/guard_shared_checkout.py`（PreToolUse フック）にある。

## 何が起きたか

一方のセッションがブランチを作り、3 ファイルを stage 済みの状態で作業していた。他方が共有
チェックアウトを整理する意図で、HEAD がそのブランチにある状態で次を実行した。

```bash
git switch main -f
git reset --hard origin/main
```

`reset --hard` は追跡ファイルを戻し、追跡外の新規ファイルは残す。結果、3 ファイルのうち
**新規 1 件だけが生き残り**、HEAD も main へ移っていたため、そのファイルは PR ゲートを 1 つも
通らずに **main へ直接コミット**された。ブランチへ出す意図だったものが main に入った。

## 「失われた作業はない」という誤った報告

実行した側は直後にこう報告した — reflog を見た、ブランチは `git log main..<branch>` が 0 件
だったので空ブランチであり、失われた作業はない。

**コミットが 0 件のブランチにも index はある。** 検証すべきだったのは次の 2 つで、どちらも
見ていなかった。

```bash
git status --porcelain     # ステージ済みと未ステージの一覧
git diff --cached          # ステージ済みの内容
```

間違ったものを検証して安全だと報告した。消えた編集は `git fsck --dangling` でも回収できなかった
（残っていたのは追跡版より古い blob のみ）。**破壊的操作に事後検証は成立しない。**

## 規則

- **セッションごとに worktree を切る。** これが最小の対策で、このリポジトリには実績がある。

  ```bash
  git worktree add /tmp/wt-<name> -b <branch>
  ```

  共有チェックアウトでは `git switch` も `git reset` も出さない。

- **`git add -A` / `git add .` / `git add --all` / `git commit -a` を使わない。**
  ファイル名を列挙する。他セッションの編集を自分のコミットに巻き込む経路がこれ。

- **コミット前に意図したブランチにいることを確認する。**

  ```bash
  git rev-parse --abbrev-ref HEAD
  ```

  `main` には直接コミットしない。

- **ステージした内容とコミットされた内容の一致は、コミット時点で確認する。**
  上の事故は、コミット後に `git show --stat` を見て 1 ファイルだと分かった。その時点で
  もう手遅れである。

## ガードの挙動

`.kiro/hooks/shared-checkout-guard.json` から PreToolUse で起動する。`.kiro/` は git 管理外
なので、判定するコード自身は `scripts/` に置いて追跡している（フックだけを持つ環境では
ガードが存在しないことになるため）。

| コマンド | 判定 |
|---|---|
| `git add -A` / `git add .` / `git add --all` / `git commit -a` | **block**。scope 指定の stage |
| `git commit`（HEAD が `main` / `master`） | **block**。PR ゲートを通らない経路 |
| `git reset` / `restore` / `checkout --` / `switch` / `checkout <branch>` / `stash` / `clean -f` / `branch -f` / `branch -D`（作業ツリーが汚れているとき） | **ask**。失われる対象をファイル名で列挙する |
| 同じコマンド（作業ツリーが clean のとき） | 通す。失うものが無い |
| `git commit`（ブランチ上） | 通す。ただし**ステージ済みファイル名を毎回出力する** |
| `git stash list` / `git branch`（読み取りのみ）/ `git clean -n` | 通す |

`git status` に答えられないとき（リポジトリ外など）は **ask** にしている。答えの出ない問いは
clean ではない — 空の結果を「対象なし」と読む形は、姉妹リポジトリでガードが無言で全マージを
通していた原因そのものである。

`git commit` を ask にしていないのは、毎回の確認は押し流されるようになるからである。要件は
「ステージ内容がコミット前に見えていること」なので、プロンプトではなく出力にしている。

## 検証

```bash
python3 scripts/guard_shared_checkout.py --selftest
python3 -m pytest scripts/tests/test_guard_shared_checkout.py -q
```

テストは**実際のリポジトリを一時ディレクトリに作って**判定させている。判定が `git status` に
依存するため、コマンド文字列だけを見るテストは、別のツリーを読んでいるガードでも通る。
