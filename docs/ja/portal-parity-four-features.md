# 同じ 4 機能を 3 つの構築ツールで実装した記録 — Amplify Gen 2 / AWS Blocks / Nx Plugin for AWS

> 🌐 **Language / 言語**: 日本語 | [English](../en/portal-parity-four-features.md)

## TL;DR

- [構築ツールの選択肢](scaffolding-and-backend-toolkit-choices.md)はスターターを生成して **ローカルの
  テンプレート生成（`synth`）まで**を測ったものだった。この文書はその続きで、**同じ 4 機能（サインイン / 一覧 /
  読み取り / アップロード）を 3 つの構築ツールで実装し、同一の Amazon FSx for NetApp ONTAP S3 Access
  Point に対して AWS 上で動かした**記録である。
- 4 機能は 3 者すべてで動いた。**一覧は 13 オブジェクト、読み取りは 1,615 バイト /
  `text/markdown; charset=utf-8`、アップロードは 24 バイトが往復**し、3 者で一致した。
- **S3 Access Point への到達方法は 3 者で同じ**だった。標準の S3 SDK にエイリアスをバケット名として
  渡すだけで、エンドポイントの上書きも VPC への接続も要らない。構築ツールによって変わるのは到達方法では
  なく、**権限の書き方と、その権限をどこに書くか**である。
- **同じ不正入力が、構築ツールによって別の層で拒否された。** `../escape.txt` は Nx の生成物では AWS WAF が
  Lambda に届く前に 403 で止め（WebACL の `BlockedRequests` で確認）、AWS Blocks では自分で書いた
  手続きに届いてドメインエラーになった。どちらも拒否だが、**障害調査のときに見えるものが違う**。
- 実測: デプロイは **AWS Blocks 318 秒 / 82 リソース**、**Nx Plugin for AWS 307 秒 / 100 リソース**。
  Amplify Gen 2 はこのリポジトリで既に動いているポータル（4 機能より広い機能を持つ）を使ったので、
  同じ物差しでは並べていない。
- 画面は[3 者 12 枚](#3-者-12-枚の画面)にある。**読み取りと書き込みの画面構成は 3 者で違う**。

## この文書の範囲

**書くこと**: 4 機能の実装が 3 者でどう違ったか、S3 Access Point への到達と権限の書き方、
実機で確認した値、拒否が起きた層、撮影した 12 枚、踏んだ罠、再現手順。

**書かないこと**: どれが優れているかの結論。性能測定（スループットもレイテンシも測っていない）。
4 機能より広い範囲の比較（ONTAP の管理操作・AI 処理・8 言語 UI・ARP/WORM はこの比較の対象外で、
[次に足すもの](#4-機能から先へ進むフェーズ)に前提だけを書いた）。AWS Blocks の GA 後の仕様
（測定は preview 時点）。

**対象読者**: FSx for ONTAP のボリュームをブラウザから見せる仕組みを作ろうとしていて、
構築ツールを決めかねている人。すでにどれかで作っていて、他の構築ツールなら何が違ったのかを知りたい人。

## 固定した 4 機能

比較を成立させるため、機能を 4 つに固定し、API の名前も 3 者で揃えた。

| 機能 | API 名 | 何をするか |
|---|---|---|
| サインイン | （構築ツールの認証機構） | 認証を通す |
| 一覧 | `listFiles(prefix)` | prefix 配下のオブジェクトを一覧する |
| 読み取り | `readFile(path)` | 1 オブジェクトの中身を取得する |
| アップロード | `uploadFile(name, text)` | 1 オブジェクトを書き込む |

補助として `describeTarget()` を置き、既定の prefix と書き込み先を返すようにした。

**4 つに絞った理由**: このリポジトリのポータルは 180 を超える操作を持つ。それを 3 通りに移植すると、
比べているものが「構築ツールの差」ではなく「私が書いた量」になる。4 機能なら、どの構築ツールでも同じ深さまで
書ききれる。

## 共通の検証対象

3 者すべてが同じ 1 つの S3 Access Point を読み書きした。

| 項目 | 値 |
|---|---|
| Access Point | Internet origin（VPC 接続なし） |
| 一覧の対象 | `reports/2026/05/10/` — **13 オブジェクト** |
| 読み取りの対象 | `compliance-report-<uuid>.md` — **1,615 バイト**、`text/markdown; charset=utf-8` |
| 書き込み先 | `portal-parity/{blocks,nx,amplify}/` に構築ツールごとに分離 |
| 書き込んだもの | `note-2026-09-14.txt` — **24 バイト** |

`Content-Type` はアプリが付けたものではなく、FSx for ONTAP のボリューム上のオブジェクトが
持っているメタデータである。3 者とも同じ値を受け取った。

書き込み先を prefix で限定したのは、この Access Point が **NFS と SMB のクライアントも使っている
稼働中のボリューム**を公開しているためである。任意のキーを受け付ける実装は、この環境では選べない。

## 同一の到達方法と、権限の書き方の差

### 共通していたこと

Internet origin の Access Point は、**標準の S3 SDK にエイリアスをバケット名として渡すだけ**で
届く。エンドポイントの上書きも、Lambda を VPC に置くことも要らない。3 者いずれも VPC 外の Lambda
から読み書きできた。

### 3 者共通の「アクセスポイント形式」要求

権限は次の形でなければ通らない。バケット形式（`arn:aws:s3:::<alias>`）では `s3:ListBucket` /
`s3:GetObject` / `s3:PutObject` のすべてが `AccessDenied` を返す。

```
arn:aws:s3:<region>:<account-id>:accesspoint/<access-point-name>          # ListBucket
arn:aws:s3:<region>:<account-id>:accesspoint/<access-point-name>/object/* # GetObject, PutObject
```

これは使い捨ての IAM ロールで対照を取って確認した（2026-09-14）。バケット形式のロールでは 3 操作
すべてが拒否され、アクセスポイント形式では 3 操作すべてが通った。

**AWS Blocks で注意が必要なのはここである。** `FileBucket.fromExisting(alias)` は既存のバケットを
参照する抽象で、内部では `s3.Bucket.fromBucketName(alias)` に対して `grantReadWrite()` を呼ぶ。
つまり生成される権限は**バケット形式**になり、Access Point には届かない。ブロックの `grant` とは
別に、アクセスポイント形式のポリシーを明示的に足す必要がある。

```ts
// aws-blocks/index.cdk.ts — ブロックの grant に加えて明示的に付与する
blocksStack.handler.addToRolePolicy(
  new iam.PolicyStatement({
    actions: ['s3:ListBucket', 's3:GetObject', 's3:PutObject'],
    resources: [apArn, `${apArn}/object/*`],
  }),
);
```

### 権限を書く場所の違い

| | 権限の付与先 | 理由 |
|---|---|---|
| AWS Blocks | ハンドラ 1 本にポリシーを追加 | API 全体が単一の Lambda |
| Nx Plugin for AWS | 共用ロールを全 Lambda に渡す | **手続きごとに Lambda が 1 本**（`pattern: 'isolated'`） |
| Amplify Gen 2 | バックエンド定義内で関数に付与 | 既存のポータルの構成に従う |

Nx の生成物は手続きの数だけ Lambda を作る。4 機能 + `echo` で 5 本になり、synth したテンプレートで
確認できた。個々のハンドラを型経由で取り出す道はない（`RestApiIntegration` 型は `handler` を
公開しない）ため、ロールを 1 つ作って既定オプションとして全体に渡す形にした。

```ts
// packages/infra/src/stacks/application-stack.ts
const api = new PortalApi(this, 'PortalApi', {
  integrations: PortalApi.defaultIntegrations(this)
    .withDefaultOptions({
      role: apiRole, // アクセスポイント形式のポリシーを持つ共用ロール
      environment: { PORTAL_S3AP_ALIAS: s3apAlias },
    })
    .build(),
});
api.grantInvokeAccess(identity.identityPool.authenticatedRole);
```

生成された integration は `Tracing.ACTIVE` が既定なので、自前のロールに差し替えるときは
`xray:PutTraceSegments` と `xray:PutTelemetryRecords` を足す必要がある。付け忘れると呼び出しごとに
トレースの失敗が記録される。

### ストレージの抽象の有無

| | ストレージの抽象 | 実装 |
|---|---|---|
| AWS Blocks | `FileBucket.fromExisting()` がある | ブロックの API 経由（権限だけ手当て） |
| Nx Plugin for AWS | **ない** | `@aws-sdk/client-s3` を直接使う |
| Amplify Gen 2 | `defineStorage` と Storage Browser がある | 既存のポータルの構成に従う |

Nx Plugin for AWS は API と Website の生成に責任を持ち、データアクセスは書く側に委ねる。
これは不足ではなく分担で、逆に言えば **Access Point のような「標準の抽象に収まらない対象」を
扱うときは、抽象がないほうが素直に書ける**。

## 認証機構の違い

| | サインインの形 | MFA の既定 | 画面 |
|---|---|---|---|
| AWS Blocks | アプリ内のモーダル（`AuthBasic` + 付属の UI キット） | — | アプリの画面 |
| Nx Plugin for AWS | **Cognito のホスト UI へリダイレクト**（OIDC の `signinRedirect()`） | **REQUIRED**（SMS + TOTP） | Cognito の画面 |
| Amplify Gen 2 | アプリ内の Authenticator（Amplify UI） | OPTIONAL | アプリの画面 |

Nx の `UserIdentity` は MFA を要求する既定を持つ。初回サインインで第 2 要素の登録が必要になり、
自動化された検証からトークンを取るには、その手順を通す必要がある（[罠](#罠の登録簿)参照）。

生成された User Pool クライアントは `ADMIN_*` の認証フローを有効にしない。管理 API で近道を作れない
ということで、**検証もブラウザと同じ公開フローを通る**。既定として妥当な選択である。

## 3 者 12 枚の画面

3 者・4 機能を同じ順序、同じ対象、同じ寸法（1512x900）で撮った。UI の言語は英語に揃えた
（AWS Blocks と Nx の実装は英語のみで、言語を比較軸にしないため）。

### サインイン

| Amplify Gen 2 | AWS Blocks | Nx Plugin for AWS |
|---|---|---|
| ![Amplify のサインイン](../screenshots/portal-parity/portal-amplify-01-signin.png) | ![AWS Blocks のサインイン](../screenshots/portal-parity/portal-blocks-01-signin.png) | ![Nx のサインイン](../screenshots/portal-parity/portal-nx-01-signin.png) |
| アプリ内の Authenticator | アプリ内のモーダル | Cognito のホスト UI |

### 一覧

| Amplify Gen 2 | AWS Blocks | Nx Plugin for AWS |
|---|---|---|
| ![Amplify の一覧](../screenshots/portal-parity/portal-amplify-02-list.png) | ![AWS Blocks の一覧](../screenshots/portal-parity/portal-blocks-02-list.png) | ![Nx の一覧](../screenshots/portal-parity/portal-nx-02-list.png) |
| フォルダを辿る（13 ファイル + 親への `..`） | prefix を入力する（13 件） | prefix を入力する（13 件） |

### 読み取り

| Amplify Gen 2 | AWS Blocks | Nx Plugin for AWS |
|---|---|---|
| ![Amplify の読み取り](../screenshots/portal-parity/portal-amplify-03-read.png) | ![AWS Blocks の読み取り](../screenshots/portal-parity/portal-blocks-03-read.png) | ![Nx の読み取り](../screenshots/portal-parity/portal-nx-03-read.png) |
| **本文を描画しない**。選択して AI Assistant に渡す、またはフォルダ単位の ZIP で取得する | 本文をページに描画（1,615 バイト） | 本文をページに描画（1,615 バイト） |

Amplify Gen 2 の列だけ性質が違うのは、比較対象が**このリポジトリで実運用しているポータル**で
あって、4 機能のために書いた最小の UI ではないからである。撮影時に確認した範囲では、
`.md` をページ内に描画する経路は見つからなかった（ファイル名のクリックと行のメニューの
両方を試した）。他の 2 列に本文が出ているのは、そう書いたからにすぎない。

> **アクセシビリティに関する補足**: 撮影の過程で、ファイル行の書類アイコンが
> `aria-label="Download <ファイル名>"` を持ちながら、クリックしてもダウンロードが発生しないことを
> 確認した（実際の動作は「AI 処理用の選択」）。`title` 属性は両方の動作を書いているが、
> スクリーンリーダーが読む accessible name は `Download` だけを名乗る。ポータル側の修正対象として
> 記録しておく。

### アップロード

| Amplify Gen 2 | AWS Blocks | Nx Plugin for AWS |
|---|---|---|
| ![Amplify のアップロード](../screenshots/portal-parity/portal-amplify-04-upload.png) | ![AWS Blocks のアップロード](../screenshots/portal-parity/portal-blocks-04-upload.png) | ![Nx のアップロード](../screenshots/portal-parity/portal-nx-04-upload.png) |
| **別画面**（Storage Browser）。24 バイトの書き込みが完了 | 一覧と同じ画面。24 バイトが一覧に反映 | 一覧と同じ画面。24 バイトが一覧に反映 |

Amplify Gen 2 の画面にはエイリアスが描画されるため、撮影直前に DOM 上のテキストを
`your-ap-xxxxx-ext-s3alias` に置換した。AWS Blocks と Nx の実装はエイリアスを画面に出さないので
置換は不要だった。

## 拒否が起きる層の違い

同じ「許可された prefix の外への書き込み」を 2 通りの入力で試した。

| 入力 | Nx Plugin for AWS の応答 | AWS Blocks の応答 |
|---|---|---|
| `../escape.txt` | **HTTP 403** `{"message":"Forbidden"}` — Lambda に届かない | 自分の手続きのドメインエラー |
| 空のファイル名 | **HTTP 400** + 自分のドメインエラー | 自分の手続きのドメインエラー |

Nx の生成物では、パストラバーサルの形をした入力が **AWS WAF に止められていた**。ジェネレーターは
API に Web ACL を既定で付け（`enableWaf` の既定が true）、Core Rule Set と Known Bad Inputs の
マネージドルールを適用する。Core Rule Set はリクエストボディを検査するため、`../` を含む本文が
Lambda に到達する前に落ちる。

**根拠**: `uploadFile` の Lambda の呼び出し回数は 3 で、送った書き込み要求は 5 件だった（2 回の
実行分）。差の 2 件がトラバーサル形式の 2 件である。API の WebACL のメトリクスも
`BlockedRequests = 2` / `AllowedRequests = 14` で一致した。

読み方は「WAF があるほうが安全」ではない。**多層防御が既定で有効なのは利点だが、拒否の理由が
自分のコードのメッセージではなく汎用の 403 として返るため、調査の起点が変わる**。自分の guard が
働いたのか、その手前で落ちたのかは、WAF のメトリクスを見るまで区別できない。

なお WAF のメトリクスは即時ではない。要求の直後は `BlockedRequests` が未取得で、
`get-sampled-requests` も 0 件だった。数分後に 2 として現れた。**直後の不在は不在の証拠に
ならない。**

## 実測

環境: ap-northeast-1、2026-09-14 実施。デプロイ時間は 1 回の測定値で、キャッシュ状態や
アカウントの既存リソースに依存する。

| | デプロイ時間 | CloudFormation リソース数 | 業務用 Lambda |
|---|---|---|---|
| AWS Blocks（production preset） | **318 秒** | **82** | 1 本（API 全体） |
| Nx Plugin for AWS（sandbox） | **307 秒** | **100** | **5 本**（手続きごと） |
| Amplify Gen 2 | 測っていない | 測っていない | — |

**Amplify Gen 2 を並べていない理由**: 比較に使ったのはこのリポジトリで動いているポータルで、
4 機能より広い機能を持つ。同じ 4 機能だけの Amplify アプリを別に作れば数値は出るが、それは
「このポータルの実測」ではなくなる。スターター同士の比較は
[構築ツールの選択肢](scaffolding-and-backend-toolkit-choices.md#実測)にある。

**AWS Blocks が 82 で、同じ preset のスターターが 117 だったこと**について。差は preset ではなく
**使ったブロックの数**から来る。この実装では `AuthBasic` と外部参照の `FileBucket` だけを使い、
スターターにあった 4 本の `DistributedTable` と Realtime を使っていない。リソース数は preset の
選択より、どのブロックを使うかで決まる。

## 罠の登録簿

### T1. `FileBucket.fromExisting()` が生成する ARN の形式

前述のとおりバケット形式になり、Access Point には届かない。ブロックの `grant` を信じて権限を
書かないと、ローカルでは通り、デプロイ後に 3 操作すべてが `AccessDenied` になる。

### T2. ローカルモードの緑と到達性の無関係

AWS Blocks のローカル e2e は 9 件のうち 7 件が通った。落ちたのは実データの読み取りに依存する 2 件
だけで、**アップロードの往復テストはローカルで通る**。モックの `FileBucket` は空で始まるため、
書いて読み直す形のテストはモックの中で完結する。ローカルの suite が緑であることは、
FSx for ONTAP の Access Point に届くことを何も示さない。

### T3. `nx sync` 未実行による生成コードの型エラー

`portal-api` に依存を追加した後、`common-constructs` と `portal-web` のコンパイルが 28 件の
TS6059 / TS6307 で失敗した。エラーが指すのは自分が書いたファイルではなく**生成されたファイル**
（`common-constructs/src/app/apis/portal-api.ts` と
`portal-web/src/components/PortalApiClientProvider.tsx`）で、どちらも `@fsxn-portal-nx/portal-api`
をソース解決して `rootDir` の外に出ていた。ジェネレーターが壊れた出力を出したように見えるが、
原因は TypeScript のプロジェクト参照が古いことである。`nx sync` を実行すると全件解消する。

### T4. 登録直後のセッションでの TOTP 登録の不成立

`VerifySoftwareToken` が `SUCCESS` を返しても、その応答に含まれるセッションで MFA チャレンジに
応答すると、正しいコードでも `CodeMismatchException` になる。**もう一度サインインして
`SOFTWARE_TOKEN_MFA` チャレンジを取り直す**必要がある。

### T5. email エイリアス設定下でのユーザー名の形式制限

`AdminCreateUser` が `Username cannot be of email format` を返す。ユーザー名は素の文字列にして、
アドレスは `email` 属性に入れる。

### T6. 自前のクエリ文字列による SigV4 署名の不一致

`SignatureDoesNotMatch` が返る。正規形はパーセントエンコードの対象が広く、
`urllib.parse.quote` の既定は `/` を素通しする。prefix にスラッシュが入るこの用途では必ずずれる。
`AWSRequest(params=...)` に渡して署名側に正規化させ、`prepare()` が組んだ URL を送る。

### T7. `aria-label` による accessible name の上書き

ポータルの言語スイッチャは表示テキストが `🌐 日本語 ▾` だが `aria-label="言語"` を持つため、
アクセシブル名で `日本語` を探しても永久に一致しない。属性で指定する必要がある。
自動化の話に見えて、実際は**スクリーンリーダーが読み上げる名前と目に見える名前が違う**という
アクセシビリティの観測でもある。

### T8. 初回ツアーのモーダルと再読み込み

ポータルの初回ツアーは一覧を覆う。「次回から表示しない」を先に選ばずにページを再読み込みすると
ツアーが再出現し、次の操作のクリックを飲み込む。ルートへ戻るときは再読み込みではなく
パンくずを使う。

### T9. Storage Browser の隠れた `input[type=file]` への直接入力の無効

コンポーネントが自前で状態を持つため、DOM 上の入力要素にファイルを設定しただけでは
アップロードが始まらない。表のオーバーフローメニューの項目を先に押して初期化する必要がある。

## 4 機能から先へ進むフェーズ

この 4 機能は最小の実用単位で、実際のポータルに必要なものはこの先にある。
フェーズごとの前提を[拡張のフェーズ](portal-parity-next-steps.md)にまとめた。

## 再現手順

```bash
# 共通: Internet origin の Access Point のエイリアスと名前を環境変数に置く
export PORTAL_S3AP_ALIAS='<alias>-ext-s3alias'
export PORTAL_S3AP_NAME='<access-point-name>'

# AWS Blocks（preview）
npm create @aws-blocks/blocks-app -- <project>
#   aws-blocks/index.ts        4 機能を実装
#   aws-blocks/index.cdk.ts    環境変数と、アクセスポイント形式の IAM を明示的に付与（T1）
npm run typecheck && npm run deploy      # production preset。CloudFront が付くのは production だけ

# Nx Plugin for AWS
npm_config_yes=true npm create @aws/nx-workspace@1.0.0 -- <project> \
  --interactive=false --pm=npm --nxCloud=skip --skipGit --aiAgents=none
nx g @aws/nx-plugin:ts#website portal-web
nx g @aws/nx-plugin:ts#website#auth --project=@<project>/portal-web
nx g @aws/nx-plugin:ts#api portal-api --framework=trpc
nx g @aws/nx-plugin:connection --sourceProject=@<project>/portal-web --targetProject=@<project>/portal-api
nx g @aws/nx-plugin:ts#infra infra
#   packages/portal-api/src/{schema,procedures}/files.ts   4 機能を実装
#   packages/infra/src/stacks/application-stack.ts         生成時点では空。ここに配線を書く
nx sync                                   # 依存を追加したら必須（T3）
NX_TUI=false CI=true nx run @<project>/infra:deploy-sandbox --args="--rollback"
```

後片付けは[デプロイ検証と後片付けの手順](scaffolding-deploy-verification.md#後片付けの手順)にある。**Nx の
生成物は User Pool と DynamoDB に削除保護を、KMS 鍵に `Retain` を付けるため、スタックを消しても
残る。** 検証環境として立てたなら、その日のうちに後片付けまで通しておくとよい。

## 関連ドキュメント

- [フルスタック AWS アプリの構築ツールの選択肢](scaffolding-and-backend-toolkit-choices.md) —
  スターター同士の比較、生成される既定値の差、固定費
- [構築ツールの生成物のデプロイ検証と後片付けの手順](scaffolding-deploy-verification.md) —
  削除保護・`Retain`・express モードの固着を含む後片付けの実務
- [拡張のフェーズ](portal-parity-next-steps.md) — 4 機能の先に足すものと、その前提
- [FSx for ONTAP の管理インターフェースの整理](fsx-ontap-management-interfaces.md) —
  管理面に何が到達できるか
