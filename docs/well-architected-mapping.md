# AWS Well-Architected Framework 対応表

🌐 **Language / 言語**: [日本語](well-architected-mapping.md) | [English](well-architected-mapping.en.md)

## 概要

本リポジトリのアーキテクチャ設計判断を AWS Well-Architected Framework の 6 つの柱に対してマッピングします。

---

## 1. Operational Excellence（運用上の優秀性）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| Infrastructure as Code | CloudFormation (SAM Transform) 全 UC テンプレート | 各 UC `template.yaml` |
| 可観測性 | X-Ray トレーシング + CloudWatch EMF メトリクス + Dashboard | Phase 3+ |
| アラーム自動化 | BATCH / REALTIME / HIGH_VOLUME プロファイル | Phase 10 |
| Runbook | SLO 違反時の対応手順 | `docs/runbooks/` |
| 段階的デプロイ | 4-level Maturity Model | [Production Readiness](production-readiness.md) |
| CI/CD | cfn-lint + pytest + ruff + 6 バリデータ | `scripts/` |
| コスト可視化 | Business Hours Scheduling + EstimatedMonthlySavings メトリクス | Phase 10 |

## 2. Security（セキュリティ）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| 最小権限 IAM | S3 AP ARN 形式 + アクション制限 | [S3AP Authorization Model](s3ap-authorization-model.md) |
| デュアルレイヤー認可 | IAM + ONTAP file system identity | [S3AP Authorization Model](s3ap-authorization-model.md) |
| 暗号化（保管時） | SSE-FSX (KMS managed) + SSE-KMS (S3 Output) | 各テンプレート |
| 暗号化（転送時） | TLS デフォルト有効 | `shared/ontap_client.py` |
| シークレット管理 | Secrets Manager + ローテーション | Phase 12 |
| VPC 分離 | VPC 内 Lambda + VPC Endpoint | Phase 9 |
| Block Public Access | S3 AP で常時有効（変更不可） | AWS 仕様 |
| SCP / Organization | StackSets execution role に OrgID 条件 | Phase 10 |
| PII 検出 | Comprehend PII detection + 墨消し | UC2, UC14, UC16 |
| 監査ログ | CloudTrail + S3 Access Logs + DynamoDB Lineage | [Governance Checklist](governance-checklist.md) |

## 3. Reliability（信頼性）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| イベント耐久性 | Persistent Store (ONTAP 9.14.1+) | [Deployment Profiles](deployment-profiles.md) |
| 冪等性 | DynamoDB conditional write | Phase 11+ |
| DLQ | SQS Dead Letter Queue | 各テンプレート |
| Retry | Step Functions Retry + Lambda retry | 各テンプレート |
| 自動復旧 | ECS Service auto-recovery / ASG | [Fargate vs EC2](fargate-vs-ec2-fpolicy-decision.md) |
| Multi-AZ | FSx for ONTAP Multi-AZ 対応 | AWS 仕様 |
| DR | SnapMirror Cross-Region | Phase 5 |
| Replay Storm Protection | 流量制御 + バックプレッシャー | Phase 12 |

## 4. Performance Efficiency（パフォーマンス効率）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| FSx スループット依存の認識 | Map 並列度を FSx provisioned throughput に合わせて設計 | [S3AP Performance](s3ap-performance-considerations.md) |
| Dynamic MaxConcurrency | ファイル数に応じた並列度自動計算 | Phase 10 |
| Lambda メモリ最適化 | UC 別の推奨メモリサイズ | [S3AP Performance](s3ap-performance-considerations.md) |
| ARM64 | Graviton (Lambda + Fargate + EC2) | 全テンプレート |
| Prefix フィルタリング | ListObjectsV2 の Prefix 活用 | Discovery Lambda |
| ストリーミング処理 | 大ファイルの chunk 処理 | `shared/s3ap_helper.py` |

## 5. Cost Optimization（コスト最適化）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| サーバーレス | Lambda + Step Functions（実行時のみ課金） | 全 UC |
| Business Hours Scheduling | 営業時間外はポーリング頻度を下げる | Phase 10 |
| VPC Endpoint オプショナル化 | Interface EP を Conditions で制御 | Phase 9 |
| Graviton | ARM64 で ~20% コスト削減 | 全テンプレート |
| Conditions によるオプトイン | SageMaker, Kinesis 等は有効化しない限り課金なし | Phase 3 |
| コスト可視化 | EstimatedMonthlySavings メトリクス | Phase 10 |
| EC2 vs Fargate 選択 | コスト差 $5-7 vs $42-70/月 | [Fargate vs EC2](fargate-vs-ec2-fpolicy-decision.md) |

## 6. Sustainability（持続可能性）

| 設計判断 | 実装 | 関連ドキュメント |
|---------|------|----------------|
| データ移動の最小化 | S3 AP でデータを FSx に残したまま処理 | アーキテクチャ全体 |
| Graviton (ARM64) | エネルギー効率の高いプロセッサ | 全テンプレート |
| オンデマンド実行 | 常時稼働リソースの最小化 | POLLING モード |
| 差分処理 | 変更ファイルのみ処理（全スキャン回避） | Discovery Lambda |

---

## Trade-offs（設計上のトレードオフ）

| 設計判断 | メリット | トレードオフ |
|---------|---------|------------|
| VPC Endpoint 有効化 | セキュリティ向上（プライベート通信） | コスト増（Interface EP ~$30-50/月） |
| POLLING モード | 予測可能、冪等、イベントロスなし | リアルタイム性なし（スケジュール間隔依存） |
| EVENT_DRIVEN モード | サブ秒検知 | 運用複雑性増（FPolicy + Fargate/EC2） |
| FSx for ONTAP S3 AP 出力 (OutputDestination=FSXN_S3AP) | One-copy 体験、NFS/SMB ユーザーが結果閲覧可能 | S3 ネイティブ機能（Lifecycle, Versioning）非対応 |
| EC2 FPolicy Server | Static IP、低コスト | OS パッチ管理、運用責任増 |
| Fargate FPolicy Server | OS 管理不要 | IP 変動、VPC EP コスト、起動レイテンシ |
| ARM64 (Graviton) | ~20% コスト削減、エネルギー効率 | 一部ネイティブ依存ライブラリの互換性確認が必要 |
| Business Hours Scheduling | コスト削減（オフピーク時の実行頻度低下） | オフピーク時の検知遅延増加 |
| Persistent Store | イベントロスゼロ（再接続時リプレイ） | ONTAP 9.14.1+ 必須、ボリューム容量管理が必要 |

## 参考リンク

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
