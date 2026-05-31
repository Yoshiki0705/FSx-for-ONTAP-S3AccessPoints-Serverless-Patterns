# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main branch | ✅ |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Email: yoshiki0705@gmail.com with subject "[SECURITY] FSx S3AP Patterns"
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Fix or mitigation**: Within 30 days for critical issues

## Scope

This security policy covers:
- CloudFormation/SAM templates (IAM policies, resource configurations)
- Python Lambda function code (shared modules, UC handlers)
- CI/CD workflow configurations
- Documentation containing sensitive patterns

## Out of Scope

- AWS service vulnerabilities (report to AWS Security)
- Third-party dependency vulnerabilities (report to upstream maintainers)
- Issues in forked/cloned environments

## Security Best Practices

This project follows:
- Least-privilege IAM policies
- SHA-pinned GitHub Actions
- Automated secret scanning (gitleaks)
- Supply-chain security (OpenSSF Scorecard)
- No hardcoded credentials or real AWS resource IDs
