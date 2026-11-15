# ファイルポータルのツール

🌐 **Language / 言語**: 日本語 | [English](file-tools.en.md)

サイドバーの「ツール」で、FSx for ONTAP 上のファイルに対して翻訳・校正・図の生成をし、Web ページを要約し、画像を作ってフォルダに保存し、よく使う指示をテンプレートとして保存できます。ファイルの一覧でファイルを選ぶと、右の AI パネルに「翻訳・校正・図にする」のボタンが出て、そのファイルを入力にしてツールを開けます。スクリーンショットは、デプロイした Amplify sandbox（ap-northeast-1、2026-11-15）で撮りました。

## 各ツールの動作

| ツール | 入力 | 結果 |
|--------|------|------|
| 翻訳 | 選択中のファイル、または貼り付けたテキスト | 13 言語へ翻訳。文体と用語の補足を指定できる。結果はコピー、ダウンロード、フォルダへの保存（`<名前>.<言語>.md`） |
| 校正 | 同上 | 指摘（元の表記・修正案・理由）と、直した全文 |
| 図の生成 | 同上 | フローチャートなど 9 種類の図を Mermaid で描く。SVG のダウンロードと、`.mmd` のフォルダへの保存 |
| Web 抽出 | URL | 要約、本文の抽出、質問への回答 |
| 画像の生成 | プロンプト | 画像を作り、保存先フォルダに PNG で保存する。既定で無効 |
| コードの実行 | 選択中のファイル、またはテキストと、課題 | モデルが Python のプログラムを書き、ネットワークのないサンドボックスで実行して、出力から答える。回答、プログラム、各回の成否と出力を表示する。既定で無効 |
| マイユースケース | 選択中のファイル、またはテキスト | 保存したテンプレートの `{{input}}` に入力を入れて実行する |

![AI パネルのツールへの近道](screenshots/tools/tools-aipanel-ja.png)

![選択中のファイルを英語に翻訳](screenshots/tools/tools-translate-ja.png)

![ファイルから生成したフローチャート](screenshots/tools/tools-diagram-ja.png)

![画像の生成。日本の外で処理されることを画面に表示し、保存先フォルダに保存した](screenshots/tools/tools-image-ja.png)

![保存したユースケースを選択中のファイルで実行](screenshots/tools/tools-usecases-ja.png)

## ファイルの読み書きと権限

- **ファイルを読むとき**: `functions/file-tools` は、ファイルの質問（`ask-about-file`）と同じ順で確かめます。外部の利用者の AI 利用、パスの境界（`scope_for_caller`）、規制対象のフォルダ（`/dicom/`、`/phi/`、`/pii/`）、データの機密区分の順です。境界の外のファイルは、何かを読む前に拒否します。読むのは先頭の 100 KB までです
- **書き込むとき**: フォルダへの保存（翻訳などの結果、画像）は `toolsMutation` を通ります。ロールを強制しているときは、書き込みロール（contributor、storage-admin）だけが使えます。リゾルバーが `writeOperation` を設定するので、`toolsQuery` から書き込むことはできません。同じ名前のファイルは上書きせず、`-1` などを付けます
- **ユースケースを保存するとき**: ユースケースの保存・削除は `toolsUseCaseMutation` を通ります。ユースケースは利用者本人のプロンプトのひな形で、専用の DynamoDB テーブルに利用者 ID ごとに入り、ファイルシステムには何も書きません。そのため、ロールを強制しているときも、ポータルのロール（viewer、contributor、storage-admin、auditor）をどれか持っていれば使えます。どのグループにも入っていないアカウントは使えません。このリゾルバーは `useCaseOperation` だけを設定するので、`toolsUseCaseMutation` からフォルダへ書き込むことはできません <!-- allow:not-a-claim: describes what this app permits, not a vendor limit -->
- **閲覧ロール**: 翻訳・校正・図の生成・Web 抽出と、ユースケースの作成・実行・削除ができます。フォルダへの保存はできません
- **Web 抽出**: ページは Lambda から取得します。公開されていないアドレス（プライベート、リンクローカル、メタデータの `169.254.169.254`、IPv6 のユニークローカル、IPv4 射影形式）に解決されるホスト、既定以外のポート、認証情報付きの URL は拒否します。接続は確かめたアドレスに固定し、リダイレクトは 1 段ごとに確かめ直します <!-- allow:not-a-claim: describes what this app refuses, not a vendor limit -->

## コードの実行
有効にすると「コードの実行」のタブが出ます。課題（例: 売上の列を月ごとに合計して、最も多い月を教える）と入力を渡すと、`functions/file-tools` の action `code` が次の順で動きます。

1. ファイルの境界を確かめます（`read_file_text`。ファイルの質問と同じ検査）。読めない、または分類で AI が使えないファイルは、モデルにもサンドボックスにも渡さず、ここで止まります。
2. モデルが Python のプログラムを書きます。モデルのプロンプトに入るのは課題、サンドボックス内の固定名（`doc1.txt`、文字を入力したときは `input.txt`）、元の拡張子だけで、ファイルの本文と元の名前は入りません。
3. AgentCore の組み込み Code Interpreter（`aws.codeinterpreter.v1`）にセッションを開き、入力を書き込み、プログラムを実行し、セッションを止めます。時間切れのときも止めます。
4. 失敗したら、プログラムとエラー（3,000 文字まで）を渡してモデルに直させます。出力は 6,000 文字までです。エラーと出力は `<input>` で包み、中の指示に従わないよう system に書いています。
5. 成功した出力から、モデルが回答を書きます。

| 上限 | 値 | 理由 |
|---|---|---|
| 1 リクエスト全体 | 25 秒 | AppSync のリゾルバーは応答を 30 秒までしか待たない。Lambda のタイムアウトを延ばしても、AppSync が先に切る |
| 実行 1 回 | 12 秒 | 最初の実行は `min(12 秒, 25 秒 − 経過 − 5 秒)`。5 秒は回答を書くための予約。残りが 3 秒未満なら実行しない |
| 実行回数 | 最大 2 回 | 2 回目は、1 回目の失敗が早く返ったときだけ時間に収まる。収まらない課題は「時間内に終わらなかった」と返す |

サンドボックスにはネットワークがなく、入るのはあなたが読める選択中のファイル（100 KB まで）または入力した文字だけです。閲覧ロールでも使えます。読み取りだけで、フォルダには書き込まないため、`toolsQuery` と同じ権限です（結果の保存は他のツールと同じく書き込みロールだけ）。Lambda のロールに足す権限は、`bedrock-agentcore:StartCodeInterpreterSession`、`InvokeCodeInterpreter`、`StopCodeInterpreterSession` の 3 つで、リソースは `arn:aws:bedrock-agentcore:<リージョン>:aws:code-interpreter/aws.codeinterpreter.v1` に限ります（アカウント部分は文字どおり `aws`）。
## 設定

`amplify/portal-config.ts` の `tools`、または環境変数で決めます。既存の `portal-config.ts` に `tools` が無くても、環境変数が使われます。

| 環境変数 | 既定 | 内容 |
|----------|------|------|
| `AMPLIFY_PORTAL_IMAGE_GENERATION_ENABLED` | `false` | 画像の生成 |
| `AMPLIFY_PORTAL_IMAGE_GENERATION_REGION` | `us-west-2` | 画像のモデルを呼ぶリージョン |
| `AMPLIFY_PORTAL_IMAGE_GENERATION_MODEL_ID` | `stability.stable-image-core-v1:1` | 画像のモデル。推論プロファイル（`us.` など）も指定でき、IAM はそれに合わせて作られる |
| `AMPLIFY_PORTAL_WEB_EXTRACT_ENABLED` | `true` | Web 抽出 |
| `AMPLIFY_PORTAL_CODE_EXECUTION_ENABLED` | `false` | コードの実行。`portal-config.ts` では `tools.codeExecution`。`true` のときだけ、Lambda の `CODE_INTERPRETER_ENABLED` と IAM、画面のタブが入る |

**[verified 2026-11-14 / ap-northeast-1、us-west-2 ほか 12 リージョン]** 東京リージョンには画像を出力するモデルがありません。 [E-019]テキストから画像を作るモデル（Stable Image Core / Ultra、SD3.5 Large）は、確かめた 14 リージョンのうち us-west-2 だけにあり、推論プロファイルはありません。このため既定は us-west-2 で、プロンプトと画像は日本の外で処理されます。画面にもそう表示します。テキストのツールは `jp.anthropic.claude-haiku-4-5-20251001-v1:0`（東京と大阪で処理）を使います。

## 確認結果

**[verified 2026-11-15 / ap-northeast-1]** Amplify sandbox で、storage-admin の利用者が `industry-packs/legal/` のファイルに対して確かめました。所要時間は 1 回ずつの観測値です。

| 確認したこと | 結果 |
|---|---|
| 選択中のファイルの英訳 | 6.7 秒。フォルダへの保存を 2 回行い、2 回目は上書きせず `contract-review-guidelines.md.en-1.md` になった |
| 図の生成（フローチャート） | 画面に描いた |
| 画像の生成（16:9） | 保存先フォルダに `contract-review-illustration.png` が保存され、ファイル一覧に出た |
| ユースケースの保存と、選択中のファイルでの実行 | 成功 |
| Web 抽出（公開ページ） | 4.8 秒 |
| Web 抽出のメタデータ URL | アプリ側で拒否（`the host resolves to an address that is not allowed`）。ポータルは AppSync 経由なので、手前に WAF はない |

**範囲**: 1 人の利用者（storage-admin）で確かめました。パスの境界、閲覧ロールの書き込み拒否、規制対象のフォルダの拒否は、`functions/file-tools/tests/` と `tests/components/FileTools.test.tsx` のテストで確かめていて、実機では確かめていません。

**この確認で見つかって直した不具合**: フォルダへの保存が 403 で失敗しました。Lambda のロールに `s3:ListBucket` が無いと、S3 は存在しないキーの HeadObject にも 404 ではなく 403 を返すため [E-020]、「名前が空いている」と「拒否された」を区別できませんでした。ロールに `s3:ListBucket` を足して直しました。403 を「空いている」とみなす直し方は、拒否を見落とすので採っていません。

## コードの実行の確認結果
**確認したこと（自動テスト）**: `functions/file-tools/tests/test_file_tools.py` と `tests/components/FileTools.test.tsx`。サンドボックスとモデルはスタブです。

- 設定が `true` でなければ動かず、サンドボックスもモデルも呼ばない
- 読めないファイルの名前も本文も、モデルとサンドボックスに渡らない。分類で AI が使えないファイルは入らない。外部の利用者は拒否される
- ファイルの本文は `doc1.txt`（文字入力は `input.txt`）としてサンドボックスにだけ入り、モデルのプロンプトには入らない
- 失敗が続いても 2 回で止まる。エラーは 3,000 文字、出力は 6,000 文字で切り、`<input>` で包んで渡す
- 時間が足りなければ次の実行を始めない（モデルが 9 秒かかると 2 回目は始まらない。20 秒かかると 1 回も始まらない）
- 時間切れでも、時間切れの後にセッションが開いた場合でも、セッションを止める
- 画面は、有効なときだけタブを出し、上限を表示し、ファイルのキーと課題だけを `toolsQuery` で送る

**実機での確認（2026-11-15/16、ap-northeast-1）**: 既存の Amplify sandbox に `AMPLIFY_PORTAL_CODE_EXECUTION_ENABLED=true` を付けてデプロイしました。AppSync の呼び出しは、サインインしたブラウザのトークンで行いました。所要時間は 1 回ずつの観測値です。

| 確認したこと | 結果 |
|---|---|
| storage-admin の利用者が、アクセスポイント上の CSV を入力に、売上の合計と最大の月を聞く | 合計 965、最大は 4 月（410）。AppSync の応答まで 6.3 秒。プログラムは 1 回で成功 |
| `time.sleep(120)` を求める課題（25 秒の枠） | 1 回目が時間切れ、2 回目が成功。全体 18.0 秒で返り、AppSync の 30 秒に収まった |
| internal グループだけの利用者が、許可外のキーを指定 | `key is outside the prefixes your groups may access` で 0.18 秒で拒否 |
| 同じ利用者が、許可内のキーを指定 | 実行できた |
| 同じ利用者が、機密の行（`SECRETSALARY`）を含むファイルを指定 | 拒否された。その利用者への応答のどこにも、機密の行は現れなかった |
| 画面 | 「コードの実行」タブ、環境の説明（Python 3.12、pandas と numpy、1 リクエスト最大 2 回、1 回 12 秒、全体 25 秒）、文字入力での実行、回答の表示 |

**確認していないこと**: 25 秒に近い最悪の場合（モデルがプログラムを書くのに長くかかったうえで、1 回目が時間切れになるなど）。上の 18.0 秒は 1 つの観測で、上限ではありません。回答まで写したスクリーンショットも未取得です（実行前の入力画面だけを撮っていて、このドキュメントには載せていません）。サンドボックスが aarch64 であることと、最小権限のロールで開始・実行・停止できることは、別のプロジェクト（RAG アプリ、ap-northeast-1、2026-11-15）の確認で、このポータルのテストと実機の確認では直接見ていません。

**確認で分かったこと**: sandbox の `S3AP_ALIAS` が指していたアクセスポイントが、すでに存在しませんでした。今回は使い捨てのボリュームとアクセスポイントを作って差し替えて確認し、確認後に元の値へ戻しました。実機のデプロイは、git で管理しない設定ファイルの 6 つの値（アクセスポイント、ONTAP の接続、VPC など）が空だと止まります。これは意図した保護です。sandbox を引き継ぐときは、設定値のアクセスポイントが実在するかを先に確かめてください。 <!-- allow:not-a-claim: describes this portal's deploy guard and a deleted access point in our own sandbox, not a vendor limit -->

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [業種別ユースケース](industry-use-cases.md) | AI 処理タブとエージェントのテンプレート |
| [UI コントリビューターガイド](CONTRIBUTING-UI.md) | 画面に機能を足す手順 |
