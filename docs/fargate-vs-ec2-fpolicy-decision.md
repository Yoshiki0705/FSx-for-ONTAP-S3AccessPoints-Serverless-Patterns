# Fargate vs EC2 — FPolicy Server Decision Matrix

🌐 **Language / 言語**: [日本語](fargate-vs-ec2-fpolicy-decision.md) | [English](fargate-vs-ec2-fpolicy-decision.en.md)

## 概要

FPolicy External Server のコンピュート選択肢として Fargate と EC2 を比較します。

## Decision Matrix

| Dimension | Fargate | EC2 (t4g.micro) |
|-----------|---------|-----------------|
| **IP 安定性** | ❌ タスク再起動で変更 | ✅ Static Private IP |
| **IP 管理** | IP Updater Lambda 必要 | 不要 |
| **月額コスト（概算）** | ~$10-15 (0.25 vCPU, 0.5GB) | ~$4 (t4g.micro) |
| **VPC Endpoint コスト** | ECR/Logs/SQS 等が必要（~$30-50/月） | 同じ VPC EP を共有可能 |
| **OS 管理** | 不要（マネージド） | パッチ適用が必要 |
| **スケーリング** | ECS Service auto-recovery | Auto Scaling Group (min=1) |
| **起動時間** | 30-60 秒 | 1-3 分 |
| **イベントロス（再起動中）** | 30-60 秒のギャップ | 1-3 分のギャップ |
| **Persistent Store との組み合わせ** | 推奨（ギャップ補完） | 推奨（ギャップ補完） |
| **運用複雑性** | 中（IP Updater + ECS 監視） | 低（Static IP、OS パッチのみ） |
| **ARM64 対応** | ✅ | ✅ (Graviton) |
| **セキュリティグループ** | タスク ENI に設定 | インスタンス ENI に設定 |
| **ログ** | CloudWatch Logs (awslogs driver) | CloudWatch Agent or rsyslog |

## 選択フローチャート

```
OS パッチ管理を避けたいか？
├── Yes → Fargate
│   └── VPC Endpoint コスト（~$30-50/月）は許容できるか？
│       ├── Yes → Fargate ✅
│       └── No → EC2（VPC EP 共有で低コスト）
└── No
    └── 最小コストを優先するか？
        ├── Yes → EC2 (t4g.micro ~$4/月) ✅
        └── No → Fargate（運用簡素化優先）
```

## 推奨構成

### PoC / Demo
- **Fargate** 推奨（OS 管理不要、即座にデプロイ可能）
- VPC Endpoint コストは PoC 期間限定なら許容

### Production
- **EC2 (t4g.micro)** 推奨（Static IP で IP Updater 不要、低コスト）
- Auto Scaling Group (min=1, max=1) で自動復旧
- UserData で FPolicy Server を自動起動

### Compliance-sensitive
- **EC2** 推奨（Static IP + Persistent Store で確実なイベント配信）
- AMI ハードニング + Inspector でパッチ管理

## コスト比較（月額、ap-northeast-1）

| コンポーネント | Fargate 構成 | EC2 構成 |
|--------------|-------------|---------|
| コンピュート | $10-15 | $4 |
| VPC Endpoints (ECR, Logs, SQS) | $30-50 | $0 (既存 EP 共有) |
| IP Updater Lambda | $1-2 | $0 |
| CloudWatch Logs | $1-3 | $1-3 |
| **合計** | **$42-70** | **$5-7** |

> EC2 構成は既存 VPC に VPC Endpoint が設定済みの場合の最小コスト。新規 VPC の場合は VPC Endpoint コストが追加される。

## テンプレート

リポジトリには両方のテンプレートが含まれています:
- `event-driven-fpolicy/template.yaml` — Fargate 構成
- `event-driven-fpolicy/template-ec2.yaml` — EC2 構成

`ComputeType` パラメータで切り替え可能。

## 参考リンク

- [Deployment Profiles](deployment-profiles.md)
- [event-driven-fpolicy/ README](../event-driven-fpolicy/README.md)
