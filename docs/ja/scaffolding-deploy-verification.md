# スキャフォールディング生成物のデプロイ検証と後片付けの手順

> 🌐 **Language / 言語**: 日本語 | [English](../en/scaffolding-deploy-verification.md)

対象は [アプリの土台の選択肢](scaffolding-and-backend-toolkit-choices.md) で比較した 3 つの生成物を、
**実際に AWS へデプロイして確認し、確認したら削除する**作業。比較ドキュメントの数値はローカル
synth までの実測なので、この文書はその先（デプロイ・実機動作・後片付け）を担当する。

**先に読む理由**: 生成物には削除保護と `Retain` が既定で入っており、スタックを削除しても消えない
リソースが残る。件数と種類は下の[後片付けの手順](#後片付けの手順)にあり、**デプロイ前に読む前提**で置いてある。

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
| P7 | Blocks の sandbox と production でコマンドと後片付けの経路が別 | **文書化済み** | [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) |
| P8 | `Retain` のリソースがスタック削除後に残る | **文書化済み**（数量はこの文書の実測） | [DeletionPolicy](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html) |
| P9 | Block ID の変更が stateful Block のデータ損失になる | **文書化済み** | [AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) |
| P10 | テンプレート外のロググループが残り、保持期間が無期限 | **文書化済み + 上流 issue 2 件**（残存件数はこの文書の実測） | [Lambda logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html) / [aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553) / [aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815) |
| P11 | `npm create` が非対話シェルで停止する | **npm の既定動作**（切り分けはこの文書の実測。上流の類似 PR は別原因） | [npm-config `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) / [nx-plugin-for-aws #1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193) |
| P12 | hotswap がスタックにドリフトを持ち込む | **文書化済み** | [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)（`--hotswap`） |
| P13 | CloudFormation が削除する KMS 鍵は 30 日の待機に入り、後から短縮できない | **既定値は文書化済み**（短縮の拒否はこの文書の実測） | [Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html) |
| P14 | `UpdateUserPool` はフラグ 1 つでは通らず、省略した設定が既定値に戻る | **専用のページで警告されている** | [Updating user pool and app client configuration](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-updating.html) |
| P15 | `describe-stack-events` はページ単位で返すので、1 ページ目だけでは件数が少なく出る | **文書化済み**（過少計上の実例はこの文書の実測） | [DescribeStackEvents](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackEvents.html) |

**AWS Support への問い合わせは行っていない。** 上の 15 件はいずれもサービス側の挙動の欠落ではなく、
公開ドキュメントに記載のある挙動か、ツール側（CDK CLI / Nx プラグイン）に既存の issue が立っている
ものだった。サービス挙動として未説明のものが残っていないため、問い合わせる対象がない。

**この表の「文書化済み」は、踏まなかったことを意味しない。** P13 と P14 は 3 者すべてを実際に削除する
過程で踏み、公開ドキュメントを読み直して既知だと分かったものである。**後片付けの手順の側に誤りが残っていた**
ため、下の[後片付けの手順](#後片付けの手順)を実測に合わせて直した。

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

**推奨の側も実機で確認した**（2026-09-13）。生成された target に `--rollback` を足した

```
cdk deploy --require-approval=never "research-board-infra-sandbox/**" --express --rollback
```

で 2 スタック 86 リソースが 317 秒で作成された。デプロイ中の各リソースには次の行が付く。

```
Resource operation completed using Express Mode. It may continue becoming available in the background.
```

**「完了」が「利用可能」ではないことを CloudFormation 自身が毎行で言っている。** 直後に動作確認を
走らせる自動化は、この行を読んでいない。

### P2. `cdk destroy --express` にも存在する同じ性質

`cdk destroy` にも `--express` があり、同じ「安定化を待たない・自動ロールバックしない」性質と、
**本番のスタック削除には推奨しない**という記述がある（出典:
[cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html)）。
生成された `destroy-sandbox` は `--express` を付けていないので、後片付け側は既定で安全側にある。

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

**該当**: Nx が `DeletionProtection: ACTIVE` で 1 本作る。実機で再現した応答（2026-09-13）:

```
An error occurred (InvalidParameterException) when calling the DeleteUserPool operation:
The user pool cannot be deleted because deletion protection is activated.
Deletion protection must be inactivated first.
```

**本文は正確で、紛らわしいのは名前だけ**だった。`InvalidParameterException` はパラメータの
書き方の問題に見えるため、名前だけを見て引数を疑うと遠回りになる。

**そして保護を外す側が 1 フラグでは済まない。** これが P14 になる。

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

**該当**: Nx 4 本（すべて自動ローテーション有効、`Retain` なので手で予定する）、
AWS Blocks（production preset）1 本（`Retain` ではないので CloudFormation が予定する → P13）。

### P6. WAF Web ACL の削除順序

`DeleteWebACL` は、リソースが他から使われている場合 `WAFAssociatedItemException` を返す
（出典: [DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)）。
削除には `LockToken` も必要で、取得後に変更があると `WAFOptimisticLockException` になる。

**該当**: Nx が 3 本（REGIONAL 2 + CLOUDFRONT 1）。CLOUDFRONT スコープのものは us-east-1 側の
スタックに属する。スタック削除で消える設計だが、手で消す場合は関連付け → ACL の順になる。

### P7. AWS Blocks の sandbox と production のコマンドと性質の差

| コマンド | 何をするか | 後片付け |
|---|---|---|
| `npm run dev` | ローカル実装。AWS アカウント不要 | 不要 |
| `npm run sandbox` | Lambda の hot-swap による短命なデプロイ。開発者ごとに分離 | `npm run sandbox:destroy` |
| `npm run deploy` | CDK 経由の本番向けデプロイ | `npm run destroy` |

出典: [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html)、
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)。
ベストプラクティスは **sandbox を本番トラフィックに使わないこと**と、環境ごとに別アカウントを
用意することを挙げている（出典:
[Best practices for AWS Blocks](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html)）。

**踏み方**: `sandbox` と `deploy` を同じものと考えて削除コマンドを間違える。片方の削除は
もう片方のリソースに触らない。

### P8. スタック削除後に残る `DeletionPolicy: Retain` のリソース

`DeletionPolicy: Retain` はスタックから切り離すだけでリソースを保持する（出典:
[DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)）。
挙動そのものは文書化済みで、**この文書が足すのは生成物ごとの件数**である。

synth 済みテンプレートから数えた、スタック削除では消えないリソース:

| 構成 | 件数 | 内訳 |
|---|---|---|
| AWS Blocks（sandbox preset） | **0** | — |
| AWS Blocks（production preset） | 8 | DynamoDB 4（削除保護 + Retain）、CDK バケットデプロイのカスタムリソース 4（Retain） |
| Nx Plugin for AWS | 9 | Cognito User Pool 1（削除保護 + Retain）、DynamoDB 1（同）、IAM ロール 2（Retain）、KMS 4（Retain）、ロググループ 1（Retain） |

**AWS Blocks の sandbox preset だけが 0 件**なので、最初に確認するならこれが最も戻しやすい。

**production preset の件数はこの検証で 9 から 8 に訂正した。** 以前は KMS 鍵 1 本を Retain に
数えていたが、テンプレートの `DeletionPolicy` を数え直すと Retain は DynamoDB 4 と
CDKBucketDeployment 4 だけで、KMS 鍵は含まれていない。削除時の CloudFormation の応答も一致する。

| CloudFormation の状態 | 意味 | 実測 |
|---|---|---|
| `DELETE_SKIPPED` | `Retain` なので触っていない | Nx 9 件、Blocks production 8 件、Blocks sandbox 0 件。3 構成すべてで上の synth の件数と一致した（削除済みスタックの `describe-stack-events` で確認） |
| `DELETE_COMPLETE` | 実際に削除した。KMS では「削除を予定した」 | Blocks production の KMS 鍵 |

**`DELETE_COMPLETE` を見て「消えた」と読むと、KMS では 30 日の待機に入っただけである**（→ P13）。

### P9. preview であることの扱い

AWS Blocks は preview で、公式ドキュメントは Block ID（コンストラクタの第 2 引数）の変更が
対応する AWS リソースの削除と再作成を引き起こし、`KVStore` / `DistributedTable` / `Database` /
`FileBucket` のような stateful な Block では**永久的なデータ損失**になると書いている。Block ID は
デプロイ後は不変として扱う（出典:
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)）。

### P10. テンプレート外のロググループの残存と、無期限の保持期間

**上の表はテンプレートを数えたもので、それでは足りないことが実測で判明した。**

実測 2026-09-12、AWS Blocks（sandbox preset）を ap-northeast-1 にデプロイして
`npm run sandbox:destroy` で削除したところ、スタック・DynamoDB 4 本・S3 バケットはすべて消えた
一方で、**ロググループが 5 件残った**。いずれも `retentionInDays` が未設定（無期限）で、
内訳は CDK / Blocks のカスタムリソースプロバイダ用 Lambda のもの
（`BlocksGsiProviderframework` 2 件、`BlocksSecretProviderframework`、
`CustomCDKBucketDeployment`、`CustomS3AutoDeleteObjects`）。

<!-- allow:not-a-claim: 以下は自分で実測した観測の記述で、ベンダーの機能欠落の主張ではない -->
テンプレートが宣言していたロググループは 4 件（アプリの handler と Blocks 内部の 3 つ）で、
これらはスタック削除で消えている。残った 5 件はテンプレートに現れない。

**残る 3 構成すべてで同じ形だった**（2026-09-12〜13 実測）。宣言済みは保持期間が設定され、
無宣言は例外なく無期限だった。

| 構成 | 宣言済み（消える） | 無宣言で残る | 宣言済みで残る |
|---|---|---|---|
| Blocks（sandbox preset） | 4（365 日） | **5**（無期限） | 0 |
| Blocks（production preset） | 4（365 日） | **8**（無期限） | 0 |
| Nx Plugin for AWS | 4（30〜365 日） | **6**（無期限） | 1（`Retain` の API アクセスログ、365 日） |

production preset が sandbox より 3 件多いのは、静的配信を足すぶんの CloudFront ルートストア用
Lambda とバケットデプロイが増えるため。Nx で残る 6 件には
`CustomCrossRegionExportReader`（us-east-1 の Web ACL をクロスリージョン参照するためのもの）が
含まれる。**構成が増えるほどカスタムリソースが増え、残るロググループも増える。**

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

**対策**: 後片付けの最後に、スタック名を接頭辞にしてロググループを走査する。

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

### P13. CloudFormation が予定した KMS の待機期間の固定

`PendingWindowInDays` は 7〜30 日で**既定 30 日**（出典:
[Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html)）。
CloudFormation が KMS 鍵を削除するときはこの API を既定で呼ぶため、待機は 30 日になる。

**後から短縮しようとすると拒否される**（実測 2026-09-13）。

```
$ aws kms schedule-key-deletion --key-id <id> --pending-window-in-days 7
An error occurred (KMSInvalidStateException) ... is pending deletion.
```

短縮するには `CancelKeyDeletion` で取り消してから予定し直すことになるが、取り消しは
「予定しなかったものとして課金される」（P5 の料金ページ）。**待機中の鍵は無料なので、
30 日のまま置くほうが安い。**

**踏み方**: 後片付けの手順に `--pending-window-in-days 7` と書いてあるのを、残った鍵すべてに
適用できると読む。**これが効くのは `Retain` で残った鍵（自分で予定する側）だけ**で、
CloudFormation が削除した鍵には効かない。下の[後片付けの手順](#後片付けの手順)はこの区別を反映している。

### P14. 削除保護の解除が 1 フラグでは通らないこと

`aws cognito-idp update-user-pool --deletion-protection INACTIVE` だけを送ると失敗する。
実測（2026-09-13）では 2 段階で拒否された。

```
1回目: All attributes in AttributesRequireVerificationBeforeUpdate must exist in AutoVerifiedAttributes
2回目: SMS configuration is required when phone_number is selected for auto verification
   （AutoVerifiedAttributes を戻したうえで再送したとき）
```

**原因は `UpdateUserPool` が全置換であること。** AWS の専用ページがこう書いている。

> When you submit an update request with just one parameter, Amazon Cognito sets that
> parameter to the value of your choosing and sets all others to a default value. This can
> reset configurations including your attribute schema, your Lambda triggers, and your email
> and SMS message configuration.

出典: [Updating user pool and app client configuration](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-updating.html)。

Nx が生成する User Pool は `AutoVerifiedAttributes` に `email` と `phone_number` を持ち、
`phone_number` は SMS 設定を要求するので、**通ったのは 3 つを同時に戻したとき**だった。

**さらに順序の制約がある。** その SMS 設定が参照する SNS caller ロールは、**`Retain` で残る
2 本の IAM ロールのうちの 1 本**である。IAM ロールを先に消すと、削除保護を外す経路そのものが
失われる。**User Pool を消してから IAM ロールを消す。**

### P15. ページ単位で返る API で件数を数えるときの過少計上
`DescribeStackEvents` は `NextToken` でページを返す（出典:
[DescribeStackEvents](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackEvents.html)）。
1 ページ目だけを読むと、**新しいイベントだけが入り、古いイベントは黙って落ちる。**
上の P8 の件数を検証する過程で実際に過少に数えた（実測 2026-09-15）。

```
# 1 ページ目だけ（--no-paginate）→ DELETE_SKIPPED 6 件
# 全ページ                       → DELETE_SKIPPED 9 件
```

削除済みスタックのイベントは**スタック削除から 90 日は引ける**が（出典:
[ListStacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListStacks.html)）、
**名前では引けず ID（ARN）が必須**である（出典: 同 DescribeStackEvents の `StackName`。
"Deleted stacks: You must specify the unique stack ID"）。その ID を `list-stacks` から
取り出すときにも注意が要る。`--query` はページごとに適用されるので、一致がないページは
`None` を返し、そのまま変数に入れると ID が壊れる。`--no-paginate` を付けるか、
`grep '^arn:'` で拾う。

**踏み方**: 件数が合わないとき、数え方（`DeletionPolicy` の読み違い）を疑って調べ直す。
実際にずれていたのは取り方だった。**エラーは出ず、少ない数が正常に返る。**
「件数が想定より少ない」は、読み間違いより先にページングを疑う。

## 後片付けの手順

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

# 3. Cognito: 削除保護の解除は 1 フラグでは通らない（P14）。
#    UpdateUserPool は全置換なので、省略した設定を一緒に送り直す。
#    IAM ロール（手順 5）より先に消す。SMS 設定が残存ロールを参照している。
aws cognito-idp update-user-pool --user-pool-id <id> \
  --deletion-protection INACTIVE \
  --auto-verified-attributes email phone_number \
  --user-attribute-update-settings 'AttributesRequireVerificationBeforeUpdate=phone_number,email' \
  --sms-configuration "SnsCallerArn=<sms-role-arn>,ExternalId=<external-id>"
#    ↑ 3 つの値は先に describe-user-pool で読む（構成によって異なる）
aws cognito-idp delete-user-pool --user-pool-id <id>

# 4. KMS: Retain で残った鍵だけを、最短の 7 日で予定する（P5）
#    CloudFormation が削除した鍵は既に 30 日で予定済みで、短縮できない（P13）。
#    待機中は課金されないので、そのまま置く。
aws kms schedule-key-deletion --key-id <id> --pending-window-in-days 7

# 5. 残った IAM ロール・ロググループ・S3 バケットを削除
aws logs delete-log-group --log-group-name <name>
aws iam delete-role --role-name <name>          # インラインポリシーとアタッチを先に外す

# 6. テンプレート外のロググループを走査（P10。手順 1 では消えない）
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/<stack-name>" \
  --query "logGroups[].[logGroupName,retentionInDays]" --output text
```

**削除の完了は API の戻り値ではなく状態で確認する。** 一覧から消えたことを数十秒おいて再確認する。

## 費用の見積り

同日にデプロイして削除する場合、時間按分される項目が主になる。

| 項目 | 単価 | 同日削除時の目安 |
|---|---|---|
| WAF Web ACL + ルール（Nx: 3 ACL + 6 ルール） | $21 / 月（時間按分） | 実測の稼働 1.5 時間で約 $0.04 |
| KMS CMK（Nx 4 + Blocks 1） | $1 / 月 / 本 | 削除予定にした時点で停止（P5） |
| Cognito MAU | Plus $0.020 / MAU | 検証で作ったのは 1 ユーザー |
| Lambda / API Gateway / DynamoDB / CloudFront / S3 | 従量 | 検証規模では数セント |

単価の出典と取得日は [比較ドキュメントの固定費の節](scaffolding-and-backend-toolkit-choices.md#固定費の差)
にある（AWS Price List API、ap-northeast-1、2026-09-07 取得）。**同日削除なら合計 $1 未満**の
見込みで、月額 $45 は放置した場合の数字である。

実際に 3 構成を回した結果、**時間の大半はデプロイの待ちだった**（Blocks production が 1,228 秒、
Nx が 317 秒、削除が 225 秒と 292 秒）。Blocks production が長いのは DynamoDB の GSI を 1 本ずつ
作るためで、リソース数の差（117 対 86）よりも待ちの構造が効いている。

## 実測結果

> 区分は上の[検証区分](#検証区分)に従い、**やっていないことを空欄にせず明示する**。

環境: ap-northeast-1、アカウントは検証用（FSx for ONTAP の検証環境と同居）、Node.js v26.4.0、
npm 11.17.0。

| 構成 | 区分 | デプロイ | 確認した操作 | 後片付け | 実施日 |
|---|---|---|---|---|---|
| AWS Blocks（sandbox preset） | **実機 E2E** | `npm run sandbox`。**リソース 83 件**（synth 実測の 83 と一致） | JSON-RPC で `authApi.setAuthState`（signUp / signIn）、`api.createTodo`（書き込み）、`api.listTodos`（読み取り）。DynamoDB に永続化されたことを応答で確認 | `npm run sandbox:destroy` 86 秒。スタック・DynamoDB 4 本・S3 は消え、**ロググループ 5 件が残った**（P10）。手で削除して 0 件を確認 | 2026-09-12 |
| AWS Blocks（production preset） | **実機 E2E** | `npm run deploy` 1,228 秒。**リソース 117 件**（synth 実測の 117 と一致）。うち約 10 分は DynamoDB の GSI が 1 本ずつ作られる待ち | JSON-RPC で signUp / signIn / `createTodo`（書き込み）/ `listTodos` を 2 つの GSI（`byPriority`・`byTitle`）で読み取り、5 操作すべて 200。**production preset の差分である CloudFront 配信も 200** | `npm run destroy` 225 秒。S3 3 本は消え、**DynamoDB 4 本（削除保護 + Retain）とロググループ 8 件が残った**。KMS 鍵は `DELETE_COMPLETE` だが実際は 30 日の待機に入っただけ（P13）。手で削除して 0 件を確認 | 2026-09-13 |
| Nx Plugin for AWS | **実機 E2E**（データ層は未通過） | `deploy-sandbox` に `--rollback` を足して 317 秒。**2 スタック 86 リソース**（Application 81 + us-east-1 の Web ACL 5、synth 実測と一致） | Cognito User Pool（**MFA が既定で必須**なので TOTP を登録）→ Identity Pool → 一時認証情報 → SigV4 署名 → `AWS_IAM` の tRPC API に `GET /echo` で 200、`{"result":{"data":{"message":"..."}}}` を確認。**生成物に DynamoDB を読み書きする手続きがないため、テーブルは作られるが通っていない** | `destroy-sandbox` 292 秒、`DELETE_SKIPPED` 9 件（synth の 9 と一致）。**User Pool・DynamoDB 1 本・KMS 4 本・IAM ロール 2 本・ロググループ 7 件が残った**。P14 の順序で削除して 0 件を確認（KMS は 7 日で予定） | 2026-09-13 |

**Nx の区分に注釈が付く理由**: 生成直後の API は `echo` だけで、DynamoDB を読み書きする手続きが
ない。認証と API の経路は実機で通ったが、**データ層は「デプロイされた」までで「動いた」ではない。**
通すには人が手続きを書く（比較ドキュメントの「生成直後は動くアプリではない」と同じ話）。

実測した既定値も生きたリソースで確認した。Nx の User Pool は `UserPoolTier=PLUS`、
`MfaConfiguration=ON`、`DeletionProtection=ACTIVE`。**MFA が必須なので、最初のサインインが
TOTP の登録を要求する。** Blocks（production preset）の DynamoDB 4 本はすべて削除保護が有効で、
`todos` と `live-connections` だけ PITR 有効。**暗号化は AWS 管理キー**（`KeyManager=AWS`）で、
顧客管理 CMK は alarm topic 用の 1 本だけだった。

## 出典一覧

- [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) / [cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html) — `--express`、`--rollback`、`--hotswap` の性質
- [CloudFormation express mode](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-express-mode.html) / [DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)
- [AWS Blocks CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) / [concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) / [best practices](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html) / [getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)
- [DynamoDB: Using deletion protection](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html)
- [Cognito: Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html) / [Updating user pool and app client configuration](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-updating.html) — `UpdateUserPool` の全置換セマンティクス
- [KMS: Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html) / [KMS pricing](https://aws.amazon.com/kms/pricing/)
- [WAF: DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)
- [CloudFormation: DescribeStackEvents](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackEvents.html) / [ListStacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListStacks.html) — ページングと、削除済みスタックの 90 日
- [Lambda logs in CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [npm config: `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) — `npm create` の確認プロンプトの自動応答
- 上流の issue / PR: [nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265)（express target）、[#1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193)（advisory 取得の遅延）、[#1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228)（npm 11 前提）、[aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931)、[aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553)、[aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815)
- 生成物そのもの: `packages/infra/project.json`（Nx の target 定義）、`aws-blocks/index.cdk.ts` と `package.json`（Blocks のコマンドと preset）

> 内容は理解しやすさのために要約・再構成している。

## 関連ドキュメント

- [アプリの土台の選択肢](scaffolding-and-backend-toolkit-choices.md) — 3 者の位置づけ、synth までの実測、固定費
- [ポータルの検証結果](../../solutions/amplify-portal/docs/verification-results.md) — 検証区分の元になっている記録
- [portal-sandbox-lifecycle](../agent/portal-sandbox-lifecycle.md) — 同じロググループ残存をこのリポジトリのポータルで記録したもの（P10 の先例）
- [IaC ガバナンスパターン](../../solutions/amplify-portal/docs/iac-governance-patterns.md) — cdk-nag をベースライン比較として運用する理由、ドリフト検出の層
- [同じ 4 機能を 3 つの土台で実装した記録](portal-parity-four-features.md) — この文書の後片付けの手順が対象にしているスタックで、実際に 4 機能を動かした記録
