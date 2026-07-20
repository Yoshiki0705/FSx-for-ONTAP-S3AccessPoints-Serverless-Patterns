# ファイルポータル デプロイ運用手順書

> 🌐 言語: **日本語** | [English](../en/portal-deployment-runbook.md)

FSx for ONTAP ファイルポータルのデプロイ・更新・削除の運用手順書。2026-07-20 の検証で得た知見を反映。

---

## 前提条件チェックリスト

| 要件 | 確認コマンド | 備考 |
|------|------------|------|
| AWS CLI v2 | `aws --version` | 認証情報設定済み |
| Node.js 18.17+ | `node --version` | Amplify Gen2 CDK に必要 |
| AWS アカウント | `aws sts get-caller-identity` | Account ID を控える |
| FSx for ONTAP | `aws fsx describe-file-systems` | ONTAP 9.14.1+ 推奨 |
| S3 AP (Internet-origin) | 下記 Step 1 参照 | DemoMode なら通常 S3 バケットでも可 |

---

## Step 1: S3 Access Point 作成

```bash
# ボリューム ID を確認
aws fsx describe-volumes \
  --query 'Volumes[?OntapConfiguration.JunctionPath!=`null`].{Name:Name,Id:VolumeId,Path:OntapConfiguration.JunctionPath}' \
  --output table

# S3 AP 作成パラメータ
cat > /tmp/create-s3ap.json << 'EOF'
{
  "Name": "portal-demo",
  "Type": "ONTAP",
  "OntapConfiguration": {
    "VolumeId": "<YOUR_VOLUME_ID>",
    "FileSystemIdentity": {
      "Type": "UNIX",
      "UnixUser": { "Name": "root" }
    }
  }
}
EOF

aws fsx create-and-attach-s3-access-point \
  --cli-input-json file:///tmp/create-s3ap.json \
  --region ap-northeast-1
```

> **検証で得た知見**: API は `Name` + `Type` + `OntapConfiguration.VolumeId` を必要とします（FileSystemId や JunctionPath ではない）。S3 AP alias はレスポンスで返されます。作成から AVAILABLE まで 1-3 分。

---

## Step 2: ポータル設定

```bash
cd solutions/amplify-portal
make install
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

**portal-config.ts** を編集:
- `region`: FSx for ONTAP のリージョン
- `s3ApAlias`: Step 1 で取得した alias

**src/portal-settings.ts** を編集:
- `region`: 同上
- `accountId`: AWS アカウント ID
- `s3ApAlias`: 同じ alias

> **検証で得た知見**: 2 つのファイルに同じ alias を設定する必要があります。片方だけだと Files タブは動くが Upload タブが AccessDenied になります。

---

## Step 3: サンドボックスデプロイ

```bash
make sandbox
```

初回: ~5 分、以降: ~30-90 秒（差分更新）

---

## Step 4: テストユーザー作成

```bash
USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "demo@example.com" \
  --temporary-password "TempPass1!" \
  --user-attributes Name=email,Value=demo@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "demo@example.com" \
  --password "Demo1234!" --permanent
```

---

## Step 5: 動作確認

```bash
make dev
# → http://localhost:5173 でブラウザアクセス
```

---

## Step 6: 本番デプロイ (Amplify Hosting)

```bash
npx vite build
aws amplify create-app --name "your-portal" --region ap-northeast-1
aws amplify create-branch --app-id <APP_ID> --branch-name main
aws amplify create-deployment --app-id <APP_ID> --branch-name main
cd dist && zip -r /tmp/deploy.zip .
curl -T /tmp/deploy.zip "<zipUploadUrl>"
aws amplify start-deployment --app-id <APP_ID> --branch-name main --job-id <JOB_ID>
# → https://main.<APP_ID>.amplifyapp.com
```

---

## 削除手順 (完全クリーンアップ)

```bash
# 1. Amplify Hosting (デプロイした場合)
aws amplify delete-app --app-id <APP_ID> --region ap-northeast-1

# 2. サンドボックス (全バックエンドリソース)
make sandbox-delete

# 3. S3 Access Point
aws fsx detach-and-delete-s3-access-point --name portal-demo --region ap-northeast-1

# 4. 残存確認
aws cloudformation describe-stacks \
  --query 'Stacks[?contains(StackName, `amplify-fsxn`)].StackName' --output text
# 期待: 空
```

> **知見**: sandbox-delete は全リソースを完全削除。部分削除は不可。

---

## トラブルシューティング

| 症状 | 原因 | 対応 |
|------|------|------|
| Files タブ "No files" | s3ApAlias 未設定 | portal-config.ts に設定 → `make sandbox` |
| Upload タブ AccessDenied | portal-settings.ts 未設定 | alias + accountId 設定 → リロード |
| Process タブ赤バナー | SFn ARN がプレースホルダー | `make sfn-test-create` |
| ログイン失敗 | ユーザー未作成 | Step 4 実行 |
| sandbox 失敗 "Cannot find module" | portal-config.ts がない | `cp portal-config.example.ts portal-config.ts` |

---

## コスト

| リソース | サンドボックス (アイドル) | 本番 (100 ユーザー) |
|----------|:---:|:---:|
| Cognito | $0 | $0 |
| AppSync | $0 | ~$4/月 |
| Lambda | $0 | ~$3/月 |
| DynamoDB | $0 | ~$1/月 |
| Amplify Hosting | — | ~$5/月 |
| **ポータル合計** | **$0** | **~$13/月** |

> FSx for ONTAP インフラコスト (~$194/月〜) は別途。ポータルの追加コストは月 $13 程度。

---

## 設定パラメータ一覧

| パラメータ | ファイル | 用途 |
|-----------|--------|------|
| `s3ApAlias` | portal-config.ts | バックエンド Lambda のファイルアクセス |
| `s3ApAlias` | portal-settings.ts | フロントエンド Storage Browser |
| `accountId` | portal-settings.ts | Storage Browser (クライアントサイド S3 呼び出し) |
| `region` | 両ファイル | FSx for ONTAP リージョンと一致させる |
| `stateMachineArn` | portal-config.ts + start-processing.js | Process タブのワークフロー起動 |
| `groupApMapping` | portal-config.ts | チームごとのファイル分離 (My Files) |
| `bedrockKbId` | portal-config.ts | 全文セマンティック検索 |
