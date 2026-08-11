# 依存更新（Renovate）

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/dependency-updates.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## Dependency Updates

| Tool | File | Purpose |
|------|------|---------|
| Renovate | `renovate.json` | Automated dependency updates (GitHub Actions, `requirements*.txt`/`pyproject.toml`, Dockerfiles). Major bumps require Dependency Dashboard approval. |

Renovate keeps SHA-pinned Actions pinned (`helpers:pinGitHubActionDigests` + `pinDigests: true` on the `github-actions` packageRule), so it does not conflict with the zizmor/gitleaks/scorecard SHA-pinning policy above.

The [Renovate GitHub App](https://github.com/apps/renovate) **is installed and active** on this repository (account-level install with "All repositories" access, so no per-repo step is needed). It has been opening and merging dependency PRs since 2026-07. Confirm status with data rather than re-checking the app settings:

```bash
gh pr list --state all --author "app/renovate" --limit 5   # recent dependency PRs
gh issue list --state open | grep "Dependency Dashboard"    # the dashboard issue
```

Major-version bumps wait for a checkbox on the Dependency Dashboard issue, so a long "Pending Approval" list is normal operation, not a broken install.
## メジャー更新を承認する前に確認すること

Dependency Dashboard のチェックボックスを押すと Renovate が PR を作りますが、破壊的変更の
修正はこちらの仕事です。**自分でブランチを切り、同一 PR で破壊箇所も直す**方が制御しやすい。

### 上流の対応表を確認する（Renovate は見ていない）

Renovate は「そのパッケージの最新メジャー」を提案するだけで、**それを使う側のサポート範囲は
見ていません**。実例: `mariadb` 11 → 12 の提案。Nextcloud 34 の
[System requirements](https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html)
が挙げる MariaDB は 10.6 / 10.11 / 11.4 / 11.8 で、**12 は入っていません**。提案どおり上げると
サポート範囲外の組み合わせになります。`solutions/nextcloud-test/docker-compose.yml` は
`mariadb:11.8` に明示ピンし、理由をコメントに書いてあります。

ミドルウェアのメジャーを上げるときは、それを載せているアプリ側の対応表を先に読む。

### GitHub Actions のメジャーは Node ランタイムの期限で決まる

2026 年のメジャー更新はほぼすべて Node 20 → Node 24 への移行です。期限があります。

| 日付 | 何が起きるか |
|---|---|
| 2026-06-02 | ランナーの既定が Node 24 に切り替わる。Node 20 の Action は `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true` がある場合のみ動く |
| 2026-09-16 | GitHub ホストランナーから Node 20 が削除される。Node 20 の Action は opt-out フラグに関係なく動かなくなる |

出典: [gitleaks-action v3 リリースノート](https://github.com/gitleaks/gitleaks-action/releases/tag/v3.0.0)。
Node 24 の Action はランナー **v2.327.1 以上**を要求します（このリポジトリは
`ubuntu-latest` のみなので影響なし。self-hosted を足すときは要確認）。

ドキュメント内のワークフロー例（`docs/`、`solutions/**/docs/`）も更新対象です。読者がコピーする
`@v4` は 2026-09-16 以降動きません。

### 実際に確認した破壊的変更

| Action | 変更 | このリポジトリへの影響 |
|---|---|---|
| `actions/checkout` v7 | `pull_request_target` / `workflow_run` での fork PR チェックアウトをブロック | 影響なし（両トリガーを使っていない） |
| `actions/setup-node` v5 / v6 | `package.json` の `packageManager` から自動キャッシュ。v6 で npm のみに限定 | 影響なし（`cache: "npm"` を明示している） |
| `actions/setup-python` v7 | `pip-install` 入力を削除 | 影響なし（未使用） |
| `aws-actions/configure-aws-credentials` v5 | 不正な boolean 入力の扱いが変わる | 影響なし（boolean 入力なし） |
| `actions/upload-artifact` v7 | ESM 化 + `archive: false` の追加 | 影響なし |
| `gitleaks/gitleaks-action` v3 | 入力・出力・挙動の変更なし（Node 24 のみ） | 影響なし |

### SHA を張り替えたら、SHA とタグの対応を機械で照合する

コミットメッセージの `# vX.Y.Z` は人が書くので、SHA と一致している保証がありません。
張り替え後に照合します。

```bash
grep -rhoE "uses: [^/]+/[^@]+@[0-9a-f]{40} # v[0-9.]+" .github/workflows/* | sort -u |
while read -r _ spec _ ver; do
  repo=$(echo "$spec" | cut -d@ -f1 | cut -d/ -f1,2); sha=$(echo "$spec" | cut -d@ -f2)
  ok=$(gh api "repos/$repo/tags?per_page=100" --paginate \
        --jq ".[] | select(.commit.sha==\"$sha\") | .name" | grep -Fx "$ver")
  printf '%-46s %-10s %s\n' "$repo" "$ver" "${ok:+VERIFIED}${ok:-MISMATCH}"
done
```

`scripts/check_actions_pinning.py` が pin と `# vX.Y.Z` コメントの存在まで検査しますが、
**コメントの中身が SHA と合っているかは検査できません**（それには API アクセスが必要）。
上のループはメジャー更新のときだけ手で回す。
