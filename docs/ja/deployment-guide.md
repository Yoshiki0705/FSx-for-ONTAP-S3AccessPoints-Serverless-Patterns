# デプロイガイド — FSx for ONTAP S3 Access Points サーバーレスパターン

> **Language / 言語**: [日本語](../ja/deployment-guide.md) | [English](../en/deployment-guide.md)

本ガイドでは、**既存の** Amazon FSx for NetApp ONTAP 環境にパターンスタックをデプロイする方法を説明します。本リポジトリのテンプレートは**オーバーレイスタック**であり、FSx ファイルシステム、SVM、ボリュームは作成しません。FSx for ONTAP インフラストラクチャは事前にプロビジョニング済みである必要があります。

---

## 最初に読む: デプロイ判断フロー

```
FSx for ONTAP は既にデプロイ済みですか？
│
├─ はい → 本番環境にデプロイしたいですか？
│         ├─ はい → パス C（本番）— 「検証済みデプロイパス」参照
│         └─ いいえ → パス A（Quick Start: sam deploy --guided）
│
└─ いいえ → パス B（DemoMode）— FSx 不要、約 5 分でデプロイ
```

**初めての方**: まずパス B（DemoMode）でパターンのエンドツーエンド動作を確認し、その後パス A/C で実際の FSx for ONTAP 環境に移行してください。

---

## 目次

1. [最初に読む: デプロイ判断フロー](#最初に読む-デプロイ判断フロー)
2. [前提条件](#前提条件)
3. [スタック一覧と Tier 分類](#スタック一覧と-tier-分類)
4. [パラメータマッピング — 既存リソースとスタックパラメータの対応](#パラメータマッピング)
5. [VPC Endpoint 競合マトリクス](#vpc-endpoint-競合マトリクス)
6. [検証済みデプロイパス](#検証済みデプロイパス)
7. [コスト見積もり](#コスト見積もり)
8. [デプロイ所要時間の目安](#デプロイ所要時間の目安)
9. [Day 2 運用](#day-2-運用)
10. [ロールバック・クリーンアップ](#ロールバッククリーンアップ)
11. [ONTAP バージョン要件](#ontap-バージョン要件)
12. [トラブルシューティング](#トラブルシューティング)
13. [CI/CD 統合](#cicd-統合)

---

## 前提条件

| 項目 | 要件 |
|------|------|
| AWS アカウント | 適切な IAM 権限を持つアクティブなアカウント |
| FSx for ONTAP | ファイルシステム（Multi-AZ または Single-AZ）がデプロイ済み |
| SVM | 少なくとも 1 つの Storage Virtual Machine が構成済み |
| ボリューム | データを含む FlexVol または FlexGroup ボリュームが 1 つ以上存在 |
| S3 Access Point | 対象ボリュームに作成・アタッチ済み（`fsx:CreateAndAttachS3AccessPoint`） |
| AWS CLI | v2.15 以上（認証情報設定済み） |
| SAM CLI | v1.100 以上（`sam build` / `sam deploy` 用） |
| Python | 3.12 以上（Lambda ランタイムターゲット） |
| ONTAP バージョン | 9.14.1 以上（S3 AP サポート）; FPolicy mandatory モードは 9.15.1 以上 |
| VPC | FSx for ONTAP がデプロイされた VPC; Lambda 用プライベートサブネットが利用可能 |
| Secrets Manager | ONTAP 管理者認証情報を JSON シークレットとして格納済み |

### デプロイに必要な最小 IAM 権限

`cloudformation create-stack` / `sam deploy` を実行する IAM プリンシパルには以下が必要です：

```json
{
  "Effect": "Allow",
  "Action": [
    "cloudformation:*",
    "s3:*",
    "lambda:*",
    "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
    "iam:PassRole", "iam:DeleteRole", "iam:DetachRolePolicy",
    "states:*",
    "events:*",
    "scheduler:*",
    "sns:*",
    "logs:*",
    "ec2:CreateVpcEndpoint", "ec2:DescribeVpcEndpoints",
    "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups",
    "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupEgress",
    "secretsmanager:GetSecretValue",
    "bedrock:InvokeModel"
  ],
  "Resource": "*"
}
```

> **セキュリティに関する補足**: 本番環境では `Resource` を特定の ARN にスコープしてください。上記は PoC/評価用の出発点です。

### スループットに関する補足

S3 Access Point 経由のリクエストは、NFS/SMB クライアント I/O と**同じスループット容量**を消費します。ファイルシステムがスループット上限に近い状態で動作している場合、Lambda 関数の S3 AP 読み取りは既存の NAS クライアントと競合します。CloudWatch で `TotalThroughput` を監視し、必要に応じてスループット容量の増加を検討してください。詳細は [S3 AP パフォーマンス考慮事項](../s3ap-performance-considerations.md) を参照。

### 既存リソース ID の取得方法

```bash
# FSx for ONTAP ファイルシステム
aws fsx describe-file-systems --query "FileSystems[?FileSystemType=='ONTAP'].[FileSystemId,DNSName]" --output table

# SVM 一覧
aws fsx describe-storage-virtual-machines --query "StorageVirtualMachines[].[StorageVirtualMachineId,Name,FileSystemId]" --output table

# ボリューム一覧
aws fsx describe-volumes --query "Volumes[?VolumeType=='ONTAP'].[VolumeId,Name,OntapConfiguration.StorageVirtualMachineId]" --output table

# S3 Access Point（FSx for ONTAP にアタッチ済み）
aws s3control list-access-points --account-id $(aws sts get-caller-identity --query Account --output text) \
  --query "AccessPointList[?contains(Name,'fsx')].[Name,Alias,NetworkOrigin]" --output table

# ONTAP 管理 IP アドレス
aws fsx describe-file-systems --file-system-ids fs-XXXXXXXXX \
  --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]" --output text

# SVM UUID（ONTAP REST API 経由）
curl -sku admin:PASSWORD "https://<MANAGEMENT-IP>/api/svm/svms?fields=uuid,name" | jq '.records[]'
```

---

## スタック一覧と Tier 分類

43 の独立した CloudFormation/SAM テンプレートを、インフラ要件に基づく 3 つのデプロイ Tier に分類しています。

### Tier 1 — VPC 外部（軽量）

VPC 設定不要。Lambda 関数が Internet-origin S3 Access Point に直接アクセスします。

| # | パターン | パス | 主な依存先 |
|---|---------|------|-----------|
| - | Content Edge Delivery | `solutions/edge/content-delivery/` | S3 AP（Internet-origin） |
| - | Media IVS VOD Publishing | `solutions/edge/media-ivs-vod-publishing/` | S3 AP（Internet-origin）、IVS |
| - | KB Self-Service Curation | `solutions/genai/kb-selfservice-curation/` | S3 AP、Bedrock KB |
| - | Quick Agentic Workspace | `solutions/genai/quick-agentic-workspace/` | S3 AP、Bedrock、Athena |

### Tier 2 — VPC 内部（標準 Industry パターン）

Lambda 関数を VPC プライベートサブネットに配置。VPC ID、サブネット ID、オプションで VPC Endpoints が必要です。

| # | パターン | パス | 主な依存先 |
|---|---------|------|-----------|
| UC1 | 法務コンプライアンス | `solutions/industry/legal-compliance/` | ONTAP API、S3 AP、Athena、Bedrock |
| UC2 | 金融 IDP | `solutions/industry/financial-idp/` | ONTAP API、S3 AP、Textract、Bedrock |
| UC3 | 医療 DICOM | `solutions/industry/healthcare-dicom/` | ONTAP API、S3 AP、Bedrock |
| UC4 | 政府アーカイブ | `solutions/industry/government-archives/` | ONTAP API、S3 AP、Bedrock |
| UC5 | 防衛衛星 | `solutions/industry/defense-satellite/` | ONTAP API、S3 AP、Bedrock |
| UC6 | 半導体 EDA | `solutions/industry/semiconductor-eda/` | ONTAP API、S3 AP、Bedrock |
| UC7 | 製造業分析 | `solutions/industry/manufacturing-analytics/` | ONTAP API、S3 AP、Bedrock |
| UC8 | メディア VFX | `solutions/industry/media-vfx/` | ONTAP API、S3 AP、Bedrock |
| UC9 | 小売カタログ | `solutions/industry/retail-catalog/` | ONTAP API、S3 AP、Rekognition、Bedrock |
| UC10 | 教育研究 | `solutions/industry/education-research/` | ONTAP API、S3 AP、Bedrock |
| UC11 | エネルギー地震探査 | `solutions/industry/energy-seismic/` | ONTAP API、S3 AP、Bedrock |
| UC12 | 物流 OCR | `solutions/industry/logistics-ocr/` | ONTAP API、S3 AP、Textract、Bedrock |
| UC13 | 建設 BIM | `solutions/industry/construction-bim/` | ONTAP API、S3 AP、Bedrock |
| UC14 | 不動産ポートフォリオ | `solutions/industry/real-estate-portfolio/` | ONTAP API、S3 AP、Bedrock |
| UC15 | 保険請求 | `solutions/industry/insurance-claims/` | ONTAP API、S3 AP、Textract、Bedrock |
| UC16 | 交通保守 | `solutions/industry/transportation-maintenance/` | ONTAP API、S3 AP、Bedrock |
| UC17 | 通信ネットワーク分析 | `solutions/industry/telecom-network-analytics/` | ONTAP API、S3 AP、Bedrock |
| UC18 | スマートシティ地理空間 | `solutions/industry/smart-city-geospatial/` | ONTAP API、S3 AP、Bedrock |
| UC19 | 自動運転 | `solutions/industry/autonomous-driving/` | ONTAP API、S3 AP、Bedrock |
| UC20 | ゲノミクスパイプライン | `solutions/industry/genomics-pipeline/` | ONTAP API、S3 AP、Bedrock |
| UC21 | 化学 SDS 管理 | `solutions/industry/chemical-sds-management/` | ONTAP API、S3 AP、Bedrock |
| UC22 | サステナビリティ ESG | `solutions/industry/sustainability-esg-reporting/` | ONTAP API、S3 AP、Bedrock |
| UC23 | 旅行文書処理 | `solutions/industry/travel-document-processing/` | ONTAP API、S3 AP、Textract、Bedrock |
| UC24 | AdTech クリエイティブ管理 | `solutions/industry/adtech-creative-management/` | ONTAP API、S3 AP、Rekognition、Bedrock |
| UC25 | 農業食品トレーサビリティ | `solutions/industry/agri-food-traceability/` | ONTAP API、S3 AP、Bedrock |
| UC26 | HR 文書スクリーニング | `solutions/industry/hr-document-screening/` | ONTAP API、S3 AP、Bedrock |
| UC27 | NPO 助成金管理 | `solutions/industry/nonprofit-grant-management/` | ONTAP API、S3 AP、Bedrock |
| UC28 | 公益事業資産検査 | `solutions/industry/utilities-asset-inspection/` | ONTAP API、S3 AP、Rekognition、Bedrock |
| SAP | SAP/ERP Adjacent | `solutions/sap/erp-adjacent/` | ONTAP API、S3 AP、Bedrock |
| HA | LifeKeeper 監視 | `solutions/ha/lifekeeper-monitoring/` | ONTAP API、S3 AP、Bedrock |
| FC1 | FlexCache Anycast DR | `solutions/flexcache/anycast-dr/` | ONTAP API、DynamoDB |
| FC2 | Dynamic Render Workflow | `solutions/flexcache/dynamic-render-workflow/` | ONTAP API、S3 AP |
| FC3 | RAG Enterprise Files | `solutions/flexcache/rag-enterprise-files/` | ONTAP API、S3 AP、Bedrock |
| FC4 | Automotive CAE | `solutions/flexcache/automotive-cae/` | ONTAP API、S3 AP |
| FC5 | Life Sciences Research | `solutions/flexcache/life-sciences-research/` | ONTAP API、S3 AP |
| FC6 | Gaming Build Pipeline | `solutions/flexcache/gaming-build-pipeline/` | ONTAP API、S3 AP |
| FC7 | DevOps CI/CD | `solutions/flexcache/devops-cicd/` | ONTAP API、S3 AP |

### Tier 3 — インフラ重量級（ネットワーキング + コンピュート）

VPC、サブネット、Security Group に加え、追加コンピュート（ECS Fargate / EC2）が必要です。

| # | パターン | パス | 主な依存先 |
|---|---------|------|-----------|
| - | FPolicy イベント駆動 | `solutions/event-driven/fpolicy/` | VPC、SG、ECS/EC2、SQS、EventBridge、ONTAP API |
| - | Event-Driven Prototype | `solutions/event-driven/prototype/` | VPC、SQS、EventBridge |

---

## パラメータマッピング

### 共通パラメータ（全 Tier 2 Industry パターン）

| 既存リソース | テンプレートパラメータ | 取得方法 |
|-------------|---------------------|----------|
| S3 Access Point エイリアス | `S3AccessPointAlias` | `aws s3control list-access-points` → `Alias` フィールド |
| S3 Access Point 名 | `S3AccessPointName` | 同コマンド → `Name` フィールド |
| ONTAP シークレット名 | `OntapSecretName` | Secrets Manager コンソール / `aws secretsmanager list-secrets` |
| ONTAP 管理 IP | `OntapManagementIp` | `aws fsx describe-file-systems` → Management エンドポイント |
| SVM UUID | `SvmUuid` | ONTAP REST API: `GET /api/svm/svms` |
| ボリューム UUID | `VolumeUuid` | ONTAP REST API: `GET /api/storage/volumes?svm.name=<SVM>` |
| VPC ID | `VpcId` | `aws ec2 describe-vpcs`（FSx と同じ VPC） |
| プライベートサブネット ID | `PrivateSubnetIds` | `aws ec2 describe-subnets --filters "Name=vpc-id,Values=<VPC>"` |
| ルートテーブル ID | `PrivateRouteTableIds` | `aws ec2 describe-route-tables --filters "Name=vpc-id,Values=<VPC>"` |
| 出力用 S3 バケット | `OutputBucketName` | 新規作成または既存バケットを指定 |
| 通知先メール | `NotificationEmail` | アラート受信者のメールアドレス |

### FPolicy イベント駆動パターン（Tier 3）— 追加パラメータ

| 既存リソース | テンプレートパラメータ | 取得方法 |
|-------------|---------------------|----------|
| VPC ID | `VpcId` | FSx for ONTAP と同一 VPC |
| プライベートサブネット ID | `SubnetIds` | FSx と同じ AZ のプライベートサブネット |
| SVM Security Group ID | `FsxnSvmSecurityGroupId` | FSx SVM ENI にアタッチされた SG |
| コンテナイメージ URI | `ContainerImage` | FPolicy サーバーイメージを格納した ECR リポジトリ |
| SVM 管理 IP | `FsxnMgmtIp` | ONTAP 管理エンドポイント |
| SVM UUID | `FsxnSvmUuid` | ONTAP REST API |
| ONTAP 認証情報シークレット | `FsxnCredentialsSecret` | Secrets Manager シークレット名 |

### DemoMode — FSx for ONTAP なしでの動作確認

多くのパターンは `DemoMode=true` をサポートしており、S3 AP エイリアスの代わりに通常の S3 バケット名を受け付け、ONTAP API 呼び出しをスキップします。以下の用途に利用できます：
- FSx for ONTAP なしでの機能検証
- パートナーデモンストレーション
- CI/CD パイプラインテスト

---

## VPC Endpoint 競合マトリクス

同一 VPC に複数のスタックをデプロイする場合、VPC Endpoint が競合する可能性があります。2 種類のエンドポイントの違いを理解することが重要です。

### Gateway Endpoint（S3、DynamoDB）

- **ルートテーブル**に関連付け（サブネットではない）
- **PrivateDNS 競合なし** — ルートテーブル関連付けの重複のみ問題
- **競合シナリオ**: 2 つのスタックが同じルートテーブルに対して S3 Gateway の `AWS::EC2::VPCEndpoint` を作成 → CloudFormation エラー
- **解決策**: 2 番目のスタックで `EnableS3GatewayEndpoint=false` を設定（VPC あたり 1 つで十分）

### Interface Endpoint（Secrets Manager、STS、Logs、Bedrock 等）

- **サブネット**に ENI として配置
- **PrivateDNS 競合**: 同一サービスの Interface Endpoint は VPC あたり 1 つのみ `PrivateDnsEnabled=true` にできる
- **競合シナリオ**: スタック A が `com.amazonaws.region.secretsmanager` を PrivateDNS 付きで作成 → スタック B が同じものを作成しようとして `InvalidParameter: already exists` エラー
- **解決策**: 後続スタックで `EnableVpcEndpoints=false` を設定し、既存エンドポイントを共有

### 競合解決マトリクス

| サービス | タイプ | VPC あたり最大数 | 無効化パラメータ |
|---------|--------|----------------|----------------|
| `com.amazonaws.REGION.s3` | Gateway | 1（ルートテーブルセットあたり） | `EnableS3GatewayEndpoint=false` |
| `com.amazonaws.REGION.dynamodb` | Gateway | 1（ルートテーブルセットあたり） | N/A（FPolicy テンプレートのみ） |
| `com.amazonaws.REGION.secretsmanager` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.sts` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.logs` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.bedrock-runtime` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.athena` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.glue` | Interface | 1（PrivateDNS 付き） | `EnableVpcEndpoints=false` |

### 推奨戦略

1. **最初のスタック**: `EnableVpcEndpoints=true` かつ `EnableS3GatewayEndpoint=true` でデプロイ
2. **同一 VPC への後続スタック**: 両方を `false` に設定してデプロイ
3. **代替案**: 必要な VPC Endpoint を全て事前に個別作成し、全スタックで `EnableVpcEndpoints=false` にする

---

## 検証済みデプロイパス

### パス A: 単一パターン Quick Start（初回デプロイ推奨）

最もシンプルなパスは SAM CLI のインタラクティブな `--guided` モードで、各パラメータを対話的に入力できます：

```bash
# 1. プリフライトチェック実行
./shared/scripts/preflight-check.sh --profile quick-start

# 2. UC1（法務コンプライアンス）を最初のパターンとしてデプロイ
cd solutions/industry/legal-compliance
sam build
sam deploy --guided
# プロンプトに従って各パラメータを入力
# Tip: SAM は入力内容を samconfig.toml に保存し、次回以降のデプロイで再利用
```

初回の `--guided` デプロイ後、以降の更新は以下だけで完了します：
```bash
sam build && sam deploy
```

### パス B: DemoMode 評価（FSx for ONTAP 不要）

```bash
# 1. テスト用 S3 バケットを作成しサンプルデータを配置
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="fsxn-demo-${ACCOUNT_ID}"
aws s3 mb "s3://${BUCKET}"

# 2. サンプルファイルをアップロード（任意のテキスト/PDF/JSON ファイル）
echo '{"sample": "document", "type": "idoc"}' > /tmp/sample.json
aws s3 cp /tmp/sample.json "s3://${BUCKET}/idoc-export/sample.json"

# 3. DemoMode=true でデプロイ
cd solutions/sap/erp-adjacent
sam build
sam deploy --parameter-overrides \
  "DemoMode=true" \
  "S3AccessPointAlias=${BUCKET}" \
  "OutputBucketName=fsxn-demo-output-${ACCOUNT_ID}" \
  "NotificationEmail=you@example.com" \
  "OntapSecretArn="
```

### パス C: 本番デプロイ（パラメータファイル使用）

```bash
# 1. プリフライトチェック実行
./shared/scripts/preflight-check.sh --profile production

# 2. パラメータファイルを使用してデプロイ
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-legal-compliance \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --tags Key=Project,Value=fsxn-s3ap-serverless-patterns Key=UseCase,Value=legal-compliance

# 3. デプロイ監視
aws cloudformation wait stack-create-complete --stack-name fsxn-s3ap-legal-compliance
aws cloudformation describe-stack-events --stack-name fsxn-s3ap-legal-compliance \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED']"
```

### パス D: マルチパターンデプロイ（同一 VPC）

```bash
# 1. 最初のスタックを VPC Endpoints 付きでデプロイ
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-uc1 \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND

aws cloudformation wait stack-create-complete --stack-name fsxn-s3ap-uc1

# 2. 2 番目のスタックを VPC Endpoints なしでデプロイ（最初のスタックと共有）
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-sap \
  --template-body file://solutions/sap/erp-adjacent/template.yaml \
  --parameters file://cfn-params/sap-erp-adjacent.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND
```

### パス E: FPolicy イベント駆動（Tier 3）

PoC / Production / Compliance-sensitive プロファイルの詳細は [デプロイプロファイル](../deployment-profiles.md) を参照してください。

```bash
# 前提: ECR イメージのビルドとプッシュが完了していること
# コンテナビルド手順は solutions/event-driven/fpolicy/README.md を参照

aws cloudformation create-stack \
  --stack-name fsxn-fpolicy \
  --template-body file://solutions/event-driven/fpolicy/template.yaml \
  --parameters file://cfn-params/fpolicy-fargate.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

---

## コスト見積もり

### 固定費（スタックあたり、月額）

| コンポーネント | 費用 | 備考 |
|--------------|------|------|
| Interface VPC Endpoint（各） | 約 $7.20/月 | $0.01/時間 × AZ 数; 通常 2 AZ |
| S3 Gateway Endpoint | 無料 | 時間課金なし |
| NAT Gateway（必要な場合） | 約 $32/月 | VPC Lambda → Internet に必要 |
| EventBridge Scheduler | 約 $1/月 | 100 万回あたり $1 |
| CloudWatch Logs | 約 $0.50-5/月 | ログ量に依存 |

### 従量課金（実行あたり）

| コンポーネント | 費用 | 備考 |
|--------------|------|------|
| Lambda | 約 $0.0001-0.001/呼び出し | メモリと実行時間に依存 |
| Bedrock（Nova Lite） | 約 $0.00022/1K 入力トークン | テスト用の最安オプション |
| Bedrock（Nova Pro） | 約 $0.0008/1K 入力トークン | 本番推奨 |
| Step Functions | $0.025/1K 遷移 | Standard ワークフロー |
| S3 AP リクエスト | $0.0004/1K GET リクエスト | 標準 S3 料金 |

### 月額コスト（プロファイル別）

| プロファイル | VPC EP | コンピュート | AI/ML | 合計目安 |
|------------|--------|------------|-------|---------|
| DemoMode（FSx なし） | $0 | 約 $1 | 約 $2 | **約 $3/月** |
| 単一 UC（VPC EP 無効） | $0 | 約 $5 | 約 $10 | **約 $15/月** |
| 単一 UC（VPC EP 有効） | 約 $43 | 約 $5 | 約 $10 | **約 $58/月** |
| 複数 UC（VPC EP 共有） | 約 $43 | 約 $20 | 約 $40 | **約 $103/月** |
| FPolicy（Fargate） | 約 $43 | 約 $35 | 約 $10 | **約 $88/月** |

> これらの見積もりは、既にお使いの FSx for ONTAP インフラストラクチャのコストを除きます。

---

## デプロイ所要時間の目安

| スタックタイプ | `sam build` | `sam deploy` / `create-stack` | 合計 |
|--------------|-------------|-------------------------------|------|
| Tier 1（VPC 外部） | 30-60 秒 | 2-4 分 | **約 5 分** |
| Tier 2（VPC EP なし） | 30-60 秒 | 3-5 分 | **約 6 分** |
| Tier 2（VPC EP あり） | 30-60 秒 | 8-12 分 | **約 13 分** |
| Tier 3（FPolicy） | 1-2 分 | 10-15 分 | **約 17 分** |

Interface Endpoint の作成が主なボトルネックです（約 5-8 分）。

---

## Day 2 運用

### デプロイ直後の検証手順

```bash
# 1. スタックステータス確認
aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].StackStatus"

# 2. SNS サブスクリプション確認（確認メールのリンクをクリック）
aws sns list-subscriptions-by-topic --topic-arn <TOPIC-ARN>

# 3. テスト実行（Step Functions）
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)
aws stepfunctions start-execution --state-machine-arn "$STATE_MACHINE_ARN"

# 4. Lambda の ONTAP 接続確認（VPC パターン）
DISCOVERY_FN=$(aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].Outputs[?OutputKey=='DiscoveryFunctionArn'].OutputValue" --output text)
aws lambda invoke --function-name "$DISCOVERY_FN" /tmp/output.json
cat /tmp/output.json | jq .
```

### 監視メトリクス

| メトリクス | 名前空間 | アラーム閾値 |
|-----------|---------|------------|
| Lambda Errors | `AWS/Lambda` | 5 分間で > 0 |
| Lambda Duration | `AWS/Lambda` | タイムアウトの 80% 超過 |
| Step Functions ExecutionsFailed | `AWS/States` | 15 分間で > 0 |
| SQS ApproximateAgeOfOldestMessage | `AWS/SQS` | > 3600 秒（FPolicy） |
| Custom: FilesProcessed | `FSxN/S3AP` | 2 連続期間で = 0 |

### 月次レビューチェックリスト

- [ ] CloudWatch コストダッシュボード確認 — 予期しないスパイクはないか？
- [ ] Lambda 同時実行数の確認 — アカウント上限に近づいていないか？
- [ ] Bedrock モデル可用性の確認 — 非推奨通知はないか？
- [ ] S3 AP アクセスログの確認 — 不正アクセスの試行はないか？
- [ ] ONTAP シークレットローテーションの確認 — 認証情報が期限切れになっていないか？
- [ ] EventBridge Scheduler の確認 — 実行ミスはないか？
- [ ] SNS 配信失敗の確認 — バウンスメールはないか？
- [ ] VPC Endpoint ヘルス確認 — 接続拒否はないか？
- [ ] CloudTrail イベントの確認 — FSx や S3 AP リソースへの予期しない API 呼び出しはないか？

---

## ロールバック・クリーンアップ

### 失敗したデプロイのロールバック

```bash
# CloudFormation の自動ロールバック（デフォルト動作）
# ROLLBACK_FAILED でスタックしている場合:
aws cloudformation continue-update-rollback --stack-name <STACK-NAME>

# S3 バケットが空でないためロールバックが失敗する場合:
aws s3 rm s3://<BUCKET-NAME> --recursive
aws cloudformation delete-stack --stack-name <STACK-NAME>
```

### スタックの完全削除

```bash
# 1. スタックが作成した S3 バケットを空にする
BUCKETS=$(aws cloudformation describe-stack-resources --stack-name <STACK-NAME> \
  --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text)
for bucket in $BUCKETS; do
  aws s3 rm "s3://$bucket" --recursive
done

# 2. スタック削除
aws cloudformation delete-stack --stack-name <STACK-NAME>
aws cloudformation wait stack-delete-complete --stack-name <STACK-NAME>

# 3. 孤立リソースがないことを確認
aws cloudformation list-stacks --stack-status-filter DELETE_FAILED \
  --query "StackSummaries[?contains(StackName,'fsxn')]"
```

### マルチスタックデプロイのクリーンアップ順序

デプロイの逆順でスタックを削除します：
1. アプリケーションスタック（UC パターン、FPolicy コンシューマ）
2. FPolicy Event-Driven スタック（デプロイ済みの場合）
3. VPC Endpoints を所有するスタック（最後 — 他のスタックが依存）

> S3 Access Point 自体はこれらのスタックで管理されていません。スタックを削除しても S3 AP や FSx for ONTAP のデータには影響しません。

---

## ONTAP バージョン要件

| 機能 | 最小 ONTAP バージョン | 影響パターン |
|------|---------------------|------------|
| S3 Access Points | 9.14.1 | 全パターン |
| FPolicy Persistent Store | 9.14.1 | event-driven/fpolicy |
| FPolicy mandatory モード | 9.15.1 | event-driven/fpolicy（Production プロファイル） |
| FlexCache with S3 AP | 9.14.1 | flexcache/* |
| S3 AP と NFS/SMB の共存 | 9.14.1 | 全パターン |
| SnapMirror with S3 AP volumes | 9.14.1 | DR シナリオ |

### ONTAP バージョンの確認方法

```bash
# ONTAP REST API 経由
curl -sku admin:PASSWORD "https://<MANAGEMENT-IP>/api/cluster?fields=version" | jq '.version'

# AWS CLI 経由
aws fsx describe-file-systems --file-system-ids fs-XXXXXXXXX \
  --query "FileSystems[0].OntapConfiguration.OntapVersion" --output text
```

### 既知の制約事項

- **S3 AP NetworkOrigin は変更不可** — 作成後に Internet から VPC、またはその逆に変更できません。
- **ONTAP S3 サーバーと S3 AP の競合** — SVM に ONTAP ネイティブの S3 サーバー（`vserver object-store-server`）が有効な場合、S3 Access Point の作成が失敗します。別の SVM を使用するか、S3 サーバーを先に削除してください。
- **S3 AP は Presigned URL をサポートしない** — 非サポートとして文書化されています。
- **PutObject の最大オブジェクトサイズは 5 GB** — より大きなファイルには Multipart Upload を使用してください。
- **S3 Gateway VPC Endpoint は Internet-origin S3 AP トラフィックをルーティングしない** — NAT Gateway または VPC 外部 Lambda を使用してください。

---

## トラブルシューティング

### よくあるデプロイエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| `Parameter S3AccessPointAlias failed regex` | エイリアスが `^[a-z0-9-]+-ext-s3alias$` に一致しない | `aws s3control list-access-points` でエイリアスを確認; `-ext-s3alias` で終わるか確認 |
| `VpcEndpoint already exists` | 別のスタックまたは手動作成が既にエンドポイントを所有 | `EnableVpcEndpoints=false` と `EnableS3GatewayEndpoint=false` に設定 |
| `Unable to assume role` | Lambda 実行ロールがまだ伝搬していない | 30 秒待って再試行; IAM ロール伝搬に最大 10 秒かかる場合がある |
| `Network timeout` (ONTAP 接続) | VPC 内 Lambda が ONTAP 管理 LIF に到達できない | SG がポート 443 のエグレスを許可しているか確認; ONTAP 管理 IP がプライベートサブネットから到達可能か確認 |
| `Access Denied` (S3 AP 操作) | IAM ポリシーまたは S3 AP リソースポリシーの不一致 | IAM アイデンティティポリシーと S3 AP リソースポリシーの両方がアクションを許可しているか確認 |
| `Secret not found` | シークレット名のタイポまたはリージョン間違い | `aws secretsmanager describe-secret --secret-id <NAME>` で確認 |
| `ONTAP S3 server exists on SVM` | ONTAP ネイティブ S3 が FSx S3 AP と競合 | 別の SVM を使用するか、ONTAP S3 サーバーを削除（既知の制約事項を参照） |
| `Bedrock InvokeModel AccessDenied` | リージョンでモデルアクセスが有効化されていない | Bedrock コンソールでモデルアクセスを有効化; クロスリージョン推論プロファイル ID を使用 |

### 接続のデバッグ

```bash
# Lambda が ONTAP 管理 IP に到達できるかテスト（ローカルマシンから）
curl -sk "https://<MANAGEMENT-IP>/api/cluster" --connect-timeout 5

# Lambda VPC 設定の確認
aws lambda get-function-configuration --function-name <FUNCTION-NAME> \
  --query "VpcConfig.{SubnetIds:SubnetIds,SecurityGroupIds:SecurityGroupIds}"

# Security Group エグレスルールの確認
aws ec2 describe-security-groups --group-ids <SG-ID> \
  --query "SecurityGroups[0].IpPermissionsEgress"
```

---

## CI/CD 統合

### GitHub Actions 例

```yaml
# .github/workflows/deploy.yml
name: Deploy Pattern
on:
  push:
    branches: [main]
    paths: ['solutions/industry/legal-compliance/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/GitHubActions-Deploy
          aws-region: ap-northeast-1

      - name: Setup SAM CLI
        uses: aws-actions/setup-sam@v2

      - name: Preflight check
        run: ./shared/scripts/preflight-check.sh --profile production --vpc ${{ vars.VPC_ID }}
        env:
          ONTAP_SECRET_NAME: ${{ vars.ONTAP_SECRET_NAME }}

      - name: SAM Build & Deploy
        run: |
          cd solutions/industry/legal-compliance
          sam build
          sam deploy --no-confirm-changeset --no-fail-on-empty-changeset \
            --parameter-overrides $(cat ../../../cfn-params/uc1-legal-compliance.json | jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' | tr '\n' ' ')
```

### 本番更新にはチェンジセットを使用

既にデプロイ済みのスタックを更新する場合は、`create-stack` ではなくチェンジセットを使用します：

```bash
# チェンジセット作成（適用前に変更をプレビュー）
aws cloudformation create-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --change-set-name update-$(date +%Y%m%d-%H%M%S)

# チェンジセットの確認
aws cloudformation describe-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --change-set-name update-XXXXXXXX

# チェンジセットの実行（適用）
aws cloudformation execute-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --change-set-name update-XXXXXXXX
```

---

## 関連ドキュメント

- [デモモードガイド](../demo-mode-guide.md) — FSx for ONTAP なしでパターンを実行
- [コスト計算](../cost-calculator.md) — 詳細なコスト見積もり
- [S3 AP 互換性ノート](../s3ap-compatibility-notes.md) — 既知の制約とワークアラウンド
- [デプロイプロファイル（FPolicy）](../deployment-profiles.md) — PoC / Production / Compliance プロファイル
- [パターン選択ガイド](../pattern-selection-guide.md) — ユースケースに適したパターンの選択
- [ONTAP 統合ノート](../ontap-integration-notes.md) — NAS 共存とアイデンティティ
- [プリフライトチェックスクリプト](../../shared/scripts/preflight-check.sh) — デプロイ前の自動検証
- [サンプルパラメータファイル](../../cfn-params/) — CloudFormation パラメータの使用例
