# Getting Started — FSx for ONTAP File Portal

> 30 分で動作確認可能。DemoMode なら FSx for ONTAP なしで始められます。

## 前提条件

| 項目 | 必須 | 備考 |
|------|:---:|------|
| AWS アカウント | ✅ | Amplify sandbox 用。Cognito/AppSync/Lambda は Free Tier 内 |
| Node.js 18+ | ✅ | `node --version` で確認 |
| AWS CLI v2 | ✅ | `aws --version` で確認 |
| FSx for ONTAP ファイルシステム | — | DemoMode なら不要。admin 機能を使う場合に必要 |

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

## フルセットアップ（FSx for ONTAP 接続あり）

### Step 1: 前提条件の確認

```bash
# FSx for ONTAP のファイルシステム ID を指定して自動検出
./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0
```

出力される値をメモしてください（VPC ID, サブネット, SG, 管理 IP, SVM 名）。

### Step 2: Secrets Manager にクレデンシャルを登録

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD_HERE"}'
```

> fsxadmin のパスワードは FSx for ONTAP 作成時に設定したもの。
> 変更: `aws fsx update-file-system --file-system-id <id> --ontap-configuration '{"FsxAdminPassword":"NewPassword"}'`

### Step 3: portal-config.ts を編集

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

### Step 4: 起動

```bash
npm start
```

初回は CloudFormation スタック作成のため 3-5 分かかります。
`Deployment completed` + `http://localhost:5173` が表示されたら完了。

### Step 5: 動作確認

1. **ファイルブラウズ**: Browse > All Files にフォルダが表示される
2. **SMB 共有**: Admin > Resources > SMB 共有 に共有一覧が表示される
3. **Lock パネル**: Data Protection > Lock でタブが表示される
4. **ARP/AI**: Data Protection > ARP/AI でボリュームの保護状態が表示される

## 既存の SaaS ツールを使っている方へ

| 現在の環境 | このポータルの使い方 |
|-----------|-------------------|
| Box / Google Drive / SharePoint | 日常のファイル共有はそのまま。NAS 上のデータ（CAD、EDA ログ等）への AI 処理のみ本ポータルを併用 |
| Nextcloud を運用中 | External Storage で S3 AP を追加接続するだけ（本リポジトリにセットアップガイドあり） |
| Egnyte / Citrix ShareFile | FSx for ONTAP への SnapMirror 連携 + S3 AP で AI 処理レイヤーを追加 |

**本ポータルは既存ツールの置き換えではありません。** NAS データへの AI 処理・監査証跡・データ保護の可視化レイヤーとして追加するアプローチです。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `ONTAP connection not configured` | VPC/ONTAP 設定が空 | portal-config.ts に VPC + ONTAP 値を設定 |
| `Execution timed out` (admin 操作) | Secrets Manager VPC Endpoint がない | VPC に `com.amazonaws.<region>.secretsmanager` Interface Endpoint を追加 |
| `Unknown action: xxx` | Lambda コードが古い | sandbox を Ctrl+C → `npm start` で再起動 |
| S3 Object Lock 「未設定」 | S3 Gateway Endpoint のルートテーブルに Lambda サブネットが含まれていない | `aws ec2 modify-vpc-endpoint --add-route-table-ids <rtb-id>` |
| `CDK Assembly Error` | cdk-nag が走っている（通常は CI-only） | `.amplify/artifacts` を削除して再起動 |

## 環境削除

```bash
# sandbox 環境を完全削除（CloudFormation スタック + 全リソース）
npx ampx sandbox delete

# S3 Object Lock テストバケットも削除する場合
aws s3 rb s3://fsxn-portal-objectlock-demo --force
```

## 次のステップ

- [Admin Resource Management Demo Guide](../../docs/en/admin-resource-management-demo.md) — 全管理機能の操作手順
- [DemoMode Guide](../../docs/demo-mode-guide.md) — FSx for ONTAP なしでの検証方法
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — 設計意図と変更履歴
- [認可モデル](../../docs/ja/portal-authorization-model.md) — Cognito グループによるアクセス制御
