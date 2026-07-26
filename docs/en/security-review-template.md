# Security Review Template — File Portal

> One-page sign-off document for CISO / security team approval before production deployment.

---

## Project Information

| Field | Value |
|-------|-------|
| Application Name | FSx for ONTAP File Portal |
| Environment | ☐ Sandbox / ☐ Staging / ☐ Production |
| Review Date | YYYY-MM-DD |
| Reviewer Role | (e.g., Security Architect, CISO) |
| Stack Name | `amplify-<project>-<env>-<hash>` |
| Region | ap-northeast-1 |

---

## Security Controls In Place

| Control | Status | Evidence |
|---------|:---:|---------|
| **Authentication** — Cognito User Pool (email + password or External IdP) | ☐ | User Pool ID: |
| **Authorization** — AppSync schema-level group auth (`storage-admin`) | ☐ | Schema file: `amplify/data/resource.ts` |
| **Encryption at rest** — FSx for ONTAP KMS, DynamoDB SSE, S3 SSE-S3 | ☐ | AWS managed |
| **Encryption in transit** — HTTPS (AppSync, S3 AP), TLS 1.2+ | ☐ | AWS enforced |
| **Secrets management** — Secrets Manager for ONTAP credentials | ☐ | Secret ARN: |
| **Network isolation** — VPC Lambda in private subnet, no public IP | ☐ | VPC ID: |
| **IAM least privilege** — Scoped to specific resource ARNs | ☐ | Review `backend.ts` inline policies |
| **Logging** — CloudWatch Logs (Lambda), CloudTrail (S3 data events) | ☐ | Log retention: days |
| **Monitoring** — CloudWatch alarms (Lambda errors, latency) | ☐ | Alarm ARNs: |
| **Data classification** — PHI paths blocked from AI processing | ☐ | `isPhiPath()` in FileExplorer.tsx |
| **Object Lock** — S3 output bucket with retention policy | ☐ | Bucket: |

---

## Residual Risks

| Risk | Likelihood | Impact | Mitigation | Accepted? |
|------|:---:|:---:|-----------|:---:|
| Lambda SG shares FSx SG (broad egress) | Medium | Low | Production checklist recommends separation | ☐ |
| `resources: ["*"]` on IAM (sandbox default) | High (sandbox) | Medium | Restrict to specific ARNs per checklist | ☐ |
| GraphQL Introspection enabled | Low | Low | Disable in AppSync Console for production | ☐ |
| No WAF on AppSync endpoint | Medium | Medium | Add AWS WAF with rate limiting | ☐ |
| Cognito MFA not enforced (default) | Medium | High | Enable MFA in Cognito settings | ☐ |
| Cross-Region Inference (Bedrock) | Low | Medium | Pin to single-region inference profile | ☐ |

---

## Acceptance Criteria

Before signing off, confirm:

- [ ] All "Status" checkboxes above are checked (controls verified)
- [ ] All "Accepted?" residual risks have been explicitly accepted or mitigated
- [ ] Production checklist in [GETTING-STARTED.md](../../solutions/amplify-portal/docs/GETTING-STARTED.md) has been followed (13 items)
- [ ] `CDK_NAG=1` run produces no new un-suppressed findings
- [ ] Penetration test scheduled (or waived with justification)
- [ ] Incident response runbook reviewed ([ARP isolation guide](./arp-ai-isolation-demo-guide.md))
- [ ] Data classification policy applied to all volumes accessible via S3 AP

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Security Reviewer | | | |
| System Owner | | | |
| CISO (if required) | | | |

---

## References

- [Production Checklist](../../solutions/amplify-portal/docs/GETTING-STARTED.md#本番移行チェックリスト)
- [Authorization Model](./portal-authorization-model.md)
- [External IdP Setup](./external-idp-setup.md)
- [Well-Architected Review](./well-architected-review.md)
