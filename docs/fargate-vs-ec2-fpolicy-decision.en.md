# Fargate vs EC2 — FPolicy Server Decision Matrix

🌐 **Language / 言語**: [日本語](fargate-vs-ec2-fpolicy-decision.md) | [English](fargate-vs-ec2-fpolicy-decision.en.md)

## Overview

This document compares Fargate and EC2 as compute options for the FPolicy External Server.

## Decision Matrix

| Dimension | Fargate | EC2 (t4g.micro) |
|-----------|---------|-----------------|
| **IP Stability** | ❌ Changes on task restart | ✅ Static Private IP |
| **IP Management** | IP Updater Lambda required | Not required |
| **Monthly Cost (approx.)** | ~$10-15 (0.25 vCPU, 0.5GB) | ~$4 (t4g.micro) |
| **VPC Endpoint Cost** | ECR/Logs/SQS etc. required (~$30-50/month) | Can share same VPC EPs |
| **OS Management** | Not required (managed) | Patching required |
| **Scaling** | ECS Service auto-recovery | Auto Scaling Group (min=1) |
| **Startup Time** | 30-60 seconds | 1-3 minutes |
| **Event Loss (during restart)** | 30-60 second gap | 1-3 minute gap |
| **Combination with Persistent Store** | Recommended (gap compensation) | Recommended (gap compensation) |
| **Operational Complexity** | Medium (IP Updater + ECS monitoring) | Low (Static IP, OS patching only) |
| **ARM64 Support** | ✅ | ✅ (Graviton) |
| **Security Group** | Set on task ENI | Set on instance ENI |
| **Logging** | CloudWatch Logs (awslogs driver) | CloudWatch Agent or rsyslog |

## Operational Responsibility Comparison

| Operations Item | Fargate | EC2 |
|----------------|---------|-----|
| OS Patch Management | Not required (AWS managed) | Required (AMI update or SSM Patch Manager) |
| Capacity Management | Automatic (ECS Service) | ASG configuration required |
| Startup Latency | 30-60 seconds | 1-3 minutes (AMI boot) |
| Long-lived Connection Maintenance | ECS Service auto-recovery | Process monitoring + systemd |
| HA Design | ECS Service (desiredCount=1, auto-restart) | ASG (min=1, max=1) + health check |
| Log Collection | awslogs driver (automatic) | CloudWatch Agent configuration required |
| Operations Ownership | Application code only | App + OS + Network |

## Selection Flowchart

```
Do you want to avoid OS patch management?
├── Yes → Fargate
│   └── Is VPC Endpoint cost (~$30-50/month) acceptable?
│       ├── Yes → Fargate ✅
│       └── No → EC2 (lower cost with shared VPC EPs)
└── No
    └── Is minimum cost the priority?
        ├── Yes → EC2 (t4g.micro ~$4/month) ✅
        └── No → Fargate (operational simplicity priority)
```

## Recommended Configurations

### PoC / Demo
- **Fargate** recommended (no OS management, immediate deployment)
- VPC Endpoint cost is acceptable for limited PoC duration

### Production
- **EC2 (t4g.micro)** recommended (Static IP eliminates IP Updater, low cost)
- Auto Scaling Group (min=1, max=1) for automatic recovery
- UserData for automatic FPolicy Server startup

### Compliance-sensitive
- **EC2** recommended (Static IP + Persistent Store for reliable event delivery)
- AMI hardening + Inspector for patch management

## Cost Comparison (Monthly, ap-northeast-1)

| Component | Fargate Configuration | EC2 Configuration |
|-----------|----------------------|-------------------|
| Compute | $10-15 | $4 |
| VPC Endpoints (ECR, Logs, SQS) | $30-50 | $0 (shared existing EPs) |
| IP Updater Lambda | $1-2 | $0 |
| CloudWatch Logs | $1-3 | $1-3 |
| **Total** | **$42-70** | **$5-7** |

> EC2 configuration shows minimum cost when VPC Endpoints already exist in the VPC. For new VPCs, VPC Endpoint costs will be additional.

## Templates

The repository includes both templates:
- `solutions/event-driven/fpolicy/template.yaml` — Fargate configuration
- `solutions/event-driven/fpolicy/template-ec2.yaml` — EC2 configuration

Switchable via the `ComputeType` parameter.

## References

- [Deployment Profiles](deployment-profiles.md)
- [solutions/event-driven/fpolicy/ README](../solutions/event-driven/fpolicy/README.md)
