# Getting Started — FSx for ONTAP File Portal

> 30 分で動作確認可能。DemoMode なら FSx for ONTAP なしで始められます。

## 前提条件

| 項目 | 必須 | バージョン | 確認コマンド |
|------|:---:|---------|----------|
| AWS アカウント | ✅ | — | Free Tier で可。IAM ユーザーまたは SSO で認証済み |
| Node.js | ✅ | 20.x 以上 | `node --version` |
| npm | ✅ | 10.x 以上 | `npm --version` |
| AWS CLI | ✅ | 2.x | `aws --version` |
| Amplify CLI | ✅ | 最新版 | `npx ampx --version` |
| FSx for ONTAP | — | ONTAP 9.15+ | DemoMode なら不要。admin 機能に必要 |
| Docker | — | 24.x 以上 | `docker --version`（Nextcloud 利用時のみ） |

> **検証環境**: 本ガイドは Node.js 20.18.x / Amplify Gen2 1.x / Python 3.12 (Lambda) / ONTAP 9.17.1 / ap-northeast-1 で検証しています。

## クイックスタート（DemoMode — FSx for ONTAP なし）

```bash
# 1. リポジトリをクローン
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. 依存関係インストール
npm install

# 3. 設定ファイル作成（DemoMode: VPC/ONTAP は空のまま）
cp amplify/portal-config.example.ts amplify/portal-config.ts

# 4. 起動（sandbox + dev server が同時に起動）
npm start
```

ブラウザで `http://localhost:5173` を開き、Cognito でユーザー登録 → サインイン。
ファイルブラウズ・AI 処理・アップロードは DemoMode で動作します。
admin/data-protection 機能は「ONTAP 接続が必要」と表示されます。

> **エンドユーザー向け**: デプロイ完了後、ポータルを使い始めるユーザーには [ユーザーガイド](../../docs/ja/portal-user-guide.md)（[EN](../../docs/en/portal-user-guide.md)）を案内してください。デプロイ手順の知識は不要で、日常操作だけをカバーしています。

## フルセットアップ（FSx for ONTAP 接続あり）

### Step 1: 前提条件の確認

```bash
# FSx for ONTAP のファイルシステム ID を指定して自動検出
./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0
```

出力される値をメモしてください（VPC ID, サブネット, SG, 管理 IP, SVM 名）。

### Step 2: VPC Endpoint の確認（必須）

VPC 内の Lambda が AWS サービスにアクセスするには、以下の VPC Endpoint が必要です:

| Endpoint | タイプ | 用途 |
|----------|--------|------|
| `com.amazonaws.<region>.s3` | Gateway | S3 API (Object Lock, ファイル操作) |
| `com.amazonaws.<region>.secretsmanager` | Interface | ONTAP クレデンシャル取得 |

```bash
# S3 Gateway Endpoint の確認（通常はデフォルト VPC に存在）
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.s3" \
  --query "VpcEndpoints[0].{Id:VpcEndpointId,RouteTables:RouteTableIds}"

# Lambda サブネットのルートテーブルが含まれているか確認
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[0].RouteTableId"

# 含まれていない場合は追加
aws ec2 modify-vpc-endpoint --vpc-endpoint-id <vpce-id> --add-route-table-ids <rtb-id>

# Secrets Manager Interface Endpoint がない場合は作成
aws ec2 create-vpc-endpoint \
  --vpc-id <vpc-id> \
  --service-name com.amazonaws.<region>.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids <subnet-id> \
  --security-group-ids <sg-id>
```

> **Security note**: S3 Gateway Endpoint のルートテーブルに Lambda のサブネットが含まれていないと、S3 API 呼び出し（Object Lock 確認等）がタイムアウトします。

### Step 3: Secrets Manager にクレデンシャルを登録

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD_HERE"}'
```

> fsxadmin のパスワードは FSx for ONTAP 作成時に設定したもの。
> 変更: `aws fsx update-file-system --file-system-id <id> --ontap-configuration '{"FsxAdminPassword":"NewPassword"}'`

### Step 4: portal-config.ts を編集

```bash
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

Step 1 で取得した値を入力:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",  // FSx for ONTAP のリージョン
  s3ApAlias: "your-s3ap-alias-xxx-s3alias",  // FSx Console > S3 Access Points タブ

  // VPC (admin/data-protection 機能に必須)
  vpcId: "vpc-0123456789abcdef0",
  vpcSubnetIds: ["subnet-0123456789abcdef0"],
  vpcSecurityGroupIds: ["sg-0123456789abcdef0"],

  // ONTAP 接続
  ontapMgmtIp: "172.30.x.x",  // management LIF IP
  ontapSecretName: "fsx-ontap-fsxadmin-credentials",
  ontapSvmName: "svm1",
  ontapVolumeName: "vol1",

  // ... 他はデフォルトのまま
};
```

### Step 5: 起動

```bash
npm start
```

初回は CloudFormation スタック作成のため 3-5 分かかります。
`Deployment completed` + `http://localhost:5173` が表示されたら完了。

### Step 6: 動作確認

1. **ファイルブラウズ**: Browse > All Files にフォルダが表示される
2. **SMB 共有**: Admin > Resources > SMB 共有 に共有一覧が表示される
3. **Lock パネル**: Data Protection > Lock でタブが表示される
4. **ARP/AI**: Data Protection > ARP/AI でボリュームの保護状態が表示される

## 既存の SaaS ツールを使っている方へ

| 現在の環境 | このポータルの使い方 |
|-----------|-------------------|
| Box / Google Drive / SharePoint | 日常のファイル共有はそのまま。NAS 上のデータへの AI 処理・監査証跡・データ保護の可視化のみ本ポータルを併用 |
| Nextcloud を運用中 | External Storage で S3 AP を追加接続するだけ（本リポジトリにセットアップガイドあり） |
| Egnyte / Citrix ShareFile | FSx for ONTAP への SnapMirror 連携 + S3 AP で AI 処理レイヤーを追加 |

**業界別の利用例**:
- **金融**: トレーディングログの異常検知 + FISC 7年監査証跡
- **製造**: CAD/EDA ファイルの AI 品質検査
- **医療**: DICOM 画像の AI 診断支援 + HIPAA 保持管理
- **メディア**: 映像素材の AI メタデータ自動タグ付け
- **法務**: 契約書 PDF の AI 分類 + 期限管理可視化
- **研究**: ゲノム/シミュレーション結果のブラウザ検索

**本ポータルは既存ツールの置き換えではありません。** NAS データへの AI 処理・監査証跡・データ保護の可視化レイヤーとして追加するアプローチです。

### ファイルサーバーだけで運用している場合

NFS/SMB ファイルサーバーを「そのまま」運用している場合、SaaS が提供するブラウザアクセス・ファイル検索・共有リンク・バージョン管理・監査証跡・AI 分類といった体験を享受できていません。本ポータルは**データ移動なし**でこれらの SaaS 相当の体験を NAS データに追加します:

| SaaS が提供する体験 | 本ポータルでの実現 |
|---|---|
| ブラウザからのアクセス（VPN 不要） | S3 AP + Cognito 認証（Internet-origin） |
| 自然言語ファイル検索 | Bedrock Knowledge Base セマンティック検索 |
| 共有リンク（期限付き） | Presigned URL + QR コード |
| バージョン管理・ワンクリック復元 | Snapshot UI + FlexClone |
| 監査証跡を UI で確認 | CloudTrail + Athena セルフサービス |
| AI 自動分類・タグ付け | Bedrock + Step Functions ワンクリック |
| ランサムウェア対策の可視化 | ARP/AI ダッシュボード |

既存の NFS/SMB ワークフローには影響しません。S3 AP は同じボリュームへの追加アクセスパスです。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `ONTAP connection not configured` | VPC/ONTAP 設定が空 | portal-config.ts に VPC + ONTAP 値を設定 |
| `Execution timed out` (admin 操作) | Secrets Manager VPC Endpoint がない | VPC に `com.amazonaws.<region>.secretsmanager` Interface Endpoint を追加 |
| `Unknown action: xxx` | Lambda コードが古い | sandbox を Ctrl+C → `npm start` で再起動 |
| S3 Object Lock 「未設定」 | S3 Gateway Endpoint のルートテーブルに Lambda サブネットが含まれていない | `aws ec2 modify-vpc-endpoint --add-route-table-ids <rtb-id>` |
| `CDK Assembly Error` | cdk-nag が走っている（通常は CI-only） | `.amplify/artifacts` を削除して再起動 |

## 本番移行チェックリスト

DemoMode/sandbox で検証後、本番に持っていく際の確認項目:

| # | 項目 | 対応 |
|---|------|------|
| 1 | IAM 最小権限化 | `resources: ["*"]` を具体的な ARN に制限。portal-config.ts のコメント参照 |
| 2 | Lambda Security Group 分離 | FSx SG を共用せず、Lambda 専用 SG を作成。Outbound: TCP/443 (ONTAP mgmt LIF IP + VPC Endpoint) のみ |
| 3 | Cognito 本番設定 | MFA 必須化、パスワードポリシー強化、External IdP (SAML/OIDC) 連携 |
| 4 | ログ保持期間 | `LogRetentionInDays` を規制要件に合わせて設定 (FISC: 2557日/7年, SOX: 1825日/5年) |
| 5 | CloudTrail 有効化 | S3 AP ARN に対する Data Event + Management Event を有効化 |
| 6 | Amplify Hosting | `amplify deploy` で本番 CloudFront + カスタムドメイン |
| 7 | WAF 追加 | AppSync に AWS WAF を追加（レート制限、IP フィルタ） |
| 8 | Bedrock data residency | 使用モデルの推論リージョンを確認。ap-northeast-1 の Nova/Claude は同リージョンで推論（cross-region 送信なし） |
| 9 | cdk-nag 有効化 | CI で `CDK_NAG=1` を設定し、新たな違反を検出 |
| 10 | Provisioned Concurrency | VPC Lambda の Cold Start を 1-2 秒に短縮 (オプション) |
| 11 | GraphQL Introspection 無効化 | AppSync Console → Settings → Introspection: OFF（スキーマ情報漏洩防止） |
| 12 | CloudWatch アラーム | VPC Lambda p99 レイテンシ > 5s のアラームを設定。Provisioned Concurrency 検討トリガーに |
| 13 | Free Tier 終了後のコスト見積 | AppSync: ~$4/100万リクエスト、Cognito: $0.0055/MAU、Lambda: $0.20/100万呼出。月額目安: $25-60 (利用頻度による) |

> **Security note**: 本番では Lambda の Security Group を FSx SG から分離してください。FSx SG は全ポート open（intra-VPC 通信用）ですが、Lambda は TCP/443 outbound のみで十分です。

> **Data residency note**: Amazon Bedrock の On-Demand モデル (Nova, Claude) は、呼び出し元と同じリージョンで推論を実行します。ap-northeast-1 から呼び出した場合、データは ap-northeast-1 内に留まります。Cross-Region Inference を使用する場合はデータが他リージョンに送信される可能性があるため、規制要件に応じて `bedrock:InferenceProfile` の ARN を制限してください。

## 環境削除

```bash
# sandbox 環境を完全削除（CloudFormation スタック + 全リソース）
npx ampx sandbox delete

# S3 Object Lock テストバケットも削除する場合
aws s3 rb s3://fsxn-portal-objectlock-demo --force
```

## 次のステップ

- [PoC → 本番移行ガイド](../../docs/ja/portal-poc-to-production.md) — DemoMode から本番接続への移行チェックリスト
- [スケーリングガイド](../../docs/ja/portal-scaling-guide.md) — キャパシティプランニングとスループット管理
- [アクセシビリティ](../../docs/en/portal-accessibility.md) — キーボードナビゲーション、ARIA、スクリーンリーダー対応
- [Admin Resource Management Demo Guide](../../docs/en/admin-resource-management-demo.md) — 全管理機能の操作手順
- [AI Agent Demo Guide](./ai-agent-demo-guide.md) — AI エージェント機能の E2E デモ
- [DemoMode Guide](../../docs/demo-mode-guide.md) — FSx for ONTAP なしでの検証方法
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — 設計意図と変更履歴
- [認可モデル](../../docs/ja/portal-authorization-model.md) — Cognito グループによるアクセス制御
