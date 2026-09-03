# ポータル sandbox の同居と後始末の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/portal-sandbox-lifecycle.md` が読み込み条件だけを持ち、該当する作業を
> しているときにこの内容へ誘導する。`.kiro/` は公開しないため、知識の本体は常にこちら側に置く。

対象は「同一 VPC に sandbox が複数ある状態」と「不要になった sandbox を消す作業」。
CDK コードそのものの罠は [portal-cdk-quality-gates](portal-cdk-quality-gates.md) にある。

## DynamoDB Gateway エンドポイントの単一所有と、所有者削除の波及

route table は prefix list ごとに route を 1 本しか持てない。そのため同一 VPC で 2 つ目の
sandbox が同じ route table にエンドポイントを作ろうとすると、

```
route table rtb-... already has a route with destination-prefix-list-id pl-...
```

で拒否され、他が正常に作られた後に data スタックがロールバックする。

`backend.ts` はこれを避けるため、`config.dynamoDbGatewayEndpointExists` が真のときは
エンドポイントを作らない。**2026-09-02 まで既定値は真**で、後から立てたスタックは
「誰かが所有している」前提で動いていた。所有者への参照は CloudFormation のどこにも現れない。

**実測 2026-09-02**: 最初に立てた sandbox を残骸として削除したところ、エンドポイントが
一緒に消え、**現役スタックの VPC Lambda が DynamoDB へ到達できなくなった**。封じ込めブロックの
期限切れ sweep が 3 回連続で失敗した。

```
sweep could not read the ledger: ConnectTimeoutError:
  Connect timeout on endpoint URL: "https://dynamodb.<region>.amazonaws.com/"
```

Lambda の呼び出しは成功し、EventBridge の `FailedInvocations` も 0 のままなので、
**メトリクスだけ見ていると気づかない**。気づけるのはハンドラが出すこのログと
`SweepFailures` である。

復旧はエンドポイントを作り直すだけ。

```bash
aws ec2 create-vpc-endpoint --region <region> \
  --vpc-id <vpc-id> --vpc-endpoint-type Gateway \
  --service-name com.amazonaws.<region>.dynamodb \
  --route-table-ids <rtb-id>
```

作り直した直後の `describe-route-tables` は反映前の内容を返すことがある。route の実在は
数秒おいて再確認する。

**既定値は 2026-09-02 に偽（このスタックが所有する）へ変えた。** 借りる既定は、貸し手が消えた
ときに黙って壊れ、走り続けているのは借り手の側である。同一 VPC に 2 つ目を立てるときだけ
`AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1` を渡す。

所有者を移すには、先に既存のエンドポイントを消してからデプロイする。順序を逆にすると
route が衝突して data スタックがロールバックする。移行中は VPC Lambda から DynamoDB へ
到達できないので、封じ込めブロックが 0 件の時間帯を選ぶ。

**予防**: 設定と実状の食い違いは preflight が落とす。デプロイ前に走らせる。

```bash
python3 scripts/portal_preflight.py     # DynamoDB route の行を見る
```

判定は「route があるか」ではなく**誰が所有しているか**で行う。2026-09-02 まではこの検査が
「prefix-list route が 1 本でもあるか」を見ており、S3 の gateway エンドポイントが同じ
route table に route を置くので**常に真**だった。つまり所有者を消してエンドポイントが
消えた後も `OK` を返し続け、検出すべき唯一の障害を通していた。所有者まで見ないと
「他スタックのを借りている（`true` が正しい）」と「自分が持っている（`false` が正しい）」も
区別できず、後者で `true` を宣言すると次のデプロイが自分の依存を消す。

`dynamoDbGatewayEndpointExists` を書き換えるときは `config_bool` が読める形
（`=== "1"` / `!== "0"` / 素の `true` `false`）を保つ。ヘルパー呼び出しに変えると
このチェックは `SKIP` になり、**設定ミスを検出しないまま通る**。

`describe-vpc-endpoints` に `route-table-id` フィルタは無い（`InvalidFilter` が返る）。
route table の突合はレスポンスの `RouteTableIds` に対してクライアント側で行う。

スタックを消す前と後には、残す側の関数に対して次も走らせる。gateway エンドポイントが対象
サブネットの route table を覆っているかまで見るので、消えれば `dynamodb` が `ok` から落ちる。

```bash
python3 scripts/portal-probes/diagnose_vpc_egress.py --function ArpResponseFun
```

## identifier 省略による 2 つ目の暗黙作成

`npx ampx sandbox` は `--identifier` を省略すると **OS のユーザー名から identifier を決める**。
これは `amplify_outputs.json` が指している sandbox とは無関係なので、`demo` に対して作業する
つもりの素の `npm start` が `yoshiki` sandbox の**新規作成**になる。identifier はディスク上の
どこにも記録されておらず、CLI の出力に出るまで分からない。

**実測 2026-09-03**: `npm start` が `yoshiki` sandbox を作りに行き、auth スタックの Cognito
User Pool と data スタックの Lambda 約 25 個を作った後、上の route 衝突で
`DynamoDbGatewayEndpoint` が `CREATE_FAILED` になった。

**sandbox はロールバックしない。** これが「失敗したから元に戻った」と読み違えやすい点で、
GETTING-STARTED には 2026-09-03 まで「スタックごとロールバックします」と書いてあった。実際は
`CREATE_FAILED` で停止して作られたリソースが残るため、`aws cloudformation delete-stack` を
明示的に呼ぶ必要がある。

被害が既存環境に及ばなかったのは、**失敗したのが新規作成側だった**ためである。`demo` が所有する
エンドポイントには触れておらず、`amplify_outputs.json` も上書きされていない（sandbox が
outputs を書く段階に到達せずに落ちた）。順序が逆——既存側が所有権を手放す形——だと
2026-09-02 の事故になる。

**対策**: リポジトリの入口はすべて `solutions/amplify-portal/scripts/sandbox.sh` を経由し、
identifier をデプロイ済みの実物から解決して明示的に渡す（`npm start` / `make sandbox` /
`make sandbox-watch` / `make sandbox-delete`）。解決は
`portal_preflight.py --print-sandbox-identifier` で、outputs が指すプール →
CloudFormation のスタック → identifier とたどる。ファイル名や設定リテラルではなく
デプロイ済み状態を読むのは、identifier がどこにも書かれていないからである。

outputs が無い場合（初回）は exit 3 を返して CLI の既定に委ねる。衝突する相手がまだ
存在しないので既定が正しい。outputs があるのに解決できない場合は exit 1 で**止める**。
ここで既定にフォールバックすると、防ぎたい事故そのものを起こす。

意図して 2 つ目を立てるときは両方を渡す。片方だけでは route 衝突で落ちる。

```bash
AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1 \
  AMPLIFY_PORTAL_SANDBOX_IDENTIFIER=<second> make sandbox
```

## `list-exports` に現れない依存の存在

上がその実例。削除前に「残骸スタック発の CloudFormation export は 0 件」を確認して依存なしと
判断したが、壊れた。**export の不在は依存の不在ではない。**

VPC エンドポイント・route・セキュリティグループルールのように「VPC に属し、CloudFormation
からは参照されず、消えると他が黙って壊れる」資源は export に現れない。同一 VPC を共有する
スタックを消す前に、消える側が持つ VPC レベルの資源を型ごとに数える。

```bash
aws cloudformation list-stack-resources --stack-name <消す側> \
  --query "StackResourceSummaries[?starts_with(ResourceType,'AWS::EC2::')].[ResourceType,PhysicalResourceId]" \
  --output text
```

`AWS::EC2::VPCEndpoint` / `AWS::EC2::Route` / `AWS::EC2::SecurityGroupIngress` が 1 件でも
あれば、それは他のスタックが暗黙に使っている可能性がある。

## VPC Lambda の ENI 解放待ち

VPC に接続した Lambda を含むスタックの削除は、ENI が外れるまで進まない。実測で 28 分。
`DELETE_IN_PROGRESS` が 20 分以上続いても、ネストスタックの残存リソースが
`AWS::Lambda::Function` の `DELETE_IN_PROGRESS` 1 件なら待てばよい。

```bash
aws cloudformation list-stack-resources --stack-name <nested-data-stack> \
  --query "StackResourceSummaries[?ResourceStatus!='DELETE_COMPLETE'].[LogicalResourceId,ResourceType,ResourceStatus]" \
  --output text
```

`UPDATE_FAILED` のスタックでも削除自体は通る。更新が失敗した原因（実例では
`amplifyAuthUserPool` の更新失敗）は削除の妨げにならない。

## retention 無期限で作られる log group の増殖

`backend.ts` の `lambda.Function` は `logRetention` も `logGroup` も指定していないので、
log group は Lambda が既定（無期限）で作る。sandbox の再デプロイで関数が置換されると
**新しいサフィックスの log group が無期限で追加され、古い方は関数が消えても残る**。

**実測 2026-09-02**: ポータル関連の log group が 101 個あり、うち 92 個（9.0 MB）は対応する
Lambda が存在せず、すべて retention 無期限だった。

孤児の判定は log group 名と実在する関数名の突き合わせで行う（`/aws/lambda/` を除いた残りが
関数名）。retention は現役分に当てる。

```bash
aws logs put-retention-policy --log-group-name <lg> --retention-in-days 90
```

**CDK 側で解決していない理由**: `logRetention` は aws-cdk-lib 2.263 で非推奨であり、かつ
`Custom::LogRetention` のカスタムリソースが増えて `security/cdk-nag-baseline.txt` の既知
findings が動く。`logGroup:` で明示すると log group 名が生成名になるため既存分が孤児になる。
どちらも「retention を入れる」より影響が大きいので、現状は手で当てる運用にしている。

## 削除前に確定すべきデータ件数

sandbox の DynamoDB テーブルは Amplify の TableManager が作るため、テーブル名には
スタック名ではなく AppSync の API id が入る（`Favorite-<apiId>-NONE`）。スタック名で
`list-tables` を絞ると**これらが見えないまま消える**。

API id で束ねて、現役の API id 以外を残骸として扱う。

```bash
aws appsync list-graphql-apis --query "graphqlApis[].[apiId,name]" --output text
aws dynamodb list-tables --query "TableNames[]" --output text | tr '\t' '\n' | grep -- '-NONE$'
```
