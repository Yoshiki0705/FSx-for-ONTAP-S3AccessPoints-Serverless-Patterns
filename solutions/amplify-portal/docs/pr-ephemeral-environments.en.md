# Design for PR-Based Ephemeral Environments

🌐 **Language / 言語**: [日本語](pr-ephemeral-environments.md) | [English](pr-ephemeral-environments.en.md)

> Reflects takeaways from the CDK Conference Japan 2026 session "Standing up a disposable environment per PR with CDK turned out to be extremely convenient".

## Overview

A design in which an independent Amplify Gen2 sandbox (the backend) is created automatically per PR and deleted automatically when the PR is merged or closed.

> **Unimplemented, and the figures are estimates**: `.github/workflows/pr-preview.yml` and `pr-cleanup.yml` **do not exist yet**. Every time and cost below is an **unmeasured estimate**.
> The proposed workflow also stops at `npm run build` and **contains no Amplify Hosting deployment step**. A reviewer therefore has to check out the branch and run `make dev` locally, which is what the PR comment tells them to do. Making it genuinely click-through requires adding the Hosting deployment step.

## Architecture

```
PR open/sync
    │
    ▼
GitHub Actions (pr-preview.yml)
    │
    ├── npx ampx sandbox --identifier pr-${PR_NUMBER} --once
    │     ├── Cognito User Pool (pr-123-fsxn-portal)
    │     ├── AppSync API (pr-123-fsxn-portal)
    │     ├── Lambda x19 (pr-123-*)
    │     └── DynamoDB tables (pr-123-*)
    │
    ├── npm run build (Vite → dist/)
    │
    └── (not implemented) deploy to Amplify Hosting
          └── the proposed workflow stops at build; the PR comment
              gives local run instructions (make dev) instead

PR close/merge
    │
    ▼
GitHub Actions (pr-cleanup.yml)
    │
    └── npx ampx sandbox delete --identifier pr-${PR_NUMBER} --yes
```

## Cost analysis

| Resource | Cost per PR (estimate) | Notes |
|---------|:---:|------|
| Cognito User Pool | $0 | Free Tier (50,000 MAU) |
| AppSync API | $0 | Free Tier (250,000 queries/month) |
| Lambda x19 | $0 | Free Tier (1M requests/month) |
| DynamoDB x5 tables | $0 | On-demand, Free Tier 25 GB |
| Amplify Hosting | ~$0.01/PR | Build minutes only. Estimate for the case where the Hosting deployment step is implemented |
| **Total** | **~$0/PR (estimate)** | Assumes the Free Tier allowance is not consumed elsewhere. The Free Tier is account-wide, so concurrent PRs break that assumption (only Cognito's 50,000 MAU is always free) |

> **Conclusion**: the cost impact is effectively zero. The main cost is CI build time (within the GitHub Actions free allowance).

## Deployment time (unmeasured estimates)

| Phase | First run | Subsequent runs (push) |
|---------|:---:|:---:|
| `npx ampx sandbox --once` | ~8-12 min | ~2-3 min (diff) |
| `npm run build` | ~10 sec | ~10 sec |
| Amplify Hosting deploy | ~30 sec | ~30 sec |
| **Total** | **~10-13 min** | **~3-4 min** |

## Workflow design

### pr-preview.yml (on PR creation/update)

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
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v6
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
        uses: actions/github-script@v9
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

### pr-cleanup.yml (on PR close/merge)

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
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v6
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

## Prerequisites

1. **IAM role**: `AMPLIFY_DEPLOY_ROLE_ARN` — an OIDC role with full Amplify + CDK deployment permissions
2. **Test S3 bucket**: `TEST_S3_BUCKET` — a regular S3 bucket for DemoMode (no Amazon FSx for NetApp ONTAP required)
3. **GitHub Actions secrets**: configure the two above

## Trade-offs and considerations

| Item | Decision |
|------|------|
| FSx for ONTAP connectivity | Not required (behaviour is verified in DemoMode) |
| Authentication testing | Independent, because a dedicated Cognito User Pool is created per PR |
| Data persistence | All data is deleted when the PR closes (the DynamoDB tables go with it) |
| Concurrent PR count | Watch AWS account resource limits (Cognito: 1000 User Pools per account) |
| Security | Not run for external PRs from forks (`head.repo.full_name == github.repository`) |
| Preventing unnecessary deployments | The `paths` filter triggers only on amplify-portal changes |

## Adoption steps

1. [ ] Create the IAM OIDC role (Amplify + CloudFormation permissions)
2. [ ] Set `AMPLIFY_DEPLOY_ROLE_ARN` + `TEST_S3_BUCKET` in GitHub Secrets
3. [ ] Create `.github/workflows/pr-preview.yml`
4. [ ] Create `.github/workflows/pr-cleanup.yml`
5. [ ] Open a test PR and confirm the behaviour
6. [ ] Add usage notes for the preview environment to the README

## Current position

Because this project is developed solo, the policy is to **keep PR preview environment automation as a design document and implement it once development moves to a team**. For solo development, the personal sandbox from `npx ampx sandbox` is sufficient.

## References

- [CDK Conference Japan 2026 session list](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
- [Amplify Gen2 Sandbox documentation](https://docs.amplify.aws/react/deploy-and-host/sandbox-environments/)
- [GitHub Actions OIDC + AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
