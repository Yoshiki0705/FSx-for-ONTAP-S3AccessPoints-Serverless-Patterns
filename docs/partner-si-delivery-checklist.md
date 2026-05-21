# Partner/SI Delivery Checklist

🌐 **Language / 言語**: [日本語](partner-si-delivery-checklist.md) | [English](partner-si-delivery-checklist.en.md)

## 概要

本チェックリストは、パートナーおよび SI が顧客に FSx for ONTAP S3 Access Points サーバーレスパターンを提案・設計・構築する際の確認項目を整理したものです。

## 顧客ワークロード分類

### Step 1: データ特性の確認

| 確認項目 | 選択肢 | 設計への影響 |
|---------|--------|------------|
| ワークロードタイプ | SAP 周辺 / ファイルサーバー / 規制対象記録 / AI 分析 / バッチ処理 | UC パターン選択 |
| データプロトコル | NFSv3 / NFSv4.1 / SMB | FPolicy 対応可否（NFSv4.2 は非対応） |
| ファイルサイズ分布 | 小 (<1MB) / 中 (1-100MB) / 大 (100MB-5GB) / 超大 (>5GB) | Lambda メモリ・処理戦略 |
| ファイル数/日 | ~100 / ~1,000 / ~10,000 / 100,000+ | Map 並列度・コスト見積もり |
| データ機密性 | 一般 / 社内機密 / 規制対象 (FISC/HIPAA/GDPR) | Deployment Profile 選択 |

### Step 2: トリガーモード選択

| 確認項目 | 選択肢 | 推奨モード |
|---------|--------|-----------|
| 検知レイテンシ要件 | 時間単位で可 | POLLING |
| | サブ分単位が必要 | EVENT_DRIVEN or HYBRID |
| イベントロス許容度 | 許容可能 | EVENT_DRIVEN (is-mandatory=false) |
| | 許容不可 | EVENT_DRIVEN + Persistent Store or HYBRID |
| 運用複雑性の許容度 | 最小限を希望 | POLLING |
| | 中程度まで可 | EVENT_DRIVEN |
| | 高くても可 | HYBRID |

詳細: [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)

### Step 3: Deployment Profile 選択

| 確認項目 | PoC/Demo | Production | Compliance-sensitive |
|---------|----------|------------|---------------------|
| 目的 | 機能検証・デモ | 本番ワークロード | 規制対応 |
| イベントロス | 許容 | Near-zero | Zero |
| ONTAP バージョン | 9.14.1+ | 9.15.1+ | 9.15.1+ |
| Persistent Store | 不要 | 推奨 | 必須 |
| 冪等性保証 | 不要 | DynamoDB | DynamoDB + S3 Object Lock |
| 監査証跡 | 不要 | 推奨 | 必須 |

詳細: [Deployment Profiles](deployment-profiles.md)

### Step 4: アクセスモデル設計

| レイヤー | 確認項目 | 設計判断 |
|---------|---------|---------|
| AWS IAM | Lambda Role の権限範囲 | ListBucket + GetObject (最小限) or + PutObject |
| S3 AP Policy | リソースポリシーの設定 | Principal 制限 + Condition (OrgID, VPC) |
| VPC Endpoint Policy | VPC 制限の要否 | VPC Origin AP の場合は必須 |
| SCP | Organization レベルの制御 | 規制環境では必須 |
| ONTAP File System | AP に関連付ける identity | 専用ユーザー（root 禁止） |
| セキュリティスタイル | UNIX or NTFS | ボリュームのスタイルに合わせる |

> **重要**: S3 API アクセスは ONTAP ファイルシステム権限をバイパスしません。AWS 側と ONTAP 側の両方で least-privilege を設計する必要があります。

詳細: [S3AP 二段階認可モデル](s3ap-authorization-model.md)

### Step 5: ネットワークモデル

| 構成 | 説明 | 適用シナリオ |
|------|------|------------|
| Single VPC (Private) | FSx + Lambda + S3AP すべて同一 VPC | 最もシンプル、PoC 向け |
| VPC Origin AP | AP を特定 VPC にバインド | セキュリティ要件が高い環境 |
| Internet Origin AP + VPC 外 Lambda | Lambda を VPC 外で実行 | S3 Gateway EP 経由不可の回避 |
| Cross-Account | RAM 共有 or Cross-Account IAM | マルチアカウント環境 |
| Shared Services | 集中監視・ログ集約 | エンタープライズ運用 |

### Step 6: 運用モデル

| 確認項目 | 選択肢 |
|---------|--------|
| 運用主体 | 顧客自社運用 / パートナー運用 / マネージドサービス |
| 監視 | CloudWatch Alarm のみ / ダッシュボード + Alarm / SLO + Runbook |
| 障害対応 | 自動復旧のみ / Runbook 手動対応 / 24/7 オンコール |
| 変更管理 | 手動デプロイ / CI/CD (StackSets) / GitOps |
| コスト管理 | 固定予算 / 従量課金監視 / Cost Anomaly Detection |

### Step 7: 成功基準の定義

| メトリクス | 測定方法 | 目標値（例） |
|-----------|---------|------------|
| 検知レイテンシ | EventBridge event timestamp - file creation time | < 30 秒 (EVENT_DRIVEN) |
| 処理スループット | Files processed / hour | > 1,000 files/hour |
| エラー率 | Failed executions / total executions | < 1% |
| コスト | Monthly AWS bill for the pipeline | < $100/month (PoC) |
| 可用性 | Pipeline uptime | > 99.5% |
| リカバリ時間 | Time to recover from Fargate task restart | < 5 min |
| 監査対応 | Event lineage completeness | 100% (Compliance profile) |

---

## PoC 実施ガイド

### Phase 1: 環境準備（1-2 日）

1. FSx for ONTAP ファイルシステム確認（既存 or 新規作成）
2. S3 Access Point 作成 + file system identity 設定
3. テストファイル配置（NFS/SMB 経由）
4. S3 AP 経由の ListObjectsV2 / GetObject 動作確認

### Phase 2: POLLING パターン検証（1-2 日）

1. UC テンプレートのデプロイ（CloudFormation）
2. EventBridge Scheduler による定期実行確認
3. Discovery Lambda → Processing Lambda → Output 確認
4. CloudWatch メトリクス・ログ確認

### Phase 3: EVENT_DRIVEN パターン検証（2-3 日）

1. FPolicy Server (Fargate or EC2) デプロイ
2. ONTAP FPolicy 設定（external-engine, policy, scope）
3. NFS/SMB ファイル作成 → SQS → EventBridge 到達確認
4. IP Updater Lambda の動作確認（Fargate の場合）

### Phase 4: 結果評価・次ステップ決定（1 日）

1. レイテンシ・スループット・コストの測定結果整理
2. Deployment Profile の選択（PoC → Production への移行計画）
3. 追加要件の洗い出し（Persistent Store, 冪等性, 監査等）

---

## よくある質問（パートナー向け）

### Q: 既存の NFS/SMB アクセスに影響はありますか？

A: ありません。S3 Access Point をアタッチしても、NFS/SMB 経由の既存アクセスは一切変更されません。AP ポリシーの制限は AP 経由のリクエストにのみ適用されます。

### Q: SAP 環境で使えますか？

A: SAP 周辺ファイル（IDoc エクスポート、帳票出力、BW データ抽出等）の自動処理に適しています。SAP HANA データボリューム自体への S3 AP アタッチは推奨しません（パフォーマンス影響の可能性）。SAP 周辺の共有ファイルストレージに対して使用してください。

### Q: 本番環境で使うには何が必要ですか？

A: [Deployment Profiles](deployment-profiles.md) の Production profile を参照してください。主な追加要件: EC2 static IP or NLB、DynamoDB 冪等性、Full alarm profile、定期ポーリングによる reconciliation。

### Q: イベントロスゼロを保証できますか？

A: ONTAP 9.14.1+ の Persistent Store + is-mandatory=true (ONTAP 9.15.1+) の組み合わせで、テスト済みシナリオ（5-event / 20-event disconnect）ではゼロイベントロスを確認しています。ただし、Persistent Store ボリュームの容量超過時の動作は追加設計が必要です。

### Q: コスト見積もりの目安は？

A: POLLING モード（1 時間間隔、1,000 ファイル/日）で月額 $6-21。EVENT_DRIVEN モードで月額 $32-60（Fargate 24/7 含む）。処理 Lambda のコストはワークロード依存。

---

## 参考リンク

- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [Deployment Profiles](deployment-profiles.md)
- [S3AP 二段階認可モデル](s3ap-authorization-model.md)
- [Enterprise Workload Examples](enterprise-workload-examples.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [FSx for ONTAP — SAP HANA 構成ガイド](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html)
