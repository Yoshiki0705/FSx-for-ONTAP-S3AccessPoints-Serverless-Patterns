# ポータル CDK / 品質ゲートの罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/portal-cdk-quality-gates.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| ポータルの Lambda が `shared/` を import できない | `functions/<name>/` の asset にはそのディレクトリしか入らない。`shared.*` を使う関数には `amplify/backend.ts` の `SharedPythonLayer` を `layers:` で付与する。レイヤーは `/opt` にマウントされ Python が見るのは `/opt/python` なので、アーカイブに `python/` プレフィックスが必要（`Code.fromAsset` の `bundling.local` で再配置している） |
| `shared/` を変更しても sandbox のレイヤーが更新されない | `ampx sandbox` は hotswap で Lambda を更新し、LayerVersion の内容変更をスキップする（無効化フラグは無い）。テンプレートに変更がある場合のみ CFn が走る。下の論理 ID 対策で作成扱いにすれば飛ばされない |
| **`shared/` がずれた sandbox では、無関係な変更のデプロイも失敗する** | hotswap でレイヤーが飛ばされ続けると deployed layer と作業ツリーの `shared/` がずれる。次に**テンプレートに変更がある**デプロイで CFn が走り、置換になって `Replacement type updates not supported on stack with disable-rollback` で拒否され、スタックは `UPDATE_FAILED` で残る。**失敗したのは自分の変更ではない**。下の論理 ID 対策を入れてあればこのずれ自体が起きない |
| **LayerVersion は論理 ID にフィンガープリントを入れて「置換」を避ける** | 内容が変わった LayerVersion は置換になり、`DisableRollback=true` の sandbox では拒否される。論理 ID に含めれば別リソースなので作成 + 削除になり、作成は disable-rollback でも通る。**作成は hotswap で飛ばせない**のでずれも起きず、ARN で一致を確認できる（`SharedPythonLayer4dc7cbd5285c…`）。両レイヤーに適用済み |
| **`ampx` は失敗しても exit 0 を返す。デプロイの判定に使ってはいけない** | 2 例。(a) `UPDATE_FAILED` のまま `--once` を打つと `✔ Deployment completed in 2.574 seconds` と表示して終わるが、スタックは `UPDATE_FAILED` のまま Lambda のコードも古い（終わる理由は下の「`UPDATE_FAILED` の関数」の行）。(b) `sandbox delete` 直後の再デプロイは削除済みスタックを指すローカルキャッシュのため `StackNotFound` で落ちる。**判定は `describe-stacks` の `StackStatus` と、対象関数の `LastModified`（`get-function-configuration`）で行う。** (b) は `rm -rf solutions/amplify-portal/.amplify/artifacts/cdk.out` で通るので、**削除〜再作成は 3 手順**（`delete` / キャッシュ削除 / `--once`）になる |
| `UPDATE_FAILED` からの復旧 API は両方使えない | `continue-update-rollback` は `cannot be called from stack with UPDATE_FAILED status`、`rollback-stack` は `not supported for stacks that were last updated using EXPRESS deployment mode` を返す。CFn の案内は「last known stable template で UpdateStack」だが `ampx` にその手段はなく、実際の復旧は `sandbox delete` → 再作成のみ。**Cognito ユーザーと DynamoDB が消える**ので、上の行の手順で消える対象を件数付きで先に確定する。**ただし削除の前に、落ちたリソースの論理 ID を変えて置換を回避できないか見る**。`UPDATE_FAILED` からでも作成 + 削除なら通る（実例: 下の対策だけで復旧した） |
| `DisableRollback=true` で `UPDATE_FAILED` のとき、成功したリソースは適用済みで残る | ロールバックが無効なので、置換で落ちたリソース以外の更新は生きている。実例: IAM ポリシーの修正は反映され（`aws iam get-role-policy` で確認）、同じデプロイの LayerVersion だけが失敗した。「デプロイが失敗した」から「何も変わっていない」を導かない。反映されたかは**スタックのステータスではなくリソースを直接見て**判定する |
| **認可規則が参照する Cognito グループが IaC に無い** | `amplify/data/resource.ts` の `allow.groups(["storage-admin"])` は、そのグループが存在しない場合でも synth もデプロイも通る。`defineAuth` に `groups` を書き忘れると、**長く動いている sandbox には手作業で作られたグループが残っているので動き、新規デプロイでは管理セクションが丸ごと消える**。しかも失敗ではなくセクションの非表示として現れるため「まだ実装されていない」ように見える。実例: 再作成した sandbox で「リソース管理」「分析」が消え、`aws cognito-idp list-groups` が空だった。認可で参照する名前は `amplify/auth/resource.ts` の `groups` に必ず宣言する（所属付与は引き続き `admin-add-user-to-group` で個別に行う） |
| 長く動いている sandbox は「手作業で足したもの」を隠し持つ | 上のグループがまさにそれ。**IaC の欠落は、既存環境では症状が出ない**。`ampx sandbox delete` → 再デプロイは、この種の欠落を洗い出す唯一の確実な方法である一方で Cognito ユーザーと DynamoDB を消す。実行前に、消える対象を件数付きで確定し、DynamoDB を `scan` してバックアップし、owner 系フィールドは**新しい sub へ付け替えてから**戻す（旧 sub のまま戻すと owner スコープの認可で誰からも見えなくなる） |
| **`GROUP_PATH_PREFIXES` を「設定した」ことと「効いている」ことは別** | このプレフィックスがマルチテナント境界だが、`functions/list-files` では**フォルダー監視の受信箱にしか適用されていなかった**。`renameFile` / `trashFile` / `restoreFromTrash` / `createUploadLink` と `listFiles` はキーを未検査で受けており、他チームのキーを直接指定すれば操作でき、他チームの prefix への署名付き PUT も発行できた。エンドポイントは認証済みなので、認可が抜けていても誰も気づかない。**キーを取る操作を追加するときは、境界を通る経路に載っているかをテストで固定する**（`functions/list-files/tests/test_write_guardrails.py`）。境界のコードを無効化してテストが落ちることを確認するまで、そのテストは境界を守っていない |
| コピー系の宛先チェックが無いと、データ破壊が「成功」として返る | `copy_object` は宛先の既存オブジェクトを黙って上書きする。`renameFile` は既存キーへの改名で相手を消していた。宛先の存在確認は `head_object` で行い、`overwrite` を明示しない限り拒否する。なお `head_object` は「無い」と「権限が無い」を区別できないが、権限が無ければ続く copy も失敗するので、判定を誤って上書きすることはない |
| **`s3:CopyObject` を IAM ポリシーに書いても何も許可されない** | そんなアクションは存在しない。`copy_object` が要求するのは source の `s3:GetObject` と **`s3:GetObjectTagging`**、destination の `s3:PutObject` と `s3:PutObjectTagging`。実例: ポータルの list-files ロールに `s3:CopyObject` が書かれていて `GetObjectTagging` が無く、**名前の変更とごみ箱からの復元が AccessDenied で常に失敗していた**。同じロールでの**ごみ箱への移動は成功していた**（同一 source・同一バケットでも要求されないケースがある）ため、最初に試した操作が通ってしまい欠陥が残った。copy を含む経路は**往復の両方向**を実際に叩いて確認する |
| 例外メッセージからエラー原因を推測する実装 | `str(IndexError(4))` は `"4"` で HTTP 404 に見える。実際に `Path(__file__).parents[4]`（Lambda では親が 3 つ）の IndexError を「CIFS 未設定」と誤報告していた。`type(e).__name__` を含めて報告し、文字列パターンで原因を決めない |
| **AwsCliLayer の置換が Express の sandbox で拒否される** | `@aws-cdk/asset-awscli-v1` の更新で層の `Content.S3Key` が変わると、論理 ID が内容を含まないため置換になる（既存 sandbox の更新のみ）。デプロイ後に `UPDATE_FAILED`（`ampx` は終了コード 0）。no mitigation applied; follow-up issue to be filed |
| **`UPDATE_FAILED` の関数は `description` の変更だけでは更新されず、`make sandbox` を再実行しても変わらない** | 観測（verified、1 観測、ap-northeast-1）: `description` に印を足した `--once` を 2 回実行した。どちらも `Updated AWS::Lambda::Function` と約 3.5 秒の `Deployment completed in` を表示し、スタックのイベントは 0 件。更新に失敗していた関数の `VpcConfig` と ONTAP の環境変数は空のままだった。理由（hypothesis）: `ampx sandbox` は差分が Lambda の `description` や環境変数だけのとき、CloudFormation を通さず Lambda API で直接反映する（hotswap）と読める。`cdk deploy --hotswap` の文書は、Lambda の設定変更で対象になるのは `description` と環境変数だけで、対象外の変更は無視され、CloudFormation にドリフトを作ると書く（documented: [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)）。`UPDATE_FAILED` のスタックが保持するテンプレートには失敗した更新の新しい定義が入っているので、`ampx` が作る差分に現れるのは `description` だけになり、`VpcConfig` は差分に出ない、と読める。`ampx` の実装は読んでいない。ロックファイルの `@aws-amplify/backend-cli` は 1.10.0 で、観測時に実行したバージョンは記録していない。**更新後の判定は `describe-stacks` の `StackStatus` ではなく、`get-function-configuration` の `VpcConfig` と環境変数で行う。** 強制: `make portal-preflight` の `VPC wiring`（`backend.ts` で VPC に入る関数ごとに論理 ID で FAIL にする。変更 1） |
| **CloudFormation の更新を起こす変更の例と限界** | 例（verified、1 観測、ap-northeast-1）: データスタックに `CfnOutput` を 1 つ足して `--once`、削除してもう 1 回 `--once`。出力の追加と削除は上の hotswap 対象の一覧になく、CloudFormation の更新になる。結果: 直前の実行で `UPDATE_FAILED` だった 2 関数が更新され（VPC 配線、ONTAP の環境変数、共有レイヤーが反映）、3 スタックが `UPDATE_COMPLETE` になり、失敗イベントは 0 件。同じ更新で、失敗していない関数を含む Lambda 24 件と IAM ロール 25 件も更新された（未完了の更新をまとめて処理したと読める。hypothesis）。限界: 失敗したリソースが再試行されるかは、リソースの型と失敗の原因による。1 観測を一般則にしない。置換が拒否された LayerVersion はこの方法では直らず、論理 ID の変更が要る（上の行）。 強制: `make portal-preflight` の `VPC wiring` が、更新後に VPC に入るはずの 3 関数を `M of N expected function(s) conform` で数える（変更 1）。M が N に届かなければ、更新は届いていない |
| **VPC に入る Lambda の更新が、実行ロールへ VPC 実行ポリシーを付けた直後に `CreateNetworkInterface` の権限エラーで失敗することがある** | 観測（verified、1 観測、ap-northeast-1）: ポリシー付与の 3〜4 秒後に始まった更新が 2 関数で失敗し、別の関数の更新は約 19 秒後に成功した。再現率は未測定。IAM の反映待ちが原因かは未確認（hypothesis）。復旧は、ロールが整った後に CloudFormation の更新を起こし直す（上の行）。 強制: 失敗した関数は VPC 配線なし・ONTAP の環境変数が空のまま残るので、`make portal-preflight` の `VPC wiring` が FAIL にする（変更 1） |
| **`portal-config.ts` は作業ツリーごとの gitignore 対象で、共有 sandbox の実効設定は「デプロイを打った作業ツリーのそれ」になる** | 別の作業ツリーで example をコピーしただけの（値がすべて空の）設定から `make sandbox` を打つと、稼働中の S3 Access Points のエイリアス（`S3_AP_ALIAS`）、ONTAP の接続（`ONTAP_MGMT_IP`、`ONTAP_SECRET_NAME`）、`vpcId`、状態機械 ARN、`S3_OBJECT_LOCK_BUCKET` が空で上書きされ、デプロイは成功する（1 観測、ap-northeast-1）。`sandbox.sh` は `ampx` の前に `portal_preflight.py --check-config-vs-live` を呼び、稼働中で非空の値が空になるキーの名前（値は出さない）を並べて止まる。実効値は環境変数、`portal-config.ts` のリテラルの順。意図した上書きは `AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING=1`（値がちょうど `1` のときだけ有効）。通す場合: 初回デプロイ、AWS を読めないとき（SSO 失効を含む）、別の identifier、`delete`。比べるのは上の 6 キーの空/非空だけで、値が違うことは見ない。起動時の 1 回だけで、`--watch` 中の再デプロイは見ない。この検査の所要時間は 7〜8 秒（2 回の実測、ap-northeast-1）。`make sandbox`、`make sandbox-watch`、`npm start` は `sandbox.sh` を通る。`npm run sandbox` と `npm run start:dev` は `npx ampx sandbox` を直接呼ぶので通らない。`AMPLIFY_PORTAL_SKIP_CONFIG_CHECK` はこの検査を飛ばさない。lab の `07_portal_config.sh --deploy` は、既存 sandbox で `portal-config.ts` が無いとき example をコピーして終了コード 10 で止まる。 強制: `scripts/portal_preflight.py --check-config-vs-live`（変更 2）、`scripts/tests/test_sandbox_script.py`、lab の `test_portal_config.py`（変更 3） |
| **`make portal-preflight` が全項目 `ok` でも、デプロイの完了を証明しない** | 観測（1 観測）: VPC に入るはずの 3 関数のうち 2 関数が更新に失敗して `VpcConfig` なし・ONTAP の両変数が空のまま残り、1 関数だけが正常だった。旧実装は「両変数が入っている関数」を ONTAP 向きとして検査したので、失敗した 2 関数が母集団から外れ、`all 1 function(s)` で `VPC wiring` が `ok` になった。修正後は母集団を `backend.ts` の `...(vpcConfig && …)` から導き、`M of N expected function(s) conform` を出す。**見るのは M と N が一致しているか。** preflight が見ない項目も残る: ホスティング済みバンドルが取り込んだ alias（`hosted bundle` はユーザープールの一致だけを見る）、`GUARDED_ENV_KEYS` 以外の設定（`ONTAP_SVM_NAME` など）、非空から別の非空への変更。 強制: `check_lambda_vpc`（変更 1）と回帰テスト `test_the_incident_shape_fails` |

sandbox が同一 VPC に複数ある状態と、不要な sandbox を消す作業の罠は
[portal-sandbox-lifecycle](portal-sandbox-lifecycle.md) にある。DynamoDB Gateway
エンドポイントの所有権、`list-exports` に現れない依存、log group の retention。

## CDK / IaC Quality Gates

This project implements a 6-layer defense architecture for infrastructure code quality:

| Layer | Tool | Purpose |
|:---:|------|---------|
| 1 | cfn-lint | Template syntax validation |
| 2 | cdk-nag (AwsSolutionsChecks) | AWS compliance checks. Blocking in CI against `security/cdk-nag-baseline.txt`; off in the deploy path (see below) |
| 3 | gitleaks + zizmor | Secrets + Actions security |
| 4 | IAM Access Analyzer | Over-permissive policy detection |
| 5 | CDK harness tests (47 assertions) | Structural regression prevention |
| 6 | floci integration tests (9 tests) | S3 AP runtime behavior |

### cdk-nag Design Decision (Amplify Gen2 Constraint)

**Problem**: registering cdk-nag during synth makes any reported violation interrupt synthesis and block deployment (v2 raised `[AssemblyError] Found errors`; v3 raises `ValidationFailed`). Amplify Gen2 creates resources (AppSync, Cognito, internal S3 buckets, DynamoDB) that produce Non-Compliant findings (ASC3, S1, S10, COG1, COG7, COG8, IAM4, IAM5) which are **NOT user-configurable** — Amplify controls their creation and does not expose configuration hooks for these properties.

**Solution**: off in the deployment path (`npx ampx sandbox` / `amplify deploy` synth
without it, so nothing blocks a deploy), on in a job of its own. Neither path needs AWS
credentials — nothing is deployed and no AWS call is made.

**It is a PR gate (since 2026-08-28)**, run by ci.yml's "Stage 2b: Amplify Portal" job,
which already has node_modules and the portal-config it needs. `npm run nag` synthesises;
`scripts/check_cdk_nag_baseline.py` compares the result to `security/cdk-nag-baseline.txt`,
which holds the 121 known findings one per line. A finding that is not there fails, and a
recorded one that gets fixed fails too.

**Do not verify it with `grep -rn CDK_NAG .github/workflows/`.** That produced no output
before the gate existed and still produces none: `scripts/cdk-nag.sh` sets the variable
itself. This file used to give that grep as the check, so it would report "no gate" either
way. Ask instead:

```bash
grep -rn check_cdk_nag_baseline .github/workflows/ Makefile
```

The other claim that was wrong: the documented `CDK_NAG=1 npx ampx generate outputs` reads
a deployed stack's outputs and never synthesises, so it reported nothing whether or not
findings existed. `ampx` has no synth-only command, so the script runs `amplify/backend.ts`
as the CDK app it is — CDK synthesises on exit when `CDK_OUTDIR` is set, and
`CDK_CONTEXT_JSON` supplies the context keys Amplify reads.

`tests/infrastructure/cdk-nag-v3.test.ts` is separate and still runs: it exercises the
`AwsSolutionsChecks` pack over constructs built in-test, so the API wiring is checked
without a portal synth.

**What this means for new code:**
- Adding a Lambda with `resources: ["*"]` → cdk-nag reports it on a manual run → acknowledge with a reason
- The harness assertion capping wildcard count (`backend-assertions.test.ts`) is the part that runs on a PR
- Amplify-managed resources (Cognito, AppSync, internal buckets) → acknowledged, documented, unchangeable

**Acknowledgments location**: `amplify/backend.ts` bottom section, via
`Validations.of(dataStack).acknowledge(...)`. cdk-nag v3 removed `NagSuppressions`, and
there is no `applyToNestedStacks` or `applyToChildren` flag — scope is the whole
mechanism, and acknowledging on a stack covers the constructs beneath it.

**Why NOT always-on nag:**
1. Amplify Gen2 nested stack resources cannot be reliably acknowledged
2. Amplify updates may introduce new internal resources with new findings, breaking unrelated deploys
3. Synthesis is interrupted by any reported violation — there is no "warning-only" mode

**Key rules for AI agents writing CDK/SAM code:**
- `resources: ["*"]` MUST have `// Restrict to ... in production` comment
- cdk-nag acknowledgments MUST include `reason` explaining why it's acceptable
- Lambda env vars for external infra MUST use `config.<property>` from `portal-config.ts` (not bare `process.env`)
- AppSync Data Sources MUST be in the same stack as the API (cross-stack = deploy failure)
- All Lambda functions: Python 3.13, ARM64, explicit timeout, description field
- No `@aws-cdk/*-alpha` modules — use L1 + escape hatches instead

**Validation commands:** `solutions/amplify-portal` で `npm run build`・`npm test`・`npm run nag`（合成のみ）。SAM: `cfn-lint solutions/industry/*/template.yaml`、`python scripts/validate-iam-policies.py solutions/industry/*/template.yaml`。統合: floci を起動（`docker run -d -p 4566:4566 floci/floci:latest`）して `python -m pytest shared/tests/integration/ -v`。
