# スキャフォールディング生成物のデプロイ検証と撤収手順

> 🌐 **Language / 言語**: 日本語 | [English](../en/scaffolding-deploy-verification.md)

対象は [アプリの土台の選択肢](scaffolding-and-backend-toolkit-choices.md) で比較した 3 つの生成物を、
**実際に AWS へデプロイして確認し、確認したら撤収する**作業。比較ドキュメントの数値はローカル
synth までの実測なので、この文書はその先（デプロイ・実機動作・撤収）を担当する。

**先に読む理由**: 生成物には削除保護と `Retain` が既定で入っており、スタックを削除しても消えない
リソースが残る。件数と種類は下の[撤収手順](#撤収手順)にあり、**デプロイ前に読む前提**で置いてある。

**この文書は発見の報告ではない。** 踏んだ箇所はいずれも上流の資料に対応するものがあり、下の
[既知性のマッピング](#既知性のマッピング)で 1 件ずつ突き合わせている。新規の主張として書くと、
既に公開されている一次資料より弱い根拠で同じことを言うことになる。

## 検証区分

ポータルの [検証結果](../../solutions/amplify-portal/docs/verification-results.md) と同じ語を使う。
区分を共有するのは、「同じ言葉で違う強さのことを言っている」状態を避けるため。

| 区分 | 意味 |
|------|------|
| **実機 E2E** | AWS にデプロイし、アプリの機能を実行して期待した結果を確認した |
| **実機 読み取り** | デプロイして参照・一覧までは確認したが、書き込み / 変更系は未確認 |
| **ローカルのみ** | ローカル実装（AWS 不要のモード）で動作を確認した。AWS 上では未確認 |
| **synth のみ** | テンプレートを生成して内容を読んだだけ。デプロイしていない |

## 事前条件

| 項目 | 必須 | 確認方法 |
|---|---|---|
| CDK bootstrap（対象リージョン） | ✅ | `aws cloudformation describe-stacks --stack-name CDKToolkit` |
| CDK bootstrap（us-east-1） | Nx のみ | Nx の生成物は CloudFront 用 Web ACL を **us-east-1 の別スタック**に作るため、対象リージョンとは別に必要 |
| Node.js 22 以上 | ✅ | AWS Blocks の前提条件（[Getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)） |
| npm 11 以上 | Nx のみ | Nx Plugin for AWS の前提条件。npm 10 では生成が `Cannot read properties of null (reading 'edgesOut')` で失敗する（出典: [awslabs/nx-plugin-for-aws PR #1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228)） |
| 非対話シェルでの `npm_config_yes=true` | Nx のみ | `npm create` の初回インストール確認に応答するため（P11） |

## 既知性のマッピング

**上流に一次資料があるかどうかを、項目ごとに分けて書く。** 「既知」は踏まなくてよいという意味では
なく、**この文書が新しい根拠を出す必要がない**という意味である。

| # | 事象 | 既知性 | 一次資料 |
|---|---|---|---|
| P1 | express モードのデプロイが失敗時にロールバックせず、以降の操作もモードに縛られる | **文書化済み + 上流 issue あり** | [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) / [nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265) / [aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931) |
| P2 | `cdk destroy --express` にも同じ性質 | **文書化済み** | [cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html) |
| P3 | DynamoDB の削除保護は所有者を含め誰にも削除させない | **文書化済み** | [WorkingWithTables.Basics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html) |
| P4 | Cognito の削除保護が `InvalidParameterException` を返す | **文書化済み** | [Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html) |
| P5 | KMS は削除予定中は課金されず、取り消すと遡って課金される | **文書化済み** | [KMS pricing](https://aws.amazon.com/kms/pricing/) |
| P6 | Web ACL は関連付けを外さないと `WAFAssociatedItemException` | **文書化済み** | [DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html) |
| P7 | Blocks の sandbox と production でコマンドと撤収経路が別 | **文書化済み** | [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) |
| P8 | `Retain` のリソースがスタック削除後に残る | **文書化済み**（数量はこの文書の実測） | [DeletionPolicy](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html) |
| P9 | Block ID の変更が stateful Block のデータ損失になる | **文書化済み** | [AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) |
| P10 | テンプレート外のロググループが残り、保持期間が無期限 | **文書化済み + 上流 issue 2 件**（残存件数はこの文書の実測） | [Lambda logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html) / [aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553) / [aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815) |
| P11 | `npm create` が非対話シェルで停止する | **npm の既定動作**（切り分けはこの文書の実測。上流の類似 PR は別原因） | [npm-config `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) / [nx-plugin-for-aws #1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193) |
| P12 | hotswap がスタックにドリフトを持ち込む | **文書化済み** | [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)（`--hotswap`） |

**AWS Support への問い合わせは行っていない。** 上の 12 件はいずれもサービス側の挙動の欠落ではなく、
公開ドキュメントに記載のある挙動か、ツール側（CDK CLI / Nx プラグイン）に既存の issue が立っている
ものだった。サービス挙動として未説明のものが残っていないため、問い合わせる対象がない。

## 罠の登録簿

**すべて出典つき。** このプロジェクトの目的は思いつきを増やすことではなく、人と AI が踏む箇所を
先に潰すことなので、根拠のない注意書きは置かない。

### P1. express モードのデプロイの不可逆性と、モードの固着

生成された `packages/infra/project.json` の target（一次情報）:

```json
"deploy-sandbox": { "command": "cdk deploy --require-approval=never \"<stack>/**\" --express" }
```

`--express` について AWS CDK CLI リファレンスが書いていること:

> Express mode allows for faster deployments through CloudFormation by reporting stack
> operations as completed as soon as CloudFormation applies the resource configuration.
> However, CloudFormation reports success without waiting for resources to stabilize.
> Additionally, express mode does not perform rollback automatically and will leave stacks
> in a failed state if something goes wrong.

出典: [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)（`--express`）。
同ページは本番デプロイに推奨しないとし、自動ロールバックを戻すには `--rollback` を併用すると
書いている。**生成物は `--rollback` を付けていない。**

**上流に既に登録されている。** [awslabs/nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265)
が、生成された express target で置換を伴う更新をすると
`Replacement type updates not supported on stack with disable-rollback` で止まることを報告し、
回避策として **`--express --rollback` の併用**を挙げている。CDK CLI 側の関連は
[aws/aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931)。

**踏み方**: `deploy-sandbox` が成功を返したのでリソースが安定したと読み、直後の動作確認が
不定に失敗する。あるいは途中で失敗してスタックが failed state のまま残る。

**対策は `--express` を外すことではない。** express で最後に更新されたスタックは、その後の操作も
express である必要がある。実測（2026-09-12）では次の 2 つがいずれも拒否された。

| 復旧の試み | 返るもの |
|---|---|
| `cdk rollback` | `RollbackStack is not supported for stacks that were last updated using EXPRESS deployment mode` |
| `cdk deploy`（express なし） | `Follow-up operations must use the same DeploymentConfig (mode=EXPRESS)` |

つまり**壊れた express スタックを戻せるのは別の express デプロイだけ**である。したがって推奨は
target を `--express --rollback` に変えることで、`--express` を落として `deploy` に切り替える
手当ては、既に express で更新済みのスタックには適用できない。

### P2. `cdk destroy --express` にも存在する同じ性質

`cdk destroy` にも `--express` があり、同じ「安定化を待たない・自動ロールバックしない」性質と、
**本番のスタック撤収には推奨しない**という記述がある（出典:
[cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html)）。
生成された `destroy-sandbox` は `--express` を付けていないので、撤収側は既定で安全側にある。

### P3. DynamoDB の削除保護の強さ

<!-- allow:not-a-claim: 次行は AWS ドキュメントの逐語引用で、この文書の主張ではない -->
> When deletion protection is enabled for a table, it cannot be deleted by anyone.

出典: [Basic operations on DynamoDB tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html)。
`UpdateTable` で無効化してから削除する。

**該当**: Nx 1 本、AWS Blocks（production preset）4 本。いずれも `DeletionPolicy: Retain` も
付いているので、スタック削除では対象にすらならない。

### P4. Cognito User Pool の削除保護が返すエラー名の紛らわしさ

> When you try to delete a protected user pool in a `DeleteUserPool` API request, Amazon
> Cognito returns an `InvalidParameterException` error. To delete a protected user pool,
> send a new `DeleteUserPool` request after you deactivate deletion protection in an
> `UpdateUserPool` API request.

出典: [Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html)
および UpdateUserPool の
[deletionProtection](https://docs.aws.amazon.com/sdk-for-kotlin/api/latest/cognitoidentityprovider/aws.sdk.kotlin.services.cognitoidentityprovider.model/-update-user-pool-request/deletion-protection.html)。

**該当**: Nx が `DeletionProtection: ACTIVE` で 1 本作る。エラー名が
`InvalidParameterException` なので、**パラメータの書き方の問題に見える**のが踏みどころ。

### P5. KMS の削除は最短 7 日の待機。ただし待機中は課金されない

待機期間は 7〜30 日で既定 30 日、状態は `PendingDeletion`、`CancelKeyDeletion` で取り消せる
（出典: [Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html)、
[schedule-key-deletion](https://docs.aws.amazon.com/cli/latest/reference/kms/schedule-key-deletion.html)）。

課金については料金ページが次のように書いている。

> There is no charge for customer managed KMS keys that you manage and are scheduled for
> deletion. If you cancel the deletion during the waiting period, the customer managed KMS
> key will incur charges as though it was never scheduled for deletion.

出典: [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/)。

**踏み方 2 つ**: (1) 「7 日間課金される」と誤って見積る。削除を予定した時点で課金は止まる。
(2) 待機中に取り消すと、予定しなかったものとして課金される。**残す判断をするなら費用も戻る。**

**該当**: Nx 4 本（すべて自動ローテーション有効）、AWS Blocks（production preset）1 本。

### P6. WAF Web ACL の削除順序

`DeleteWebACL` は、リソースが他から使われている場合 `WAFAssociatedItemException` を返す
（出典: [DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)）。
削除には `LockToken` も必要で、取得後に変更があると `WAFOptimisticLockException` になる。

**該当**: Nx が 3 本（REGIONAL 2 + CLOUDFRONT 1）。CLOUDFRONT スコープのものは us-east-1 側の
スタックに属する。スタック削除で消える設計だが、手で消す場合は関連付け → ACL の順になる。

### P7. AWS Blocks の sandbox と production のコマンドと性質の差

| コマンド | 何をするか | 撤収 |
|---|---|---|
| `npm run dev` | ローカル実装。AWS アカウント不要 | 不要 |
| `npm run sandbox` | Lambda の hot-swap による短命なデプロイ。開発者ごとに分離 | `npm run sandbox:destroy` |
| `npm run deploy` | CDK 経由の本番向けデプロイ | `npm run destroy` |

出典: [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html)、
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)。
ベストプラクティスは **sandbox を本番トラフィックに使わないこと**と、環境ごとに別アカウントを
用意することを挙げている（出典:
[Best practices for AWS Blocks](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html)）。

**踏み方**: `sandbox` と `deploy` を同じものと考えて撤収コマンドを間違える。片方の撤収は
もう片方のリソースに触らない。

### P8. スタック削除後に残る `DeletionPolicy: Retain` のリソース

`DeletionPolicy: Retain` はスタックから切り離すだけでリソースを保持する（出典:
[DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)）。
挙動そのものは文書化済みで、**この文書が足すのは生成物ごとの件数**である。

synth 済みテンプレートから数えた、スタック削除では消えないリソース（2026-09-07 実測）:

| 構成 | 件数 | 内訳 |
|---|---|---|
| AWS Blocks（sandbox preset） | **0** | — |
| AWS Blocks（production preset） | 9 | DynamoDB 4（削除保護 + Retain）、KMS 1、CDK バケットデプロイのカスタムリソース 4（Retain） |
| Nx Plugin for AWS | 9 | Cognito User Pool 1（削除保護 + Retain）、DynamoDB 1（同）、IAM ロール 2（Retain）、KMS 4（Retain）、ロググループ 1（Retain） |

**AWS Blocks の sandbox preset だけが 0 件**なので、最初に確認するならこれが最も戻しやすい。

### P9. preview であることの扱い

AWS Blocks は preview で、公式ドキュメントは Block ID（コンストラクタの第 2 引数）の変更が
対応する AWS リソースの削除と再作成を引き起こし、`KVStore` / `DistributedTable` / `Database` /
`FileBucket` のような stateful な Block では**永久的なデータ損失**になると書いている。Block ID は
デプロイ後は不変として扱う（出典:
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)）。

### P10. テンプレート外のロググループの残存と、無期限の保持期間

**上の表はテンプレートを数えたもので、それでは足りないことが実測で判明した。**

実測 2026-09-12、AWS Blocks（sandbox preset）を ap-northeast-1 にデプロイして
`npm run sandbox:destroy` で撤収したところ、スタック・DynamoDB 4 本・S3 バケットはすべて消えた
一方で、**ロググループが 5 件残った**。いずれも `retentionInDays` が未設定（無期限）で、
内訳は CDK / Blocks のカスタムリソースプロバイダ用 Lambda のもの
（`BlocksGsiProviderframework` 2 件、`BlocksSecretProviderframework`、
`CustomCDKBucketDeployment`、`CustomS3AutoDeleteObjects`）。

<!-- allow:not-a-claim: 以下は自分で実測した観測の記述で、ベンダーの機能欠落の主張ではない -->
テンプレートが宣言していたロググループは 4 件（アプリの handler と Blocks 内部の 3 つ）で、
これらはスタック削除で消えている。残った 5 件はテンプレートに現れない。

**両方の要素が上流に記載されている。**

- **無期限になること**: Lambda のドキュメントが、関数の初回実行時にロググループが作られ、
  その保持期間は無期限になると書いている（出典:
  [Lambda logs in CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)）。
- **CDK のカスタムリソースの分**: [aws/aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553)
  が CustomResourceProvider のロググループを削除・設定できるようにする要望として立っており、
  [aws/aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815) が
  `s3.Bucket` の `autoDeleteObjects` が作るロググループが Never expire で残ることを報告している。
  今回残った 5 件のうち `CustomS3AutoDeleteObjects` は #24815 と同一のもの。

**踏み方**: 「テンプレートを読めば何が残るか分かる」という前提が崩れる。**synth ベースの棚卸しは、
CloudFormation の外で作られるリソースを原理的に見られない。**

<!-- allow:not-a-claim: ポータル側の既存記録の要約で、新たな主張ではない -->
同じ形はこのリポジトリのポータルでも記録されていて、そちらでは 101 件のうち 92 件（9.0 MB）が
対応する Lambda を伴わない状態で残っていた（[portal-sandbox-lifecycle](../agent/portal-sandbox-lifecycle.md)）。

**対策**: 撤収の最後に、スタック名を接頭辞にしてロググループを走査する。

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/<stack-name>" \
  --query "logGroups[].[logGroupName,retentionInDays]" --output text
```

デプロイ直後の `storedBytes` は 0 なので費用はほぼ発生しないが、デプロイを繰り返すたびに増える。

### P11. 非対話シェルで見えない確認プロンプトによる停止

`npm create @aws/nx-workspace` が出力を出さずに長時間停止し、25 分経っても生成物が作られない
状態を観測した（2026-09-07）。当初はこれを「npm 経由では生成できない」と読み、pnpm 経由に
切り替えて測定した。

**切り分けた結果、原因は npm の初回インストール確認だった**（2026-09-12）。標準出力を
捕捉した状態で実行すると、次の行で待っている。

```
Need to install the following packages:
@aws/create-nx-workspace@1.0.0
Ok to proceed? (y)
```

`npm_config_yes=true` を付けた同じコマンドは **45 秒で完走**し、生成された `package.json` に
`@aws/nx-plugin@1.0.0` が入ることを確認した。**pnpm は必要条件ではない。**

**踏み方**: プロンプトは改行を伴わないため、ログを行単位で読む自動化からは何も出ていないように
見える。「無出力で停止」は「処理が進んでいない」ではなく「入力を待っている」だった。同じ形は
`npx cdk`（CDK の導入確認）と `npx pnpm`（pnpm@12 の導入確認）でも観測している。

**混同しやすい別の遅延が上流にある。**
[awslabs/nx-plugin-for-aws PR #1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193) は、
npm の advisory 一括取得エンドポイント（`POST /-/npm/v1/security/advisories/bulk`）の応答が
遅いときに生成が待たされることを扱い、`npm_config_audit=false` で所要時間が 26 秒から
414 ミリ秒に縮んだと記録している。**今回の停止はこれではない。** `npm_config_audit=false` だけを
付けた実行は同じプロンプトで待ち続け、`npm_config_yes=true` で解けた。
[PR #1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228) が扱う npm 10 の
`Cannot read properties of null (reading 'edgesOut')` も、自環境が npm 11.17.0 なので該当しない。

**この項目は最初の測定の前提を訂正している。** 比較ドキュメントは pnpm で測った数値を
そのまま残し、理由の記述だけを直した（数値を測ったコマンドと文書のコマンドを一致させるため）。

### P12. hotswap が持ち込むドリフト

CDK CLI は `--hotswap` について、CloudFormation を経由せず直接リソースを更新するため
**意図的にスタックのドリフトを持ち込む**とし、本番スタックには使わないよう書いている。
`--hotswap` は `--no-rollback` を含意し、次の非 hotswap デプロイでは `--revert-drift` を
併用するよう案内される（出典:
[cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)）。

**該当**: AWS Blocks の `npm run sandbox` は hot-swap を使う（P7）。同じスタックを後から
`npm run deploy` 相当の経路で更新する運用にすると、ドリフトを抱えた状態から始まる。**sandbox と
production はスタックを共有しない**のが前提（出典:
[Best practices for AWS Blocks](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html)）。

## 撤収手順

**順序が意味を持つ。** 保護を外す → スタックを削除 → 残ったものを個別に削除。

```bash
# 1. スタックを削除（Retain と削除保護のものは残る）
#    Blocks sandbox:    npm run sandbox:destroy
#    Blocks production: npm run destroy
#    Nx:                nx run @<workspace>/infra:destroy
#    express で更新したスタックは、以降の操作も express である必要がある（P1）

# 2. DynamoDB: 削除保護を外してから削除（P3）
aws dynamodb update-table --table-name <name> --no-deletion-protection-enabled
aws dynamodb delete-table --table-name <name>

# 3. Cognito: 削除保護を Inactive にしてから削除（P4）
aws cognito-idp update-user-pool --user-pool-id <id> --deletion-protection INACTIVE
aws cognito-idp delete-user-pool --user-pool-id <id>

# 4. KMS: 待機期間を最短の 7 日にして予定（P5。予定した時点で課金は止まる）
aws kms schedule-key-deletion --key-id <id> --pending-window-in-days 7

# 5. 残った IAM ロール・ロググループ・S3 バケットを削除
aws logs delete-log-group --log-group-name <name>
aws iam delete-role --role-name <name>          # インラインポリシーを先に削除

# 6. テンプレート外のロググループを走査（P10。手順 1 では消えない）
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/<stack-name>" \
  --query "logGroups[].[logGroupName,retentionInDays]" --output text
```

**削除の完了は API の戻り値ではなく状態で確認する。** 一覧から消えたことを数十秒おいて再確認する。

## 費用の見積り

同日にデプロイして撤収する場合、時間按分される項目が主になる。

| 項目 | 単価 | 同日撤収時の目安 |
|---|---|---|
| WAF Web ACL + ルール（Nx: 3 ACL + 6 ルール） | $21 / 月（時間按分） | 4 時間で約 $0.12 |
| KMS CMK（Nx 4 + Blocks 1） | $1 / 月 / 本 | 削除予定にした時点で停止（P5） |
| Cognito MAU | Plus $0.020 / MAU | 検証ユーザー数分。1〜2 人なら実質ゼロ |
| Lambda / API Gateway / DynamoDB / CloudFront / S3 | 従量 | 検証規模では数セント |

単価の出典と取得日は [比較ドキュメントの固定費の節](scaffolding-and-backend-toolkit-choices.md#固定費の差)
にある（AWS Price List API、ap-northeast-1、2026-09-07 取得）。**同日撤収なら合計 $1 未満**の
見込みで、月額 $45 は放置した場合の数字である。

## 実測結果

> 区分は上の[検証区分](#検証区分)に従い、**やっていないことを空欄にせず明示する**。

環境: ap-northeast-1、アカウントは検証用（FSx for ONTAP の検証環境と同居）、Node.js v26.4.0、
npm 11.17.0。

| 構成 | 区分 | デプロイ | 確認した操作 | 撤収 | 実施日 |
|---|---|---|---|---|---|
| AWS Blocks（sandbox preset） | **実機 E2E** | `npm run sandbox`。**リソース 83 件**（synth 実測の 83 と一致） | JSON-RPC で `authApi.setAuthState`（signUp / signIn）、`api.createTodo`（書き込み）、`api.listTodos`（読み取り）。DynamoDB に永続化されたことを応答で確認 | `npm run sandbox:destroy` 86 秒。スタック・DynamoDB 4 本・S3 は消え、**ロググループ 5 件が残った**（P10）。手で削除して 0 件を確認 | 2026-09-12 |
| AWS Blocks（production preset） | — | 未実施 | — | — | — |
| Nx Plugin for AWS | — | 未実施 | — | — | — |

## 出典一覧

- [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) / [cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html) — `--express`、`--rollback`、`--hotswap` の性質
- [CloudFormation express mode](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-express-mode.html) / [DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)
- [AWS Blocks CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) / [concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) / [best practices](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html) / [getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)
- [DynamoDB: Using deletion protection](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html)
- [Cognito: Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html)
- [KMS: Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html) / [KMS pricing](https://aws.amazon.com/kms/pricing/)
- [WAF: DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)
- [Lambda logs in CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [npm config: `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) — `npm create` の確認プロンプトの自動応答
- 上流の issue / PR: [nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265)（express target）、[#1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193)（advisory 取得の遅延）、[#1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228)（npm 11 前提）、[aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931)、[aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553)、[aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815)
- 生成物そのもの: `packages/infra/project.json`（Nx の target 定義）、`aws-blocks/index.cdk.ts` と `package.json`（Blocks のコマンドと preset）

> 内容は理解しやすさのために要約・再構成している。

## 関連ドキュメント

- [アプリの土台の選択肢](scaffolding-and-backend-toolkit-choices.md) — 3 者の位置づけ、synth までの実測、固定費
- [ポータルの検証結果](../../solutions/amplify-portal/docs/verification-results.md) — 検証区分の元になっている記録
