# AWS DevOps Agent — Evaluation for CDK Maintenance Automation

🌐 **Language / 言語**: [日本語](devops-agent-evaluation.md) | [English](devops-agent-evaluation.en.md)

> Reflects takeaways from the CDK Conference Japan 2026 session "Does AWS DevOps Agent make CDK maintenance easier? — the sweet spot found through evaluation".

## What DevOps Agent is

AWS DevOps Agent (GA 2026/3) is an AI agent that connects to a GitHub repository and automates change analysis, test generation, and release risk assessment. CDK resource definition: `AWS::DevOpsAgent::AgentSpace`.

## Applicability to this project

### Areas where it applies

| Use case | DevOps Agent capability | Value for this project |
|-------------|-------------------|-------------------|
| **CDK version upgrade impact analysis** | Automatic analysis of the blast radius of a code change | Automatically detect breaking changes on `aws-cdk-lib` minor/major updates |
| **PR review assistance** | Automatic evaluation against organizational standards | Review whether cdk-nag suppressions are justified |
| **Test generation** | Generate tests automatically for a given change | Append CDK harness tests automatically when a new Lambda is added |
| **Incident investigation** | Cross-cutting log/metric analysis | Trace root cause across AppSync error → Lambda error → S3 AP timeout |

### Current constraints

| Constraint | Impact |
|------|------|
| **Regions**: us-east-1, us-west-2, eu-west-1 only | Resources in ap-northeast-1 are out of monitoring scope (GitHub connection is fine) |
| **Cost**: usage-based (conversations + investigations) | Cost-effectiveness is unclear for a personal project |
| **Amplify Gen2 support**: whether it understands the backend.ts synth flow is unverified | The defineBackend pattern differs from standard CDK, so false positives are possible |
| **Memory limit**: 25KB / 120 lines recommended | Hard to make it retain the full contents of a large AGENTS.md |

## Comparison with the current approach

| Capability | Current tooling | Replace with DevOps Agent? |
|------|------------|:---:|
| Dependency updates | Renovate (automatic PRs) | ❌ Renovate is sufficient |
| Security scanning | gitleaks + zizmor + cfn-guard | ❌ Existing tooling is sufficient |
| IAM validation | validate-iam-policies.py (Access Analyzer) | ❌ The dedicated script is more precise |
| Breaking change detection | cdk-nag + CDK harness tests | ⚠️ DevOps Agent could complement it |
| Test generation | manual | ✅ Useful for generating tests when adding a feature |
| Incident investigation | manual review of CloudWatch dashboards | ✅ Cross-cutting analysis adds value |

## Decision

### Why not adopt it right now

1. **Renovate + cdk-nag + CDK harness** already cover dependency management and quality gates
2. No monitoring support for ap-northeast-1 resources (GitHub integration only)
3. Solo development, so the benefit of PR review assistance is limited
4. Usage-based pricing makes the cost hard to justify for a personal project

### When to reconsider adoption

- If development moves to a team and PR review load increases
- If a large-scale migration is needed for an `aws-cdk-lib` major version upgrade (v3, etc.)
- If a production incident occurs and cross-cutting root cause analysis is needed
- If DevOps Agent adds ap-northeast-1 monitoring support

## Alternative: automating CDK version upgrades (current approach)

Today **Renovate** updates `aws-cdk-lib` automatically, and CI validates the following:

```
Renovate PR (aws-cdk-lib bump)
    → cfn-lint (template syntax)
    → cdk-nag (compliance)
    → CDK harness tests (47 structural assertions)
    → IAM policy validation (Access Analyzer)
    → Unit tests (2,162+ tests)
```

With this layered defense, most breaking changes can be detected without DevOps Agent.

## References

- [AWS DevOps Agent — User Guide](https://docs.aws.amazon.com/devopsagent/latest/userguide/)
- [AWS DevOps Agent GA announcement (2026/3)](https://aws.amazon.com/about-aws/whats-new/2026/03/aws-devops-agent-generally-available/)
- [Getting started with AWS CDK](https://docs.aws.amazon.com/devopsagent/latest/userguide/getting-started-with-aws-devops-agent-getting-started-with-aws-devops-agent-using-aws-cdk.html)
- [CDK Conference Japan 2026](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
