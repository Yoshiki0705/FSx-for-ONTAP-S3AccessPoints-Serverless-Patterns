# ポータルの再デプロイ失敗と検査の罠

対象は「更新に失敗した Lambda が再デプロイで直らない」ことと、デプロイの前後に走る検査。
CDK コードそのものの罠は [portal-cdk-quality-gates](portal-cdk-quality-gates.md)、
同一 VPC の sandbox の同居と後始末は [portal-sandbox-lifecycle](portal-sandbox-lifecycle.md) にある。
根拠の段階は、verified（この環境で実行して確認）、documented（公式文書）、hypothesis（読みであって未確認）で区別する。
表は何をするかと強制の所在だけを持ち、各行の観測・読み・限界は表の下の「根拠の詳細」にあり、見出しの行番号が表の行に対応する。
末尾の「強制」は、その行を機械的に守っている検査の所在。

| Pitfall | Solution |
|---------|----------|
| **`UPDATE_FAILED` の関数は `description` の変更だけでは更新されず、`make sandbox` を再実行しても変わらない** | 更新後の判定は `describe-stacks` の `StackStatus` ではなく、`get-function-configuration` の `VpcConfig` と環境変数で行う。観測は 1 件（verified、ap-northeast-1）、理由は hypothesis（行 1 の根拠）。強制: `make portal-preflight` の `VPC wiring`。`backend.ts` で VPC に入る関数ごとに、論理 ID を挙げて FAIL にする |
| **CloudFormation の更新を起こす変更の例と限界** | データスタックに `CfnOutput` を 1 つ足して `--once`、削除してもう 1 回 `--once` すると、直前に `UPDATE_FAILED` だった 2 関数が更新された（verified、1 観測、ap-northeast-1）。失敗したリソースが再試行されるかは、リソースの型と失敗の原因による。1 観測を一般則にしない（行 2 の根拠）。強制: `make portal-preflight` の `VPC wiring` が、更新後に VPC に入るはずの関数を `M of N expected function(s) conform` で数える。M が N に届かなければ、更新は届いていない |
| **VPC に入る Lambda の更新が、実行ロールへ VPC 実行ポリシーを付けた直後に `CreateNetworkInterface` の権限エラーで失敗することがある** | ポリシー付与の 3〜4 秒後に始まった更新が 2 関数で失敗し、別の関数の更新は約 19 秒後に成功した（verified、1 観測、ap-northeast-1。再現率は未測定、原因は hypothesis）。復旧は、ロールが整った後に CloudFormation の更新を起こし直す（上の行）。強制: 失敗した関数は VPC 配線なし・ONTAP の環境変数が空のまま残るので、`make portal-preflight` の `VPC wiring` が FAIL にする |
| **`portal-config.ts` は作業ツリーごとの gitignore 対象で、共有 sandbox の実効設定は「デプロイを打った作業ツリーのそれ」になる** | `sandbox.sh` は `ampx` の前に `portal_preflight.py --check-config-vs-live` を呼び、稼働中で非空の値が空になる 6 キーの名前（値は出さない）を並べて止まる。意図した上書きは `AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING=1`（値がちょうど `1` のときだけ有効）。通す場合と通らない入口は行 4 の根拠。強制: `scripts/portal_preflight.py --check-config-vs-live`、`scripts/tests/test_sandbox_script.py` |
| **`make portal-preflight` が全項目 `ok` でも、デプロイの完了を証明しない** | 全項目 `ok` の後は、`VPC wiring` の `M of N expected function(s) conform` で M と N が一致しているかを見る。N は `backend.ts` から導くので、更新に失敗した関数が母集団から外れても縮まない。旧実装は外れた（verified、API 形のフェイクで再現。行 5 の根拠）。強制: `check_lambda_vpc` と回帰テスト `test_the_incident_shape_fails` |

## 根拠の詳細

行 3 は表の中で観測と段階が完結しているので、ここには置かない。

### 行 1 の根拠: 更新されない関数の観測と読み

- 観測（verified、1 観測、ap-northeast-1）: `description` に印を足した `--once` を 2 回実行した。どちらも `Updated AWS::Lambda::Function` と約 3.5 秒の `Deployment completed in` を表示し、スタックのイベントは 0 件。更新に失敗していた関数の `VpcConfig` と ONTAP の環境変数は空のままだった。[portal-cdk-quality-gates](portal-cdk-quality-gates.md) の「`ampx` は失敗しても exit 0 を返す」の (a) と同じ型の現象で、この行はその理由の読み。
- 読み（hypothesis）: `ampx sandbox` は差分が Lambda の `description` や環境変数だけのとき、CloudFormation を通さず Lambda API で直接反映する（hotswap）と読める。`UPDATE_FAILED` のスタックが保持するテンプレートには失敗した更新の新しい定義が入っているので、`ampx` が作る差分に現れるのは `description` だけになり、`VpcConfig` は差分に出ない、と読める。
- 公式文書（documented）: `cdk deploy --hotswap` の文書は、Lambda の設定変更で対象になるのは `description` と環境変数だけで、対象外の変更は無視され、CloudFormation にドリフトを作ると書く（[cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)）。
- 未確認: `ampx` の実装は読んでいない。ロックファイルの `@aws-amplify/backend-cli` は 1.10.0 で、観測時に実行したバージョンは記録していない。再実行が関数を更新するかは 1 観測であり、`ampx` の別バージョンや別の失敗原因では未測定。

### 行 2 の根拠: CloudFormation の更新を起こす変更の例と限界

- 観測（verified、1 観測、ap-northeast-1）: 出力の追加と削除は行 1 の根拠の hotswap 対象の一覧になく、CloudFormation の更新になる。直前の実行で `UPDATE_FAILED` だった 2 関数が更新され（VPC 配線、ONTAP の環境変数、共有レイヤーが反映）、3 スタックが `UPDATE_COMPLETE` になり、失敗イベントは 0 件。
- 同じ更新で起きたこと: 失敗していない関数を含む Lambda 24 件と IAM ロール 25 件も更新された。未完了の更新をまとめて処理したと読める（hypothesis）。
- 限界: 失敗したリソースが再試行されるかは、リソースの型と失敗の原因による。置換が拒否された LayerVersion はこの方法では直らず、論理 ID の変更が要る（[portal-cdk-quality-gates](portal-cdk-quality-gates.md) の「LayerVersion は論理 ID にフィンガープリントを入れて」の行）。

### 行 4 の根拠: 設定の上書きとその検査の範囲

- 観測（1 観測、ap-northeast-1）: 別の作業ツリーで example をコピーしただけの（値がすべて空の）設定から `make sandbox` を打つと、稼働中の S3 Access Points のエイリアス（`S3_AP_ALIAS`）、ONTAP の接続（`ONTAP_MGMT_IP`、`ONTAP_SECRET_NAME`）、`vpcId`、状態機械 ARN、`S3_OBJECT_LOCK_BUCKET` の 6 キーが空で上書きされ、デプロイは成功した。
- 検査の実測（verified、読み取り専用、ap-northeast-1）: 空の example を実効設定にすると 6 キーが FAIL になり（8 秒、1 回）、実設定では 6 キーを比較して通った（7 秒、1 回）。どちらも出力に値は無かった。
- 実効値: 環境変数、`portal-config.ts` のリテラルの順。
- 通す場合: 初回デプロイ、AWS を読めないとき（SSO 失効を含む）、期待と違う形の応答、別の identifier、`delete`。AWS を読めないことを失敗にしないのは、`ampx` が同じ認証情報を要し、`sandbox.sh` が sandbox を特定できなければ先に止まるので、2 つ目の関門は迂回の理由を増やすだけになるため。
- 通らない入口: `npm run sandbox` と `npm run start:dev` は `npx ampx sandbox` を直接呼ぶ。`make sandbox`、`make sandbox-watch`、`npm start` は `sandbox.sh` を通る。起動時の 1 回だけで、`--watch` 中の再デプロイは見ない。
- 比べないもの: 6 キー以外の設定、非空から別の非空への変更（値が違うことは見ない）。
- `AMPLIFY_PORTAL_SKIP_CONFIG_CHECK` はこの検査を飛ばさない。
- lab の `07_portal_config.sh --deploy` は example をコピーしたあとそのまま `sandbox.sh --once` を呼ぶので、既存 sandbox で環境変数も値を渡していなければ同じ検査が止める（lab 側には専用のガードは無い）。

### 行 5 の根拠: 全項目 ok の後に見るもの

- 観測（verified、1 観測、ap-northeast-1）: VPC に入るはずの 3 関数のうち 2 関数が更新に失敗して `VpcConfig` なし・ONTAP の両変数が空のまま残り、1 関数だけが正常だった。
- 旧実装の判定（verified、API 形のフェイクに旧実装を流して再現）: 旧実装は「両変数が入っている関数」を ONTAP 向きとして検査したので、失敗した 2 関数が母集団から外れ、`all 1 function(s)` で `VPC wiring` が `ok` になった。
- 修正後: 母集団を `backend.ts` の `...(vpcConfig && …)` から導き、`M of N expected function(s) conform` を出す。見るのは M と N が一致しているか。
- preflight が見ない項目: ホスティング済みバンドルが取り込んだ alias（`hosted bundle` はユーザープールの一致だけを見る）、`GUARDED_ENV_KEYS` 以外の設定（`ONTAP_SVM_NAME` など）、非空から別の非空への変更。
