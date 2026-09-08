# Feature Request: Scope remote_write Labels to an IAM Principal in Amazon Managed Service for Prometheus

## Current State

An ingesting identity can write any label set it likes. Nothing observed restricts which label
values a given IAM principal may claim, so one collector can emit series that appear to belong to
another tenant.

The [access-control documentation](https://docs.aws.amazon.com/prometheus/latest/userguide/security-iam.html)
describes permissions at the level of the `RemoteWrite` action on a workspace. It does not describe a
condition key or a policy shape that constrains label values. Read in full 2026-09-06.

## Why It Matters

Multi-tenant collection into one workspace has no enforceable tenancy boundary. The alternative is a
workspace per tenant, which multiplies the surrounding fixed costs — collectors, Grafana data sources,
alerting rules — and retention is applied per workspace and uniformly (`E-004`), so per-tenant
retention cannot be expressed inside one workspace either.

## Requested Behavior

An IAM condition key that constrains the label values a principal may write — for example a
`aps:LabelValue/<label>` condition usable with `aps:RemoteWrite` — so a collector's identity and the
tenant it may claim are bound together.

## Status

Tracked as `E-005`, tier `hypothesis`: the absence is reasoned from the documented policy shape and
not from a statement that it cannot be done. Filed 2026-09-06; a feature request was raised on it
2026-09-08.

**This claim is a design premise.** The two-tier retention design in this repository assumes a
workspace boundary is the only tenancy boundary available. If the condition key exists and was
missed, that design is wrong and should be revisited.
