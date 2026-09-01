# Contributing

Thank you for considering contributing to this project.

## How to Contribute

1. **Issues**: Report bugs or suggest features via [GitHub Issues](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues)
2. **Pull Requests**: Fork the repo, create a branch, and submit a PR

## Development Setup

```bash
cd solutions/amplify-portal
npm install
npm start  # Starts sandbox + dev server
```

See [Getting Started](solutions/amplify-portal/docs/GETTING-STARTED.md) for full setup.

Changing the portal UI? Read the
[UI Contributor Guide](solutions/amplify-portal/docs/CONTRIBUTING-UI.en.md)
([日本語](solutions/amplify-portal/docs/CONTRIBUTING-UI.md)) first. Two boundaries in the
portal are invisible to the compiler — the generic dispatch to Lambda, and UI strings
across eight locales — and the guide covers how each is checked.

## PR Guidelines

- **Branch naming**: `feat/<description>` or `fix/<description>`
- **Commit messages**: [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `chore:`
- **PR title**: Under 70 characters, conventional commit prefix
- **Tests**: `npx vitest run` in `solutions/amplify-portal` for the front end, `make test-quick` for Python
- **Lint**: `make lint` for Python (`ruff check` and `ruff format --check` both), `npm run lint` and `npx tsc -b` for TypeScript
- **Contracts**: `make drift` — the portal's action-parameter contract, i18n coverage and theme tokens are checked there, not by lint

## Code Style

- **Python**: PEP 8, type hints, Google-style docstrings
- **TypeScript/React**: Functional components, hooks, strict types
- **i18n**: All user-facing strings via `useTranslation()` hook (ja.ts is the type source)
- **Naming**: See [AGENTS.md](AGENTS.md) for full conventions

### Japanese section headings are noun phrases (体言止め)

Every heading at `##` and below in a Japanese document is a label, so it is written as a noun
phrase — not a verb-final clause (`自分の環境で確かめる`), a question (`なぜこの区分が必要か`),
or a full sentence (`記録されない読み取りがあります`). Write `自環境での確認手順`,
`この区分が必要な理由`, `記録されない読み取りの存在` instead.

Do not lose an assertion while nominalizing. A heading often carries the finding itself, and
`監査の 2 つの面と片方の穴` no longer claims the hole exists. Keep the claim with a suffix
(`〜の存在` / `不在` / `成立` / `不成立` / `必要` / `不可` / `差` / `上限`) or a modifier
(`未対応の〜`, `既定で無効な〜`). If no suffix preserves it, the heading is holding a sentence —
move that sentence into the body.

Out of scope: H1 and frontmatter `title` (those are single-claim sentences under a separate rule),
English headings, `#` lines inside code fences (shell comments — any detector must skip fences),
table cells and list items, and headings inside a numbered / `Step N` / `段階 N` walkthrough that
tell the reader to perform an action (`## 3. フォルダをたどる`). Numbered symptoms, findings and
questions are still in scope.

Renaming a heading changes its anchor. Run `grep -rn '#<old-anchor>' .`, fix every reference in
the same commit, and flag anything cited from outside the repo before renaming — GitHub serves an
unknown fragment as the top of the page, so the citing side never learns the link broke.
`make drift` does not cover heading style; check it yourself when adding or rewriting a Japanese
document.

## What We Accept

- Bug fixes with reproduction steps
- New UC patterns (industry-specific AI processing)
- Documentation improvements (especially translations)
- Performance optimizations with benchmarks
- Security hardening

## What We Don't Accept

- Vendor-specific marketing language or claims
- Changes that break DemoMode compatibility
- Dependencies with restrictive licenses (GPL in main code)
- Features that require paid third-party services without free-tier alternatives

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
