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

## PR Guidelines

- **Branch naming**: `feat/<description>` or `fix/<description>`
- **Commit messages**: [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `chore:`
- **PR title**: Under 70 characters, conventional commit prefix
- **Tests**: Run `npm run build` (Vite) before submitting
- **Lint**: `ruff check` for Python, `eslint` for TypeScript

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
