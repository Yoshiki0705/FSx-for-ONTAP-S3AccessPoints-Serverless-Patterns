# FSx for ONTAP — PowerShell Toolkit Automation Environment

> 初心者でもパラメータ選択だけで、FSx for ONTAP の管理自動化環境をデプロイできる CloudFormation テンプレート

---

## 🚀 はじめる (Get Started)

| ステップ | 所要時間 | 内容 |
|---------|---------|------|
| 1. 前提準備 | 5分 | Secrets Manager にfsxadmin資格情報を保存 |
| 2. デプロイ | 10-15分 | CloudFormation でスタック作成 |
| 3. 接続確認 | 2分 | EC2 or Lambda 経由で FSx for ONTAP に接続 |

### 前提条件

- FSx for ONTAP ファイルシステムがデプロイ済み
- fsxadmin のパスワードが Secrets Manager に保存済み
- VPC 内の Private Subnet に EC2/Lambda を配置可能

### Secrets Manager の準備

```bash
aws secretsmanager create-secret \
  --name fsxn-admin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD_HERE"}'
```

### デプロイ

```bash
# EC2 モード (RDP でログインして PSTK を対話的に使用)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pstk-automation \
  --parameter-overrides \
    ExecutionMode=EC2 \
    VpcId=vpc-xxxx \
    SubnetId=subnet-xxxx \
    FsxMgmtEndpointIp=10.0.1.100 \
    SvmName=svm1 \
    FsxAdminSecretArn=arn:aws:secretsmanager:... \
  --capabilities CAPABILITY_NAMED_IAM

# Lambda モード (API 経由で自動化)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pstk-automation \
  --parameter-overrides \
    ExecutionMode=Lambda \
    VpcId=vpc-xxxx \
    SubnetId=subnet-xxxx \
    FsxMgmtEndpointIp=10.0.1.100 \
    SvmName=svm1 \
    FsxAdminSecretArn=arn:aws:secretsmanager:... \
    EnableApiGateway=true \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## 📂 ディレクトリ構成

```
infrastructure/pstk-automation/
├── template.yaml                  # CloudFormation/SAM テンプレート
├── README.md                      # このファイル
├── samconfig.toml.example         # SAM デプロイ設定例
├── functions/
│   └── ontap-actions/
│       └── handler.ps1            # Lambda PowerShell ハンドラー
├── scripts/
│   └── build-lambda-layer.sh      # Lambda Layer ビルドスクリプト
├── layers/                        # ビルド済み Layer 出力先
└── docs/
    ├── pstk-action-catalog.md     # PSTK 操作カタログ（全アクション一覧）
    └── amplify-portal-integration.md  # Amplify Portal 統合設計
```

---

## ⚙️ パラメータ一覧

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|:----:|-----------|------|
| `ExecutionMode` | ✅ | Lambda | `EC2` / `Lambda` / `Both` |
| `VpcId` | ✅ | — | FSx for ONTAP が存在する VPC |
| `SubnetId` | ✅ | — | FSx 管理エンドポイントに到達可能なサブネット |
| `FsxMgmtEndpointIp` | ✅ | — | ファイルシステム管理 IP |
| `SvmName` | | svm1 | 対象 SVM 名 |
| `FsxAdminSecretArn` | ✅ | — | Secrets Manager ARN |
| `Ec2InstanceType` | | t3.medium | EC2 モード時のインスタンスタイプ |
| `Ec2KeyPairName` | | — | RDP 用キーペア（オプション） |
| `EnableApiGateway` | | true | API Gateway デプロイ (Lambda モード) |

---

## 🔧 利用可能なアクション

詳細は [docs/pstk-action-catalog.md](docs/pstk-action-catalog.md) を参照。

<details>
<summary>主要アクション一覧 (クリックで展開)</summary>

| カテゴリ | アクション | Lambda API | EC2 PSTK |
|---------|----------|:----------:|:--------:|
| CIFS 共有 | 一覧取得 | `GET /shares` | `Get-NcCifsShare` |
| CIFS 共有 | 作成 | `POST /shares` | `Add-NcCifsShare` |
| CIFS 共有 | ACL 設定 | (included in POST) | `Add-NcCifsShareAcl` |
| ローカルユーザ | 一覧取得 | `GET /users` | `Get-NcCifsLocalUser` |
| ローカルユーザ | 作成 | `POST /users` | `New-NcCifsLocalUser` |
| ボリューム | 情報取得 | `GET /volumes` | `Get-NcVol` |
| スナップショット | 一覧取得 | `GET /snapshots` | `Get-NcSnapshot` |
| スナップショット | 作成 | `POST /snapshots` | `New-NcSnapshot` |
| SVM | ステータス | `GET /status` | `Get-NcVserver` |

</details>

---

## 🖥️ EC2 モードの使い方

デプロイ後、SSM Session Manager で接続:

```bash
aws ssm start-session --target <instance-id>
```

または RDP で接続（キーペア指定時）。

EC2 上には以下が自動設定済み:
- PowerShell 7.x
- NetApp.ONTAP モジュール
- 接続テストスクリプト (`C:\test-fsx-connection.ps1`)
- 設定ファイル (`C:\ontap-automation\config.json`)

---

## 🌐 Lambda モード + Amplify Portal

Lambda モードでは API Gateway 経由で FSx for ONTAP を操作可能。
Amplify Portal (`solutions/amplify-portal/`) に統合して Web UI から操作できます。

詳細: [docs/amplify-portal-integration.md](docs/amplify-portal-integration.md)

---

## 📚 関連ドキュメント

- [PSTK 操作カタログ](docs/pstk-action-catalog.md)
- [Amplify Portal 統合設計](docs/amplify-portal-integration.md)
- [NetApp PSTK 公式ドキュメント](https://docs.netapp.com/us-en/ontap-automation/pstk/learn-about-pstk.html)
- [Classmethod — PSTK で共有移行](https://dev.classmethod.jp/articles/amazon-fsx-for-netapp-ontap-migrate-multiple-file-share-settings-with-netapp-ontap-powershell-toolkit/)
- [AWS Lambda PowerShell Custom Runtime](https://github.com/awslabs/aws-lambda-powershell-runtime)
