# マルチテナント設計パターン

> 🌐 **Language / 言語**: 日本語 | [English](../en/multi-tenant-design.md)

## 概要

本ポータルを複数テナント（組織 / チーム）向けのサービスとして提供したい ISV やマネージドサービスプロバイダー向けに、データ分離のパターンを説明します。

## 分離レベル

| レベル | 仕組み | ユースケース |
|-------|-----------|----------|
| **グループベース** | portal-config.ts の `groupApMapping` | 単一組織内のチーム分離 |
| **Cognito グループ** | テナントごとに個別の Cognito グループ | テナント数が少ない場合（20 未満） |
| **DynamoDB パーティション** | テナント ID をパーティションキーにする | 多数のテナントを抱える SaaS |
| **スタック分離** | テナントごとに 1 つの Amplify スタック | 完全分離（エンタープライズ） |

## パターン 1: groupApMapping（チーム分離に推奨）

チームごとに、異なる File System Identity（UNIX UID/GID）を持つ別々の S3 Access Point を割り当てます。その Cognito グループのユーザーには、自身の UID でアクセスできるファイルのみが見えます。

```typescript
// portal-config.ts
groupApMapping: {
  "engineering": "ap-eng-uid1001-xxx-s3alias",   // UID 1001
  "legal":       "ap-legal-uid1002-xxx-s3alias", // UID 1002
  "finance":     "ap-fin-uid1003-xxx-s3alias",   // UID 1003
}
```

**データ分離**: ONTAP の UNIX パーミッションが可視範囲を強制します。UID 1001 は UID 1002 が所有するファイルを読み取れません。

## パターン 2: DynamoDB によるテナント分離

DynamoDB のモデル（JobExecution、Favorite、RecentFile など）には、パーティションキーとして `tenantId` フィールドを追加します。

```typescript
// amplify/data/resource.ts
const schema = a.schema({
  JobExecution: a.model({
    tenantId: a.string().required(),  // Partition key
    jobId: a.string(),
    // ...
  }).authorization(allow => [
    allow.owner(),
    allow.groups(["storage-admin"]),
  ]),
});
```

**クエリパターン**: すべてのクエリに `tenantId` フィルタを含めます。AppSync のリゾルバーが Cognito トークンのクレームからテナント ID を注入します。

## パターン 3: Amplify スタックの分離（完全分離）

インフラの完全な分離を要求するエンタープライズテナント向けの構成です。

```bash
# Deploy per-tenant stack with unique identifier
npx ampx sandbox --identifier tenant-acme
npx ampx sandbox --identifier tenant-globex
```

それぞれが独自の Cognito User Pool、AppSync API、Lambda 関数、DynamoDB テーブルを持ちます。

## セキュリティ上の考慮事項

- **行レベルのセキュリティ**: DynamoDB の Condition 式によってテナント横断のデータアクセスを防ぎます
- **S3 AP の分離**: テナントごとの S3 AP は異なる File System Identity を使用し、ONTAP がファイルシステムレベルでアクセスを制御します
- **IAM の境界**: Permission Boundaries を使って、テナント固有のロールができることを制限します
- **監査**: CloudTrail のログには Cognito のユーザー識別子が含まれるため、テナントまで追跡できます

## 参考資料

- [Amplify Gen2: Multi-tenancy](https://docs.amplify.aws/gen2/build-a-backend/auth/concepts/multi-tenancy/)
- [DynamoDB tenant isolation](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/dynamodb-isolation.html)
