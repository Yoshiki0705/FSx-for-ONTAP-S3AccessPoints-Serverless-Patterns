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
