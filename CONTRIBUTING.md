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
