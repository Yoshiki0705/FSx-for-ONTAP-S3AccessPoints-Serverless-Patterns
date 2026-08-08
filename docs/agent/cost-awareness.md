# コスト意識

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/cost-awareness.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## Cost Awareness

### High-Cost Resources (monitor actively)

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| FSx for ONTAP (128 MBps) | ~$194 | Core infrastructure, always running |
| NAT Gateway | ~$32 each | Needed for VPC Lambda → Internet |
| Interface VPC Endpoints | ~$7.20 each | ECR, Logs, STS, SQS, SecretsManager |
| ECS Fargate (FPolicy) | ~$35 | Set desiredCount=0 when not testing |
| Transfer Family | ~$82 | Delete when not needed |

### Cost Optimization Patterns

- Use `EnableVpcEndpoints=false` for PoC (saves ~$43/month)
- Use `DemoMode=true` to test without FSx for ONTAP
- Disable EventBridge Schedules when not actively testing
- Set ECS desiredCount=0 for FPolicy server when idle
- Use `amazon.nova-lite-v1:0` (cheapest Bedrock model) for testing
