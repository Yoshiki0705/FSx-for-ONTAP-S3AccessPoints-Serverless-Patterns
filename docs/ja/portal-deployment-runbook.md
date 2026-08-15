# ファイルポータル デプロイ運用手順書

> 🌐 **Language / 言語**: 日本語 | [English](../en/portal-deployment-runbook.md)

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

`amplify/portal-config.ts` を編集:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",                              // FSx for ONTAP のリージョン
  s3ApAlias: "portal-demo-xxx-ext-s3alias",             // Step 1 で取得
  stateMachineArn: "arn:aws:states:...:placeholder",    // または実際の UC パターンの ARN
  stateMachineResourceScope: "*",                        // 本番では絞る
  s3ApResourceArns: [
    "arn:aws:s3:*:*:accesspoint/*",
    "arn:aws:s3:*:*:accesspoint/*/object/*",
  ],
  groupApMapping: {},                                    // 空 = 全ユーザーが同じ AP を共有
  bedrockKbId: "",                                       // 空 = 検索無効
};
```

`src/portal-settings.ts` は UI の機能スイッチだけを持ちます:

```typescript
export const portalSettings = {
  processingEnabled: false,       // SFn ARN 設定後に true
  aiAgentEnabled: false,          // Bedrock KB は課金が継続するため既定 false
};
```

> **検証で得た知見**: S3 AP alias を書く場所は `amplify/portal-config.ts` の 1 か所だけです。以前は `src/portal-settings.ts` にも同じ alias が必要で、こちらはコミット対象だったためプレースホルダーのまま出荷され、Upload タブが存在しない Access Point に対して全件失敗していました。現在は `amplify/backend.ts` が `backend.addOutput({ custom: ... })` で `amplify_outputs.json` に書き出し、ブラウザはそれを読みます。

---

## Step 3: サンドボックスデプロイ

```bash
make sandbox
```

**初回**: 約 5 分（CDK bootstrap + スタック全体の作成）
**以降**: 約 30-90 秒（差分更新）

**作成されるもの**:
- Cognito User Pool + Identity Pool
- AppSync GraphQL API（20 以上の resolver）
- 10 以上の Lambda 関数（Python 3.13、ARM64）
- 6 つの DynamoDB テーブル（JobExecution, FileNotification, Favorite, FileTag, FolderWatch, RecentFile）
- IAM ロール（Lambda ごとに最小権限）

> **検証で得た知見**: 全リソースが同一の CDK スタックに入ります。スタックをまたぐ参照は resolver のバインドに失敗します。

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
# → http://localhost:5173
```

本番ビルドのプレビュー:
```bash
npx vite build && npx vite preview --port 4173
# → http://localhost:4173
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
| **Files タブ "No files" (DemoMode)** | **s3ApResourceArns に S3 AP ARN のみ、バケット ARN がない** | **`arn:aws:s3:::your-bucket` + `arn:aws:s3:::your-bucket/*` を追加** |
| Upload タブが「未設定」と表示 | portal-config.ts の s3ApAlias が空、または sandbox 未実行 | alias を設定 → `npx ampx sandbox` → リロード |
| Upload / フォルダー作成が 501 NotImplemented | S3 AP が `if-none-match`（条件付き書き込み）を未実装。Storage Browser の既定ハンドラーが送る | `src/lib/storageBrowserWriteHandlers.ts` の差し替えハンドラーを使う（既定で有効） |
| Upload タブ "ListCallerAccessGrants" | 旧コードが `createManagedAuthAdapter` を使用 | StorageBrowserTab.tsx を direct auth モードに更新 |
| Process タブ赤バナー | SFn ARN がプレースホルダー | `make sfn-test-create` |
| ログイン失敗 | ユーザー未作成 | Step 4 実行 |
| sandbox 失敗 "Cannot find module" | portal-config.ts がない | `cp portal-config.example.ts portal-config.ts` |
| AppSync resolver "Data source not found" | Data source が別の CDK スタックにある | Data source は API と同一スタックに置く |
| **sandbox デプロイが 2 分以上** | **IAM ポリシーや環境変数の変更（hot-swap 非対象）** | **想定動作。Lambda コードのみの変更は ~7 秒** |
| **cdk-nag でデプロイがブロック** | cdk-nag を常時適用にした場合のみ発生（既定は無効なので通常は起きない） | `CDK_NAG=1` を付けずにデプロイする。nag の確認は `CDK_NAG=1 npx ampx generate outputs` を別途実行 |

> **DemoMode の IAM に関する注意**: S3 AP ARN (`arn:aws:s3:*:*:accesspoint/*`) と通常の S3 バケット ARN (`arn:aws:s3:::bucket-name`) は**異なるフォーマット**です。DemoMode で通常 S3 バケットを使う場合、`portal-config.ts` の `s3ApResourceArns` にバケット ARN とオブジェクトレベル ARN の両方を追加する必要があります。

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
| `s3ApAlias` | portal-config.ts | Lambda のファイルアクセスと、`amplify_outputs.json` 経由の Upload タブ |
| `region` | portal-config.ts | FSx for ONTAP リージョンと一致させる |

### エイリアスは API から引く

`s3ApAlias` を手で書き写すと、削除済みや `MISCONFIGURED` の Access Point でも設定ファイル上は
正しく見えます。インベントリは FSx API から derive してください。

```bash
make discover-s3ap ARGS="--lifecycle AVAILABLE --format table"   # 使える AP の一覧
make discover-s3ap ARGS="--require-alias <alias>"                # 無ければ non-zero
REGIONS="ap-northeast-1 us-east-1" make discover-s3ap            # 複数リージョン
make discover-s3ap ARGS="--accounts 111111111111 222222222222 --role-name <role>"
```

`--require-alias` はデプロイ前のゲートとして使えます（`AVAILABLE` でなければ失敗）。

ポータル自身も実行時に同じ API を引きます。Upload タブの location 一覧は `listAccessPoints`
アクション（ListFiles Lambda）が返す値で、`portal-config.ts` の alias と `groupApMapping` の
うち**呼び出し元のグループに対応するもの**だけを、`Lifecycle` と Internet/VPC 由来を添えて
返します。account 内の全 AP を出すわけではないので、可視範囲は従来どおり設定が決めます。
`fsx:DescribeS3AccessPointAttachments` が拒否された場合は `lifecycle: UNKNOWN` として
そのまま返す（読み取り権限の不足でブラウズ不能にしない）。

### グループと AP の対応がずれていないか調べる

`groupApMapping` は手書きで、これまで**ずれても誰も知らせませんでした**（AP を作り替えると
古い alias が残り、そのグループは存在しないものを指す）。対応表そのものは設定ファイルに残し、
Access Point のタグと食い違ったら報告する検査を用意しています。

```bash
make check-group-ap-tags                        # 既定のタグキーは PortalGroup
make check-group-ap-tags ARGS="--tag-key Team"
```

`PortalGroup=engineering` とタグ付けした AP は、対応表の `engineering` に現れることを期待します。
報告するのは 4 種類です。タグ付き AP が無いグループ、alias が別の AP に移っているグループ、
対応表に無いタグ、同じタグ値を持つ AP が 2 つ（対応表は 1 つしか書けない）。**タグを付け忘れても
動作は壊れません**。可視範囲を決めるのは引き続き設定ファイルで、検査は知らせるだけです。
終了コード 2 は `portal-config.ts` が無い場合で、「一致した」とは区別しています。
| `stateMachineArn` | portal-config.ts + start-processing.js | Process タブのワークフロー起動 |
| `groupApMapping` | portal-config.ts | チームごとのファイル分離 (My Files) |
| `bedrockKbId` | portal-config.ts | 全文セマンティック検索 |
| `ONTAP_MGMT_IP` | Lambda 環境変数 | バージョン履歴（Snapshot 一覧） |
| `CLASSIFICATION_TABLE_NAME` | Lambda 環境変数 | CONFIDENTIAL ガードレール |
| `AI_METADATA_TABLE_NAME` | Lambda 環境変数 | AI 結果のインラインバッジ |
