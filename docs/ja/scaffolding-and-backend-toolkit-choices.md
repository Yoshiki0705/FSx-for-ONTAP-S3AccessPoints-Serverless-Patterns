# フルスタック AWS アプリの土台の選択肢 — Nx Plugin for AWS / AWS Blocks / Amplify Gen 2

> 🌐 **Language / 言語**: 日本語 | [English](../en/scaffolding-and-backend-toolkit-choices.md)

## TL;DR

- 3 つは**同じ層のものではない**。Nx Plugin for AWS はモノレポの生成と実行管理、AWS Blocks は
  アプリコードから使うバックエンド機能の抽象、Amplify Gen 2 はバックエンド定義・開発 sandbox・
  ホスティングを一体で扱うプラットフォーム。置き換え関係ではなく、AWS の公式ドキュメントは
  Blocks と Amplify を相互補完（complementary）と明記している。
- **このリポジトリは Amplify Gen 2 を採用している。** ファイルポータル
  （`solutions/amplify-portal/`）が sandbox と Hosting で動いており、この文書はそれを
  「正式なデプロイパターンの 1 つ」として位置づけ、選定理由と乗り換えの条件を記録する。
- 同等の初期構成を 3 通りで作り、ローカル synth までを実測した（2026-09-07、AWS へのデプロイなし）。
  スターターの CloudFormation リソース数は **Amplify Gen 2: 79 / AWS Blocks: 83（sandbox
  preset）・117（production preset）/ Nx Plugin for AWS: 86**。桁は同じで、**差が出るのは
  リソース数ではなく既定値**。
- 既定値の差はそのまま**トラフィックに依存しない固定費**として現れる。実測した構成では
  Nx Plugin の生成物が WAF Web ACL 3 本・KMS CMK 4 本・Cognito の Plus プランを含み、
  ap-northeast-1 の公表単価で月 **$25〜** の固定費になる。Blocks の production preset は
  CMK 1 本で **$1**、Amplify のスターターは CMK も WAF も **$0**。どちらが良いかではなく、
  **本番の初期値としての厚みと、検証環境での後片付けやすさのどちらを先に取るか**の違い。
- 選び方は本文の[選び方](#選び方)にある。1 アプリを 1 回作るだけなら Nx の価値は出にくく、
  Website・API・Data・AI エージェント・IaC が増え続けるなら Nx の依存グラフが効く。
  ローカル完結の反復速度を最優先するなら Blocks（ただし preview）。バックエンド定義と
  認証・ホスティングを一体で運用したいなら Amplify Gen 2。

## この文書の範囲

**書くこと**: 3 つの位置づけの違い、同一手順で作った初期構成の実測値、生成される既定値の差、
その差が生む固定費、選定の条件、このリポジトリが Amplify Gen 2 を使っている理由。

**書かないこと**: どれが優れているかの結論。ベンチマーク（性能測定は行っていない）。
本番運用の実績比較（3 つのうち本番相当の運用実績があるのは、このリポジトリでは Amplify Gen 2
だけ）。AWS Blocks の GA 後の仕様（本文の測定は preview 時点）。

**対象読者**: これから AWS 上にフルスタックアプリの土台を選ぶ人。すでにどれかを使っていて、
別のものに移る判断材料が欲しい人。このリポジトリのポータルがなぜ Amplify Gen 2 なのかを
知りたい人。

## 3 つの位置づけ

| | 主に担当する範囲 | 成果物 | 状態（2026-09-07 時点） |
|---|---|---|---|
| Nx Plugin for AWS | モノレポの生成・プロジェクト間接続・実行順管理 | 通常の React / tRPC / ElectroDB / CDK コード | v1.0（2026-09 公開、OSS） |
| AWS Blocks | アプリコードから使うバックエンド機能の抽象（ローカル実装と AWS 実装の 2 面を持つ） | CDK アプリ。Block が実行時 API を持つ | **preview**（2026-06-17 発表、OSS） |
| Amplify Gen 2 | バックエンド定義・開発者 sandbox・ホスティングの一体運用 | TypeScript のバックエンド定義（`defineAuth` / `defineData`）と CDK | 一般提供 |

「置き換え関係ではない」ことは推測ではなく、AWS のドキュメントに書かれている。AWS Blocks の
概要ページは Amplify との関係を **complementary**（相互補完）と説明し、Amplify がホスティング・
CI/CD・マネージドなバックエンド体験を提供する一方で Blocks は型安全な infrastructure-from-code と
ローカル優先の開発に焦点を置くと整理している。Amplify のドキュメント側にも Blocks のページがある。

同じ理由で、Nx Plugin for AWS も Amplify や Blocks と排他ではない。Nx が管理するのは
「複数プロジェクトが同居するリポジトリの生成と実行順」で、生成されるのは通常の CDK コードである。

## このリポジトリの選択

**このリポジトリのファイルポータルは Amplify Gen 2 で作られており、正式なデプロイパターンの
1 つとして扱う。** 位置づけを明文化する理由は、`solutions/` の他のパターンが SAM/CloudFormation
テンプレート単体でデプロイできる形をしているのに対し、ポータルだけが Amplify の sandbox と
`amplify/backend.ts` の CDK という別の系統を使っており、その差が意図的なものだと分かる必要が
あるためである。

選定の理由は 3 つで、いずれもこのリポジトリの制約に固有のものである。

1. **認証が要件の中心にある。** ポータルは Cognito のグループを 2 軸（role と scope）で使い、
   AppSync の認可ルールがそのグループ名を参照する。`defineAuth` と `defineData` が
   グループとルールを 1 か所で扱えることが、この形をいちばん短く書ける。
2. **開発者ごとの sandbox が必要だった。** ONTAP の管理 LIF に届く VPC 内 Lambda を含むため、
   ローカルだけでは検証が閉じない。`ampx sandbox` の identifier ごとに独立した環境が作れる
   ことが、共有環境を壊さずに試す前提になっている。
3. **CDK への出口がある。** ポータルは FSx for ONTAP の S3 Access Point、Step Functions、
   Bedrock、DynamoDB を `backend.ts` の中で CDK として組んでいる。Amplify が管理する範囲の
   外側を CDK で書けることが必須だった。

**乗り換えを検討する条件**（このリポジトリの場合）:

- ポータル以外に Website や API が増え、プロジェクト間の依存と実行順が
  `package.json` のスクリプトで管理しきれなくなったとき → Nx Plugin for AWS の依存グラフ
- 認証を Cognito 以外に寄せる判断をしたとき → Blocks の `AuthBasic` / `AuthOIDC` が選択肢に入る
- ローカルだけで完結する反復が開発速度の支配要因になったとき → Blocks のローカル実装

現時点でどれも満たしていないため、乗り換えの計画はない。

## 実測

同じ初期構成（Web フロントエンド + API + データストア + 認証 + IaC）を 3 通りで作り、
**ローカルの synth まで**を実測した。**AWS へのデプロイは行っていない**ので、これはテンプレートの
実測であって稼働構成の実測ではない。

環境: macOS、Node.js v26.4.0、npm 11.17.0、2026-09-07 実施。

| | 生成手順 | スタック数 | CloudFormation リソース数 |
|---|---|---|---|
| Amplify Gen 2 | `npm create amplify`（`defineAuth` + `defineData` のスターター） | 5（ネスト含む） | **79** |
| AWS Blocks（preview） | `npm create @aws-blocks/blocks-app`（todo アプリ）、`BlocksPresets.sandbox` | 1 | **83** |
| AWS Blocks（preview） | 同上、`BlocksPresets.production` | 1 | **117** |
| Nx Plugin for AWS 1.0 | `ts#website` + `ts#website#auth` + `ts#api --framework=trpc` + `ts#dynamodb` + `connection` ×2 + `ts#infra`、生成された `echo` プロシージャのみ | 2 | **86** |

> **同じ物差しではない点**: 3 つのスターターが作るアプリは同一ではない（Amplify は
> GraphQL の Todo、Blocks は認証付き Todo、Nx は Welcome 画面と echo API）。ここで比べているのは
> 「公式の初期構成を作った直後にテンプレートに現れるリソースの規模」であり、
> 同一アプリを 3 通りで実装した比較ではない。

### Nx Plugin for AWS で分かったこと

- **`ts#infra` を実行した直後の `ApplicationStack` は空である。** その状態で synth すると
  テンプレートのリソースは 1 個（CDK メタデータ）だけになる。86 リソースになったのは、
  生成された Construct（`FeedbackWeb` / `FeedbackApi` / `FeedbackData` / `UserIdentity`）を
  `ApplicationStack` に配置し、IAM の付与と CORS を手で書いた後である。ジェネレーターは
  再利用可能な Construct を作るところまでを担当し、どれを採用してどう権限をつなぐかは
  設計判断として残る。
- Nx projects は 7 個（`common-constructs` / `common-scripts` / `common-shadcn` /
  `feedback-web` / `feedback-api` / `feedback-data` / `infra`）。
- `infra:synth` は依存する bundle・compile を先に実行する。nx の報告では 13 タスクで 5.1 秒
  （キャッシュ 7/13 ヒット時）。
- 業務用の Lambda は 1 本（`echo` プロシージャ）。テンプレート内の Lambda 7 本のうち残りは
  CDK のカスタムリソース。プロシージャを増やせば Lambda と API Gateway Method も増える構成である。

### 生成される既定値の差

固定費と後片付けに直結する項目だけを、実測したテンプレートから抜き出した。

| 項目 | Amplify Gen 2（スターター） | AWS Blocks（production preset） | Nx Plugin for AWS |
|---|---|---|---|
| WAF Web ACL | なし | なし | **3 本**（REGIONAL 2 + CLOUDFRONT 1）、各 2 マネージドルール |
| KMS カスタマー管理キー | なし | 1 本（アラーム用 SNS） | **4 本**、いずれも自動ローテーション有効 |
| 認証 | Cognito User Pool。`UserPoolTier` 未設定（= 既定の `ESSENTIALS`） | `AuthBasic`（DynamoDB + JWT）。Cognito を使わない | Cognito User Pool。**`UserPoolTier: PLUS`**、MFA `ON`、脅威保護 `AUDIT` |
| User Pool の削除保護 | 未設定 | — | `ACTIVE` |
| DynamoDB | `Custom::AmplifyDynamoDBTable` 経由 | 4 テーブル。全て削除保護 + `Retain`。業務用 2 本は PITR + SSE、認証用 2 本は PITR/SSE なし | 1 テーブル。PITR + 削除保護 + CMK による SSE + GSI 2 本 + `Retain` |
| S3 バケットの `DeletionPolicy` | `Delete`（スターター） | `Delete` | — |
| 匿名テレメトリ | 既定で有効（`ampx configure telemetry disable` で無効化） | 既定で有効（`AWS_BLOCKS_DISABLE_TELEMETRY=1` で無効化） | （測定していない） |

読み方は「厚い方が良い」でも「薄い方が良い」でもない。**Nx Plugin の既定は本番の出発点として
心強く、短期の検証環境では削除保護と `Retain` が後片付けを難しくする。** Amplify のスターターの
既定は逆で、消しやすいが本番前に足す作業が残る。Blocks は preset で切り替える形にしていて、
sandbox と production で 83 と 117 に分かれる。

## 固定費の差

上の既定値のうち、**トラフィックがゼロでも発生する分**を公表単価で並べた。

出典は AWS Price List API、リージョン **ap-northeast-1**、取得日 **2026-09-07**
（API の `publicationDate` は 2026-09-11、Cognito の料金は 2026-08-01 発効）。

| 項目 | 単価 |
|---|---|
| WAF Web ACL | $5.00 / 月（ap-northeast-1、us-east-1 も同額） |
| WAF ルール | $1.00 / 月 |
| WAF リクエスト処理 | $0.60 / 百万リクエスト |
| KMS カスタマー管理キー | $1.00 / 月。**ローテーションは 1 回目と 2 回目が各 +$1.00 / 月で、2 回目で上限**（3 回目以降は課金されない） |
| Cognito MAU（Lite） | $0.0055（最初の 90,000 MAU） |
| Cognito MAU（Essentials） | $0.015 |
| Cognito MAU（Plus） | $0.020 |

これを、**月間 1,000 認証ユーザー・トラフィックなし**という前提に当てはめたサンプル試算:

| | WAF | KMS | Cognito（1,000 MAU） | 合計 |
|---|---|---|---|---|
| Amplify Gen 2（スターター） | $0 | $0 | $15.00（Essentials） | **$15.00** |
| AWS Blocks（production preset） | $0 | $1.00 | $0（Cognito 非使用） | **$1.00** |
| Nx Plugin for AWS | $21.00（ACL 3 × $5 + ルール 6 × $1） | $4.00 → ローテーション 2 回後は最大 $12.00 | $20.00（Plus） | **$45.00 → 最大 $53.00** |

> **これはサンプル前提の試算であって本番見積りではない。** Lambda・API Gateway・DynamoDB・
> CloudFront・S3・Bedrock などトラフィックに比例する費用、CloudWatch Logs の保存、
> データ転送、無料利用枠、Savings Plans、EDP などの割引は含まない。実際の請求はワークロードで
> 決まる。ここで示したのは「初期値の違いが、使わなくても毎月出続ける額としていくらの差になるか」
> だけである。
>
> Cognito の無料利用枠は適用していない。新規アカウントでは上の額より小さくなる場合がある。

固定費の観点で押さえるべき点:

- **KMS のローテーションは無限に増えない。** 2 回目のローテーションで上限に達するので、
  自動ローテーション有効の CMK は最終的に $3.00 / 月に落ち着く。年次ローテーションなら
  4 本で $4 → $8 → $12 と 2 年かけて増え、そこで止まる。
- **CloudFront スコープの Web ACL は us-east-1 で作成される**が、公表単価は同額である。
- **Cognito の `UserPoolTier` を明示しない場合の既定は `ESSENTIALS`**（AWS ドキュメントで確認）。
  Nx Plugin の生成物が `PLUS` を明示するのは、脅威保護などの機能を有効にするためであり、
  1,000 MAU では月 $5、10,000 MAU では月 $50 の差になる。要件次第で下げられる。

## 選び方

条件が 1 つでも当てはまるものを起点にする。複数当てはまる場合は、組み合わせられる
（3 つは排他ではない）。

**Nx Plugin for AWS が効く条件**

- Website・API・Data・AI エージェント・MCP サーバー・CDK / Terraform が**同じリポジトリで
  増え続ける**見込みがある
- 「何が何に依存し、どの順で実行するか」を個別のシェルスクリプトではなく
  依存グラフで管理したい
- 生成されたコードを自分たちの保守対象として引き受けられる（独自形式ではなく通常の
  React / TypeScript / CDK が残るのは利点だが、更新方針は自分で決める必要がある）

**逆に効きにくい条件**: 1 アプリを 1 回生成するだけ。その場合、Nx の依存グラフが解く問題が
まだ発生していない。

**AWS Blocks が効く条件**

- **AWS アカウントなしのローカル反復**が開発速度の支配要因
- バックエンドの機能単位（KV ストア、テーブル、リアルタイム、ジョブ、エージェント）を
  アプリコードから型付きで呼びたい
- **preview であることを受け入れられる**。仕様変更の可能性があり、公式ドキュメントは
  Block ID の変更が stateful な Block のリソース削除と再作成を引き起こし、**永久的な
  データ損失**になると明記している（Block ID はデプロイ後は不変として扱う）

**Amplify Gen 2 が効く条件**

- 認証（Cognito のグループ、外部 IdP、MFA）が要件の中心にある
- 開発者ごとの sandbox 環境が必要
- フロントエンドのホスティングまで同じ枠組みで扱いたい
- Amplify が管理する範囲の外側を CDK で書く必要がある（`defineBackend()` の戻り値から
  CDK スタックに触れる）

**逆に効きにくい条件**: 複数の独立したアプリを 1 リポジトリで並行して育てる形。Amplify の
sandbox はバックエンド 1 つを単位にするので、プロジェクト間の実行順の管理は別途必要になる。

## トレードオフ

推奨する側の制約も含めて対称に並べる。

| | 利点 | トレードオフ |
|---|---|---|
| Nx Plugin for AWS | 本番寄りの既定値（WAF・KMS・削除保護・可観測性）が最初から入る。プロジェクトが増えても依存と実行順を保てる。生成物は通常の React / CDK | 生成直後は動くアプリではない（Welcome 画面・echo・サンプル Entity）。IaC の最終配線は設計判断として残る。固定費が最も高い。検証環境では削除保護と `Retain` が後片付けを難しくする。生成コードの更新方針を自分で決める必要がある |
| AWS Blocks | AWS アカウントなしでアプリ全体がローカルで動く。型がバックエンドから UI まで通る。CDK に降りられる。Amplify や既存 CDK と併用できる | **preview**。Block ID の変更が stateful な Block の永久的なデータ損失になる。ローカル実装と AWS 実装は同一ではないので結合確認は別途必要。既定でテレメトリが有効 |
| Amplify Gen 2 | バックエンド定義・sandbox・ホスティングが一体。認証とデータの認可を 1 か所で書ける。CDK への出口がある。このリポジトリで本番相当の運用実績がある | 既存の Cognito User Pool を CloudFormation から更新しようとした 2026-08-27 の試行は Cognito 側に拒否され、回避策として新規作成すると既存ユーザーが失われた（記録と再現条件は下記の設計判断ガイド）。失敗した sandbox は作られたリソースを残したまま停止する。cdk-nag の findings に Amplify 管理リソース由来のものが含まれるため、合否のゲートではなくベースライン比較として運用する。既定でテレメトリが有効 |

Amplify Gen 2 側のトレードオフの詳細は
[Amplify Gen2 + CDK 設計判断ガイド](../../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.md) と
[IaC ガバナンスパターン](../../solutions/amplify-portal/docs/iac-governance-patterns.md) にある。

## 実測の再現手順

同じ数字を自分の環境で出すための手順。**いずれも AWS へのデプロイを行わない**（synth のみ）。

```bash
# Nx Plugin for AWS
#   npm 経由の `npm create @aws/nx-workspace` は出力なしで停止したため pnpm 経由で実行する
npx --yes pnpm@10 create @aws/nx-workspace@1.0.0 research-board \
  --interactive=false --pm=pnpm --nxCloud=skip --skipGit --aiAgents=none
cd research-board
NX=node_modules/.bin/nx          # `npx pnpm` はバージョン確認のプロンプトで停止する
$NX g @aws/nx-plugin:ts#website feedback-web --no-interactive
$NX g @aws/nx-plugin:ts#website#auth --project=@research-board/feedback-web --no-interactive
$NX g @aws/nx-plugin:ts#api feedback-api --framework=trpc --no-interactive
$NX g @aws/nx-plugin:ts#dynamodb feedback-data --no-interactive
$NX g @aws/nx-plugin:connection --sourceProject=@research-board/feedback-web \
  --targetProject=@research-board/feedback-api --no-interactive
$NX g @aws/nx-plugin:connection --sourceProject=@research-board/feedback-api \
  --targetProject=@research-board/feedback-data --no-interactive
$NX g @aws/nx-plugin:ts#infra infra --no-interactive
# ここで ApplicationStack に Construct を配置する（空のままでは 1 リソースしか出ない）
NX_TUI=false $NX sync && NX_TUI=false $NX run @research-board/infra:synth
```

```bash
# AWS Blocks（preview）
npm create @aws-blocks/blocks-app@latest my-todo-app
cd my-todo-app && npm install
npx --yes aws-cdk synth --context sandboxMode=true --output out-sandbox --quiet
npx --yes aws-cdk synth --output out-prod --quiet
```

```bash
# Amplify Gen 2
npm create amplify@latest
CDK_OUTDIR=out CDK_CONTEXT_JSON='{"amplify-backend-name":"probe","amplify-backend-namespace":"probe","amplify-backend-type":"sandbox"}' \
  npx --yes tsx amplify/backend.ts
```

リソース数の数え方（テンプレートの `Resources` のキー数を合計する）:

```bash
find <出力ディレクトリ> -name '*.template.json' -exec node -e \
  'const t=require(process.argv[1]);console.log(Object.keys(t.Resources||{}).length)' {} \;
```

このリポジトリのポータルを同じ方法で synth する場合は `make -C solutions/amplify-portal nag`
相当の `npm run nag` を使う。コミットされた `portal-config.example.ts` に対して synth し、
AWS へは何も送らない。

## FAQ

**Q. 3 つのどれかに決めなければならないのか。**
いいえ。AWS のドキュメントは Blocks と Amplify を相互補完と説明しており、Blocks のアプリは
CDK アプリなので既存の CDK スタックに埋め込める。Nx Plugin が生成するのも通常の CDK である。
実務では「Nx でリポジトリを構成し、その中の 1 プロジェクトが Amplify Gen 2」のような形も取れる。

**Q. リソース数が少ない方が良いのか。**
判断材料の 1 つにすぎない。79 と 117 の差の大半は既定で入る保護（暗号化、監視、ホスティング）
であり、少ない方は後で足す作業が残る。見るべきは数ではなく、**その既定値が自組織の標準と
一致しているか**である。

**Q. このリポジトリのポータルは 472 リソースだが、Amplify が重いということか。**
違う。ポータルは業務アプリで、AppSync のリゾルバ 78 個、Lambda 24 個、DynamoDB 6 テーブルを
持つ。スターター（79 リソース）と比べる対象ではない。**472 という数字はスターター比較の行に
入れてはいけない**、という注意のためにここに書いている。

**Q. Nx Plugin の Cognito Plus プランは下げられるのか。**
生成された Construct の設定なので変更できる。ただし脅威保護など Plus でしか使えない機能が
既定で有効になっているため、下げるなら何を失うかを確認してから決める。生成されたから採用する
のではなく、初期値をレビューする対象として扱う。

**Q. AWS Blocks を本番で使ってよいか。**
2026-09-07 時点で preview である。公式ドキュメントが Block ID の変更を永久的なデータ損失として
警告している点も含め、preview の前提を受け入れられるかで判断する。このリポジトリでは
本番相当の用途に採用していない。

## 出典

- [AWS announces Nx Plugin for AWS for scaffolding full-stack applications](https://aws.amazon.com/about-aws/whats-new/2026/09/nx-plugin-for-aws/)（What's New、2026-09）
- [awslabs/nx-plugin-for-aws](https://github.com/awslabs/nx-plugin-for-aws) と
  [ドキュメント](https://awslabs.github.io/nx-plugin-for-aws/)
- [What is AWS Blocks?](https://docs.aws.amazon.com/blocks/latest/devguide/what-is-blocks.html)、
  [Getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)、
  [AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)（Block ID の不変性）
- [AWS Blocks (preview) の発表](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-blocks-preview/)（2026-06-17）
- [AWS Amplify Gen 2 ドキュメント](https://docs.amplify.aws/) と
  [Amplify から見た AWS Blocks](https://docs.amplify.aws/nextjs/build-a-backend/aws-blocks/)
- [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/)（ローテーション課金の上限）
- [Cost and billing management best practices for AWS KMS](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-kms-best-practices/cost.html)
- `UserPoolTier` の既定値が `ESSENTIALS` であること:
  [AWS CDK API リファレンス（CfnUserPoolProps）](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cognito-readme.html)
- 単価は AWS Price List API から 2026-09-07 に取得（ap-northeast-1）
- Nx Plugin for AWS を実際に生成して検証した記事: AWS Japan のソリューションアーキテクトによる
  [AWSアプリ開発の初手が変わる？ Nx Plugin for AWSは何を自動化し、何を人に残すのか](https://zenn.dev/aws_japan/articles/nx-plugin-for-aws-nx-explained)。
  ジェネレーターの役割分担、`connection` が組み合わせごとに異なること、生成コードの保守が
  自分たちの責任になることの整理は同記事による。本文の数値は当リポジトリで独自に測定したもので、
  構成が異なるため同記事の数値とは一致しない（同記事は 3 プロシージャを実装した状態、本文は
  生成された `echo` のみ）。

> 内容は理解しやすさのために要約・再構成している。

## 関連ドキュメント

- [Amplify Gen2 + CDK 設計判断ガイド](../../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.md) — `backend.ts` の内と外の切り分け
- [IaC ガバナンスパターン](../../solutions/amplify-portal/docs/iac-governance-patterns.md) — cdk-nag をゲートにできない理由、alpha モジュール方針
- [ポータルの Getting Started](../../solutions/amplify-portal/docs/GETTING-STARTED.md) — 他環境でのデプロイ手順
- [PoC から本番への移行](portal-poc-to-production.md) — sandbox 構成を本番に寄せる手順
