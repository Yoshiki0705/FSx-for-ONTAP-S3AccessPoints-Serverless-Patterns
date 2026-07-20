# Amplify Gen2 + CDK 設計判断ガイド

> CDK Conference Japan 2026 セッション「Amplify Gen2 で backend.ts に CDK を定義する/しないことによる CDK の挙動の違いとユースケース」(鈴木) の知見を反映。

## 判断基準: backend.ts 内に定義するか、外部スタックにするか

Amplify Gen2 では `defineBackend()` の戻り値から CDK スタックにアクセスし、追加リソースを配置できます。しかし、**すべてを backend.ts に詰め込む**のと**外部スタックに分離する**のでは、デプロイ挙動・依存関係・テスト容易性が異なります。

### backend.ts 内に定義すべきリソース

| リソース種別 | 理由 |
|-------------|------|
| AppSync Data Source (HTTP/Lambda) | AppSync API と同じスタックに存在しないと "Data source not found" エラー |
| AppSync API に紐づく Lambda 関数 | Data Source として API に登録するため、同一スタック必須 |
| Cognito Identity Pool のポリシー追加 | `backend.auth.resources` 経由でのみアクセス可能 |
| cdk-nag Aspects 適用 | `Stack.of()` で取得した参照に直接適用 |

### 外部スタック（別 CDK App / 別テンプレート）に分離すべきリソース

| リソース種別 | 理由 |
|-------------|------|
| VPC / Subnet / Security Group | ライフサイクルが異なる（ポータルより長寿命） |
| FSx for ONTAP ファイルシステム | インフラ層。ポータルの再デプロイで影響を受けてはならない |
| Step Functions State Machine (UC パターン) | 独立デプロイ可能。ポータルは ARN 参照のみ |
| DynamoDB テーブル（JobExecution 等） | Amplify Gen2 の defineData が自動管理 |
| S3 バケット（Athena 結果出力用） | ポータルのライフサイクルと独立 |

### このプロジェクトで実際にハマったケース

#### ケース 1: Data Source を別スタックに定義 → "Data source not found"

```typescript
// ❌ FAILS: Data Source in a different stack
const infraStack = new Stack(app, "InfraStack");
const sfnDataSource = new HttpDataSource(infraStack, "SfnDS", { ... });
// → AppSync API は dataStack にある → resolver が Data Source を見つけられない
```

```typescript
// ✅ WORKS: Data Source in the SAME stack as AppSync API
const dataStack = Stack.of(api);
const sfnDataSource = api.addHttpDataSource("SfnDS", endpoint, { ... });
// → 同一スタック内なので resolver binding が成功
```

**根本原因**: AppSync の resolver は CloudFormation テンプレート内の論理 ID で Data Source を参照する。クロススタック参照では論理 ID が解決できない。

#### ケース 2: Lambda を VPC 内に配置 → sandbox デプロイが 10 分以上に

VPC Lambda（ListSnapshots 等）は ENI の作成/削除に時間がかかる。`npx ampx sandbox` のホットスワップ対象外のため、VPC 設定変更のたびにフルデプロイが走る。

**対策**: VPC Lambda は `process.env` でオプション化し、DemoMode では VPC 配置をスキップ:

```typescript
// VPC configuration is optional — only applied when env vars are set
...(process.env.VPC_ID ? {
  vpc: ec2.Vpc.fromLookup(dataStack, 'PortalVpc', { vpcId: process.env.VPC_ID }),
  securityGroups: [ec2.SecurityGroup.fromSecurityGroupId(...)],
} : {}),
```

#### ケース 3: 環境変数が未設定のまま synth → Lambda が起動時にクラッシュ

```typescript
// ❌ Lambda が空文字列で API を呼ぶ → ランタイムエラー
environment: { ONTAP_MGMT_IP: process.env.ONTAP_MGMT_IP || "" }
```

**対策**: Lambda コード内でフォールバック UI を返す（今回の VersionHistory 改善で対応済み）。

## Amplify Gen2 sandbox のライフサイクル

```
npx ampx sandbox --once
  ├── cdk synth (backend.ts → CloudFormation テンプレート生成)
  │     └── cdk-nag チェック実行（AwsSolutionsChecks）
  ├── cdk deploy (差分のみ反映)
  │     ├── 初回: Cognito User Pool + AppSync API + Lambda x N + DynamoDB
  │     └── 2回目以降: 変更された Lambda コードのみホットスワップ（数秒）
  └── amplify_outputs.json 生成（フロントエンドが読み込む設定ファイル）
```

**ホットスワップ対象**: Lambda コード変更、AppSync resolver コード変更
**フルデプロイになる変更**: IAM ポリシー変更、VPC 設定変更、新規リソース追加、環境変数追加

## 推奨ワークフロー

1. **開発時**: `npx ampx sandbox` (watch mode) — Lambda コード変更は数秒で反映
2. **CI**: `npx ampx sandbox --once` + `cdk synth` → cdk-nag チェック → テスト
3. **本番**: `npx ampx pipeline-deploy` (Amplify Hosting の CI/CD パイプライン)

## 関連リファレンス

- [Amplify Gen2: Add custom AWS resources](https://docs.amplify.aws/react/build-a-backend/add-aws-services/custom-resources/)
- [CDK Conference Japan 2026 セッション一覧](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
- [builders.flash: Amplify Gen2 から始める CDK 入門](https://aws.amazon.com/jp/builders-flash/202411/cdk-introduction-with-amplify-gen2/)
