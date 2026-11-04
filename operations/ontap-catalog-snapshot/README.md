# OPS7: ONTAP コマンドと REST API のスナップショット

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

FSx for ONTAP の管理者が、**ONTAP のバージョンごとに、自分の管理者アカウントで使える CLI コマンドと REST API を記録する** Lambda です。ONTAP のバージョンを確認するときに同じ頻度で取っておくと、バージョンが上がったときに何が増え、何が使えなくなったかを前回との差分で追えます。

このパターンの本体は [FSx-for-ONTAP-Cyber-Resilience-Patterns の `solutions/ontap-catalog-snapshot/`](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/tree/main/solutions/ontap-catalog-snapshot) です。ここでは `operations/` の規約（Python 3.13、arm64、タグ、登録点）に合わせて置いています。

---

## 認証情報の扱い: D28 からの例外

この版は **`fsxadmin`（ONTAP 管理者）の認証情報を使います。** [`docs/harvest-metrics-decisions.md`](../../docs/harvest-metrics-decisions.md) の D28 は「`fsxadmin` を共有せず、クラスターごとに `fsxadmin-readonly` のユーザーを使う」と決めています。この版はその決定に**従っていません**。理由は次のとおりです。

- 読み取り専用ユーザーで、読み取る 4 つのコマンド（`security login role show`、`show-user-capability`、`show-rest`、`show-ontapi`）が読めるかを**確認していません**。確認にはユーザーの作成（ONTAP への書き込み）が要るため、別途承認を取って行います。
- 実行は週 1 回で、認証が拒否されたら 1 回で止まります（後述）。常時ポーリングする監視に比べて、ロックの危険は小さくなります。ただし、なくなるわけではありません。

D28 と揃っている点は、1 ファイルシステムに 1 つのシークレットを使うこと（`FileSystemId` タグの照合）と、最初の認証失敗で止めることです。揃っていない点は、`fsxadmin` を使うことと、実行をまたいだ停止がないことです。

読み取り専用ユーザーに差し替えたとき、読めない項目は `manifest.json` の `unavailable` に HTTP コードを残し、実行は続けます（読めた項目の記録は取れます）。ただし、認証そのものが拒否された場合は続けず、全体を止めます。

---

## 何を記録するか

| 記録 | 取得元（ONTAP）| 権限で絞られるか |
|---|---|---|
| 実行できる CLI コマンド | `security login role show-user-capability` | 絞られる（実行ユーザーのもの）|
| REST エンドポイント全件 | `security login role show-rest` | 絞られない |
| ロール定義 | `security login role show` | 絞られない |
| 旧 API と CLI の対応 | `security login role show-ontapi` | 絞られない |
| REST の GET の可否 | パスパラメータのない GET を 1 回ずつ | 絞られる |

- 記録するのは **HTTP コードとエラーコードだけ** です。応答の中身（設定値、ライセンスなど）は保存しません。
- 送るのは **GET だけ** です。POST・PATCH・DELETE は送りません。
- 記録の意味は **実行ユーザーで決まります**。`manifest.json` の `ran_as` にユーザー名を残します。

実機で同じ内容を手で取った結果と読み方は、Cyber Resilience Spoke の [ONTAP コマンドと REST API のスナップショット](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/ontap-native/ontap-command-api-snapshot.md) にあります。

---

## 構成

```
EventBridge (rate) ──→ Lambda: snapshot (VPC 内) ──→ ONTAP 管理エンドポイント（GET のみ）
                              ├──→ Secrets Manager（指定した 1 つのシークレット）
                              └──→ S3（スナップショットと差分）──→ SNS（任意、件数のみ）
```

`operations/` の他の 6 パターンは Step Functions（collect、analyze、report）ですが、このパターンは**単一の Lambda** です。理由は、Step Functions の `States.TaskFailed` のリトライが、拒否された認証情報での再実行になりうるためです。`shared/ontap_client.py` も使いません。共有クライアントは `urllib3.Retry(total=3)` を内蔵し、401 を区別せずに例外にするので、「最初の認証失敗で止める」を持てません。ハンドラは標準ライブラリと boto3 だけで書いてあります。

VPC 内の Lambda から S3 とシークレットに出る経路（既存の VPC エンドポイントか NAT ゲートウェイ）が必要です。このテンプレートは作りません。

---

## 出力

```
s3://<bucket>/<OutputPrefix>/<FileSystemId>/
  latest.json                          # 最新の実行を指すポインタ
  <ONTAP version>/<yyyymmddThhmmssZ>/
    manifest.json                      # 版、件数、実行ユーザー、取得できなかった項目
    diff.json                          # 前回との差分
    cli-user-capability.json           # 実行できる CLI コマンド
    rest-endpoints.json                # REST 全件。操作、対応 CLI、GET の実測
    roles.json                         # ロール定義
    show-ontapi.json                   # ONTAPI と CLI の対応
```

[`examples/manifest.example.json`](examples/manifest.example.json) と [`examples/diff.example.json`](examples/diff.example.json) は構造の例です（`diff.example.json` の内容は説明用の仮のものです）。バケットは版の履歴を残すバージョニングつきで、スタックを削除しても残ります。

`diff.json` は、前回との差で次を示します。`changed` が `true` なら、通知先の SNS（任意）に件数だけを送ります。

- 追加・削除された CLI コマンド
- 追加・削除された REST エンドポイント
- GET の HTTP コードが変わったエンドポイント

---

## デプロイ

### 前提

1. FSx for ONTAP の管理エンドポイントに届く VPC 内のサブネット（管理エンドポイントは VPC 内からのみ到達します）。セキュリティグループはテンプレートが作れます。
2. 同じサブネットから Secrets Manager と S3 に出られること（VPC エンドポイントか NAT ゲートウェイ）。必要な値は `scripts/discover-network.sh` が引きます（後述）。
3. ONTAP 管理者の認証情報のシークレット（JSON で `username` と `password`）。**そのファイルシステム用のシークレット** を使います。
4. 管理エンドポイントの DNS 名（`aws fsx describe-file-systems` の `OntapConfiguration.Endpoints.Management.DNSName`）。
5. アカウントの Lambda 同時実行の上限に余裕があること。同時実行を 1 に予約します。

> **シークレットはファイルシステムごとに分ける。** FSx for ONTAP は、どのファイルシステムでも管理ユーザーが `fsxadmin` です。別のファイルシステムのシークレットを使うと認証に失敗し、繰り返すとアカウントがロックされます。シークレット名で選ばず、`FileSystemId` タグで選んでください。タグが `FileSystemId` パラメータと違うとき、この Lambda は ONTAP へ何も送らずに止まります。タグがないときは警告だけで進みます。

### セキュリティグループ

関数に必要なのは、**外向きの HTTPS（443）だけ** です。内向きは要りません。次の 3 か所への 443 を通します。

| 宛先 | 通す理由 | 相手側で必要なもの |
|---|---|---|
| FSx for ONTAP の管理エンドポイント | ONTAP の REST を読む | FSx のネットワークインターフェイスのセキュリティグループに、この関数から 443 の許可 |
| Secrets Manager | 認証情報を読む | VPC エンドポイントのセキュリティグループに、この関数から 443 の許可（NAT ゲートウェイ経由なら不要）|
| S3 | スナップショットを書く | ゲートウェイエンドポイントのプレフィックスリストへの外向き 443（NAT ゲートウェイ経由なら不要）|

`CreateSecurityGroup=true`（既定）にすると、テンプレートがこれを作ります。

- 関数用のセキュリティグループを作る。外向きは上の 3 か所の 443 だけで、内向きはなし。
- FSx と Secrets Manager のエンドポイントの既存グループに、**この関数のグループから 443 を許可するルール**を足す。ルールはスタックの削除で消える。デプロイする人に `ec2:AuthorizeSecurityGroupIngress` が要る。
- 必要な値が欠けていると、デプロイの時点で止まる（`Rules`）。関数が届かない構成を作って、15 分後の初回実行で気づく、ということは起きない。

必要な値は、読み取りだけのスクリプトが引きます。何も作らず、シークレットの値も読みません。

```bash
scripts/discover-network.sh fs-0123456789abcdef0 ap-northeast-1
```

出力の `FsxSecurityGroupId`、`SecretsEndpointSecurityGroupId`、`S3PrefixListId`、`VpcId` を `samconfig.toml` に写します。VPC エンドポイントが無く NAT ゲートウェイを使う場合は、スクリプトが `AllowOutboundHttpsToInternet=true` を案内します（`0.0.0.0/0` への 443 を 1 本許可します）。自分のセキュリティグループを使いたい場合は `CreateSecurityGroup=false` にして `VpcSecurityGroupIds` を渡します。その場合、上の表の許可は自分で用意します。

### 手順

```bash
cd operations/ontap-catalog-snapshot
cp samconfig.toml.example samconfig.toml     # プレースホルダーを自分の値に
sam build
sam deploy
```

`shared/` を使わないので、`build.sh` は要りません。

```bash
aws lambda invoke --function-name fsxn-ontap-catalog-snapshot-snapshot --payload '{}' --cli-binary-format raw-in-base64-out /tmp/out.json
cat /tmp/out.json
```

---

## パラメータ

| パラメータ | 既定 | 内容 |
|---|---|---|
| `FileSystemId` | 必須 | 出力先の名前と、シークレットのタグの照合に使う |
| `ManagementEndpoint` | 必須 | 管理エンドポイントの DNS 名または IP |
| `OntapSecretArn` | 必須 | 管理者の認証情報のシークレット |
| `SecretKmsKeyArn` | 空 | シークレットが自前の KMS キーのときだけ |
| `VpcSubnetIds` | 必須 | 関数を置く VPC のサブネット |
| `CreateSecurityGroup` | `true` | `true` なら関数用のセキュリティグループと、既存グループへの 443 の許可ルールを作る。`false` なら `VpcSecurityGroupIds` をそのまま使い、ルールは作らない |
| `VpcId` | 空 | サブネットの VPC。`CreateSecurityGroup=true` のとき必須 |
| `FsxSecurityGroupId` | 空 | FSx のネットワークインターフェイスのセキュリティグループ。`CreateSecurityGroup=true` のとき必須 |
| `SecretsEndpointSecurityGroupId` | 空 | Secrets Manager の VPC エンドポイントのセキュリティグループ。NAT ゲートウェイ経由なら空 |
| `S3PrefixListId` | 空 | S3 ゲートウェイエンドポイントのプレフィックスリスト。NAT ゲートウェイ経由なら空 |
| `AllowOutboundHttpsToInternet` | `false` | `true` なら `0.0.0.0/0` への外向き 443 を許可する（NAT ゲートウェイ経由で Secrets Manager と S3 に出る場合）|
| `VpcSecurityGroupIds` | 空 | `CreateSecurityGroup=false` のときだけ使う、自分のセキュリティグループ |
| `ExistingOutputBucketName` | 空 | 空なら、バージョニングと暗号化つきのバケットを作る |
| `OutputPrefix` | `ontap-catalog` | バケット内のキーの接頭辞 |
| `ScheduleState` | `ENABLED` | `DISABLED` にすると定期実行を作らず、手動で実行したときだけ動く。**空文字ではなくこれを使う**（`sam deploy` は空の値を無視して既定値を使う）|
| `ScheduleExpression` | `rate(7 days)` | `ScheduleState` が `ENABLED` のときの EventBridge の式 |
| `ProbeRestGet` | `true` | GET の実測を行うか |
| `ProbeMaxEndpoints` | `400` | GET を実測する上限 |
| `VerifySsl` | `false` | 管理エンドポイントの証明書を検証するか。既定の証明書は公的な CA の署名ではない |
| `NotificationTopicArn` | 空 | 変更があったときの SNS（件数だけ）|
| `LogRetentionInDays` | `90` | ログの保持期間 |

`operations/` の共通パラメータ（`FileSystemIds`、`AutomationLevel`、`DemoMode` など）は持ちません。1 ファイルシステム・1 スタックで、読み取りだけを行うためです。

---

## 管理者アカウントを守る設計

この Lambda は 1 回の実行で、同じ管理者の認証情報を何百回も使います。**認証に失敗したまま繰り返すと、ONTAP の管理ユーザーがロックされる** ので、次の仕組みを入れています。

| 仕組み | 実装 | 確認 |
|---|---|---|
| 最初の認証失敗で全体を止める | ONTAP のコード `6691623`、またはコードのない 401 で `AuthenticationAbort` | ユニットテスト: 認証失敗後に送られるリクエストが 1 件だけ |
| ロールによる 401 は止めない | ONTAP のコードが違う 401 は記録だけ | ユニットテスト: 後続のエンドポイントも実測される |
| 自動リトライなし | `EventInvokeConfig.MaximumRetryAttempts: 0`、EventBridge の `RetryPolicy` も 0 | テンプレートのテスト |
| 同時に 1 回だけ実行 | `ReservedConcurrentExecutions: 1` | テンプレートのテスト |
| 別のファイルシステムのシークレットを使わない | `FileSystemId` タグの照合。違えば ONTAP へ何も送らない | ユニットテスト |
| パスワードをログに出さない | SDK のロガーを WARNING に固定（`LOG_LEVEL=DEBUG` でも）| ユニットテスト |
| 応答の中身を保存しない | HTTP コードとエラーコードだけを残す | ユニットテスト |
| REST のパスを検証する | ONTAP が返したパスは `^/[A-Za-z0-9/_.-]+$` に合うものだけ使う | ユニットテスト |

---

## 制限と未確認

### 実行をまたぐ停止はない

停止が働くのは **1 回の実行の中だけ** です。認証が拒否されても、スケジュールが有効なら、**次の週に同じ認証情報をもう一度使います。**

その結果、拒否が続く間は週に 1 回ずつ認証の失敗が積み上がり、管理ユーザーがロックされることがあります。ONTAP の REST ではロックとパスワード誤りを区別できず、復旧はパスワードの再設定（`aws fsx update-file-system` の `FsxAdminPassword`）とシークレットの更新に限られます。

**運用者の対応:** 認証の失敗で実行が止まった（Lambda が失敗した）ら、原因を直すまで再実行しません。必要なら EventBridge のルールを無効にします。

```bash
aws events disable-rule --name <ルール名>
```

失敗したときにスケジュールを自動で無効にする設計は入れていません。入れるには、関数に `events:DisableRule` を与える必要があり、IAM の範囲が広がるため、別の判断にしています。

### その他

- **読み取り専用ユーザーでの動作は未確認です。** 読めない項目は `manifest.json` の `unavailable` に HTTP コードが残ります。
- GET を実測するのは、パスパラメータのない GET だけです（Cyber Resilience Spoke の実機、ONTAP 9.18.1P6 では 570 件のうち 219 件）。残りは `{uuid}` などの値を Lambda が知らないので実測しません。
- POST・PATCH・DELETE は試しません。副作用があるためです。
- 「すべての CLI コマンド」の一覧ではありません。API に対応づいたものと、実行ユーザーが使えるものだけです。
- 1 回の実行が長引いて残り時間が 90 秒を切ると、GET の実測を打ち切り、`probe_truncated` が `true` になります。
- Multi-AZ や他の ONTAP 版での動作は未確認です。

---

## 検証の状態

| 項目 | 状態 |
|---|---|
| ユニットテスト（Python 3.13、ONTAP は差し替え）| 通過 |
| cfn-lint | 通過 |
| Cyber Resilience Spoke での実機の確認 | ONTAP 9.18.1P6、Single-AZ、`fsxadmin`、Python 3.12 で 3 回成功（18〜19 秒）。出力は手で取ったデータと一致 |
| この Spoke のテンプレート（Python 3.13、arm64）での Lambda 上の実行 | 1 回成功（19 秒、最大メモリ 102 MB）。ONTAP 9.18.1P6、Single-AZ、`fsxadmin`、`ap-northeast-1`。CLI 1,744 件、REST 570 件、ONTAPI 対応 1,045 件、GET の実測 219 件。Cyber Resilience Spoke の実機と同じ件数。成果物・ログ・応答にパスワードなし |
| このテンプレートが作るセキュリティグループ | 上の実行で使用（外向き 443 のみ、既存グループへの許可ルール 2 本）。2 回目の実行、Multi-AZ、他の版は未確認 |
| 認証失敗の停止 | ユニットテストのみ。実機では起こしていません（ロックを避けるため）|
| ONTAP の版が変わったときの差分 | ユニットテストのみ |

実行は 1 回だけです。初回なので `diff.json` は「first snapshot」で、前回との差分は Lambda 上では確認していません（ユニットテストのみ）。所要時間の揺れも未確認です。

---

## 削除

```bash
aws cloudformation delete-stack --stack-name fsxn-ontap-catalog-snapshot
aws cloudformation wait stack-delete-complete --stack-name fsxn-ontap-catalog-snapshot
```

- **所要時間:** 実測で約 20 分でした（1 回の観測）。そのうち約 19.5 分は VPC 内の Lambda の削除で、残りは 15 秒以内です。待ち時間は ENI の解放によるもので、手順では縮められません。`wait` で待ってください。
- **削除の順序:** FSx と Secrets Manager エンドポイントの既存グループに足した許可ルール 2 本が最初に消え、次に関数、最後に関数用のセキュリティグループが消えます。実測では、セキュリティグループが使用中で止まることはありませんでした。他のクライアントのルールには触れません。
- **残るもの:** 出力バケットだけです。スナップショットが記録そのものなので `Retain` にしてあります。ログ、セキュリティグループ、IAM ロールはスタックと一緒に消えます。
- **バケットを消す場合:** バージョニングが有効なので、「空にする」だけでは古い版と削除マーカーが残り、バケットを削除できません。スクリプトが、パターンのタグを持つバケットだけを対象に、全バージョンを消してバケットを削除します。`--yes` なしでは一覧を出すだけで、何も変えません。**取り消せません。** 記録を残したいなら実行しないでください。

```bash
scripts/delete-output-bucket.sh <bucket> ap-northeast-1          # 一覧だけ
scripts/delete-output-bucket.sh <bucket> ap-northeast-1 --yes    # 削除
```

---

## 関連

- [本体（Cyber Resilience Spoke）](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/tree/main/solutions/ontap-catalog-snapshot)
- [D28: ONTAP 資格情報の決定](../../docs/harvest-metrics-decisions.md)
- [operations/ の一覧](../README.md)

---

<!-- playbook-reading:start -->
## 本番に出す前に読むもの

デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあります。同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。

- [運用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/05-operate) — このパターンで判断が集中するところ
- [性能](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/performance) — 次に読む
- [構築](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/04-build) — 本番前に通す（全パターン共通）
<!-- playbook-reading:end -->
