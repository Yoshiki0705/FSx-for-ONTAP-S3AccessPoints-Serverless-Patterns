# PR ベース使い捨て環境の設計

> CDK Conference Japan 2026 セッション「CDKでPRごとに使い捨て環境立てたら便利すぎました」(友岡) の知見を反映。

## 概要

PR ごとに独立した Amplify Gen2 サンドボックスを自動作成し、reviewer がポータルの動作を実際に触って確認できる仕組み。マージまたは PR クローズ時に自動削除される。

## アーキテクチャ

```
PR open/sync
    │
    ▼
GitHub Actions (pr-preview.yml)
    │
    ├── npx ampx sandbox --identifier pr-${PR_NUMBER} --once
    │     ├── Cognito User Pool (pr-123-fsxn-portal)
    │     ├── AppSync API (pr-123-fsxn-portal)
    │     ├── Lambda x13 (pr-123-*)
    │     └── DynamoDB tables (pr-123-*)
    │
    ├── npm run build (Vite → dist/)
    │
    └── Deploy dist/ to Amplify Hosting preview branch
          └── https://pr-123.d1234567.amplifyapp.com

PR close/merge
    │
    ▼
GitHub Actions (pr-cleanup.yml)
    │
    └── npx ampx sandbox delete --identifier pr-${PR_NUMBER} --yes
```

## コスト分析

| リソース | PR 開中のコスト/時間 | 備考 |
|---------|:---:|------|
| Cognito User Pool | $0 | Free Tier (50,000 MAU) |
| AppSync API | $0 | Free Tier (250,000 queries/月) |
| Lambda x13 | $0 | Free Tier (1M requests/月) |
| DynamoDB x5 tables | $0 | On-demand, Free Tier 25 GB |
| Amplify Hosting | ~$0.01/PR | Build minutes のみ |
| **合計 (PR 存続中)** | **~$0/PR** | 全リソースが Free Tier 内 |

> **結論**: コスト影響は実質ゼロ。主要コストは CI のビルド時間（GitHub Actions 無料枠）のみ。

## デプロイ時間

| フェーズ | 初回 | 2回目以降 (push) |
|---------|:---:|:---:|
| `npx ampx sandbox --once` | ~8-12 min | ~2-3 min (差分) |
| `npm run build` | ~10 sec | ~10 sec |
| Amplify Hosting deploy | ~30 sec | ~30 sec |
| **合計** | **~10-13 min** | **~3-4 min** |

## Workflow 設計

### pr-preview.yml (PR 作成/更新時)

```yaml
name: PR Preview Environment
on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - "solutions/amplify-portal/**"

permissions:
  contents: read
  id-token: write
  pull-requests: write

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    if: github.event.pull_request.head.repo.full_name == github.repository
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AMPLIFY_DEPLOY_ROLE_ARN }}
          aws-region: ap-northeast-1

      - name: Install dependencies
        working-directory: solutions/amplify-portal
        run: npm install

      - name: Deploy sandbox (PR-scoped)
        working-directory: solutions/amplify-portal
        run: npx ampx sandbox --identifier pr-${{ github.event.pull_request.number }} --once
        env:
          # DemoMode: use test S3 bucket (no FSx for ONTAP dependency)
          S3_AP_ALIAS: ${{ secrets.TEST_S3_BUCKET }}

      - name: Build frontend
        working-directory: solutions/amplify-portal
        run: npm run build

      - name: Comment PR with preview URL
        uses: actions/github-script@v7
        with:
          script: |
            const prNumber = context.payload.pull_request.number;
            const body = `## 🔗 Preview Environment Ready

            | Resource | URL |
            |---------|-----|
            | Portal | \`http://localhost:5173\` (run \`make dev\` locally with this sandbox) |
            | Sandbox ID | \`pr-${prNumber}\` |

            **To test locally:**
            \`\`\`bash
            cd solutions/amplify-portal
            npx ampx sandbox --identifier pr-${prNumber} --once  # connects to existing
            make dev
            \`\`\`

            **To clean up:** This environment auto-deletes when the PR is closed/merged.
            `;
            github.rest.issues.createComment({
              issue_number: prNumber,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });
```

### pr-cleanup.yml (PR クローズ/マージ時)

```yaml
name: PR Cleanup
on:
  pull_request:
    types: [closed]
    paths:
      - "solutions/amplify-portal/**"

permissions:
  contents: read
  id-token: write

jobs:
  cleanup:
    runs-on: ubuntu-latest
    if: github.event.pull_request.head.repo.full_name == github.repository
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AMPLIFY_DEPLOY_ROLE_ARN }}
          aws-region: ap-northeast-1

      - name: Install dependencies
        working-directory: solutions/amplify-portal
        run: npm install

      - name: Delete PR sandbox
        working-directory: solutions/amplify-portal
        run: npx ampx sandbox delete --identifier pr-${{ github.event.pull_request.number }} --yes
```

## 前提条件

1. **IAM ロール**: `AMPLIFY_DEPLOY_ROLE_ARN` — Amplify + CDK のフルデプロイ権限を持つ OIDC ロール
2. **テスト用 S3 バケット**: `TEST_S3_BUCKET` — DemoMode 用の通常 S3 バケット（FSx for ONTAP 不要）
3. **GitHub Actions secrets**: 上記 2 つを設定

## トレードオフと考慮事項

| 項目 | 判断 |
|------|------|
| FSx for ONTAP 接続 | 不要（DemoMode で動作確認） |
| 認証テスト | 各 PR に専用 Cognito User Pool が作られるため独立 |
| データ永続性 | PR クローズで全データ削除（DynamoDB テーブルごと消える） |
| 並行 PR 数 | AWS アカウントのリソース制限に注意（Cognito: 1000 User Pools/アカウント） |
| セキュリティ | 外部 PR（fork）では実行しない（`head.repo.full_name == github.repository`） |
| 不要なデプロイ防止 | `paths` フィルターで amplify-portal 変更時のみトリガー |

## 導入ステップ

1. [ ] IAM OIDC ロール作成（Amplify + CloudFormation 権限）
2. [ ] GitHub Secrets に `AMPLIFY_DEPLOY_ROLE_ARN` + `TEST_S3_BUCKET` 設定
3. [ ] `.github/workflows/pr-preview.yml` 作成
4. [ ] `.github/workflows/pr-cleanup.yml` 作成
5. [ ] テスト PR を作成して動作確認
6. [ ] README にプレビュー環境の使い方を追記

## 現時点の判断

本プロジェクトはソロ開発のため、PR プレビュー環境の自動化は**設計ドキュメントとして保持し、チーム開発に移行した段階で実装する**方針とする。個人開発では `npx ampx sandbox` の個人サンドボックスで十分。

## 参考

- [CDK Conference Japan 2026 セッション一覧](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
- [Amplify Gen2 Sandbox documentation](https://docs.amplify.aws/react/deploy-and-host/sandbox-environments/)
- [GitHub Actions OIDC + AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
