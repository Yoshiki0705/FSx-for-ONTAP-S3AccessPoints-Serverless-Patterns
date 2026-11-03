# アーキテクチャ：日本語文書 OCR × AI エージェント連携

FSx for ONTAP の S3 Access Points 上のスキャン文書を Amazon Textract（東京リージョン）で読み、
その実行を AgentCore Gateway 経由で AI エージェントのツールにする構成です。測定値は
[success-metrics.md](success-metrics.md) にあり、ここでは設計の理由と上限を扱います。

## 構成

```
AI エージェント ──MCP──▶ AgentCore Gateway（NONE | AWS_IAM）
                              │ states コネクタ。StartExecution / ListExecutions /
                              │ DescribeStateMachine はステートマシン ARN を固定
                              ▼
                  Standard ステートマシン
  Discover ─▶ HasDocuments ─▶ Map（ItemProcessor、同時実行 MapConcurrency）─▶ Report ─▶ Done / Fail
                                   │
            ┌──────────────────────┴───────────────────────┐
            ▼ route=sync（画像 5 MiB 以下）                  ▼ route=async（PDF / TIFF / 5 MiB 超の画像）
      OcrSync（bytes を inline で渡す）            AsyncStart ─▶ Wait ─▶ AsyncCheck ─┐
            │                                      （一時コピー + Start*）  ▲ IN_PROGRESS │
            │                                                 └──────────────────────┘
            │                                      AsyncCollect（Get* を辿る。一時コピーを削除）
            └─────────▶ [ExtractFields（任意、Bedrock）] ─▶ Summarize
   読み取り: S3 Access Points（DemoMode は通常の S3 バケット）
   書き込み: 結果バケット（result.json / text.txt / fields.json / manifest.json）
```

- 手順の順序、分岐、再試行、失敗の扱いはステートマシンが持ちます。エージェントが渡すのは
  「どのコレクションを、どのプロファイルで、何件まで」だけです。
- OCR 本文は状態遷移に載せません。本文は結果バケットに置き、実行結果には件数、信頼度、
  要レビューの一覧、S3 の参照だけを返します（claim check）。
- Textract は Lambda と同じリージョン（東京）で呼びます。クロスリージョンの切り替えは持ちません。
- 既存の [stepfunctions-agentcore-tools](../../stepfunctions-agentcore-tools/) との違いは、
  入力が許可リストの `collection` ID だけであること、入力不正と全件失敗を FAILED で返すこと、
  実行結果が本文を持たないことです。

## 処理経路の決め方

`discovery` が文書ごとに決めます。PDF のページ数は推定しません（推定が外れる経路より、常に
非同期にするほうが確実なため）。

| 文書 | 経路 | 理由 |
|---|---|---|
| PNG / JPEG、5 MiB 以下 | sync | 同期 API に bytes を渡せる上限（API リファレンスの `Bytes`）に収まる |
| PNG / JPEG、5 MiB 超 10 MiB 以下 | async | 非同期 API の画像の上限は 10 MiB |
| PDF / TIFF | async | 同期 API は PDF と TIFF を 1 ページしか受け付けない |
| 上記以外の拡張子、空、10 MiB を超える画像、`MaxDocumentBytes` 超過 | スキップ | 理由（`unsupported_extension`、`empty`、`image_too_large`、`too_large`）を `skipped` に記録する |

プロファイルで呼ぶ API が決まります。`text` は `DetectDocumentText`、`structure` は
`AnalyzeDocument`（`TABLES` と `LAYOUT`）です。Forms は日本語に対応していないため提供しません。

## S3 Access Points の制約への対応

Textract は S3 Access Points を参照渡しで読めません。そのため経路ごとに次のようにします。

- sync: Lambda が `S3ApHelper` で bytes を取得し、`Document={"Bytes": ...}` で渡します。
- async: PDF / TIFF を、同じアカウント・同じリージョンの一時バケットへコピーしてから
  `Start*` を呼びます。ジョブが終わると `AsyncCollect` がコピーを削除します。1 日で失効する
  ライフサイクルルールは削除漏れに備えた保険です。一時バケットは SSE-KMS（`aws/s3`）、
  公開ブロック、TLS 以外を拒否するバケットポリシーで保護します。

一時コピーは原本が FSx for ONTAP の外にも一時的に存在することを意味します。コピーを許さない
運用では、コレクションの `suffixes` を `.png` / `.jpg` / `.jpeg` に絞ります。画像は bytes で渡すため
コピーが作られません。

## 結果の保存先と実行結果

結果バケットには次のキーで書きます。`doc_id` は原本キーの SHA-256 の先頭 16 文字で、日本語を含む
キーをパスに使わないための置き換えです。原本のキーは `result.json` と `manifest.json` に持ちます。

| キー | 内容 |
|---|---|
| `{collection}/{execution}/{doc_id}/result.json` | ページ、行、信頼度、表、レイアウト、品質指標、Textract のモデル版、OCR だけの判定 |
| `{collection}/{execution}/{doc_id}/text.txt` | OCR テキスト |
| `{collection}/{execution}/{doc_id}/fields.json` | 項目抽出の値、根拠、モデル ID（項目抽出を有効にしたときだけ） |
| `{collection}/{execution}/manifest.json` | 全文書の一覧と、項目抽出を含めた最終の判定 |

判定は 2 か所にあります。`result.json` は OCR だけの判定を持ち、項目抽出で根拠のない項目があれば
`manifest.json` と実行結果の `action` が `HUMAN_REVIEW` に引き上がります。最終の判定は
`manifest.json` と実行結果を読みます。

`DescribeExecution` の出力（SUCCEEDED）は次の形です。

```json
{
  "status": "completed | completed_with_errors",
  "collection": "invoices", "profile": "structure", "region": "ap-northeast-1",
  "summary": {"total": 3, "succeeded": 2, "failed": 1, "skipped": 1, "pages": 2,
              "review_required": 2, "mean_confidence": 0.9641,
              "errors": {"UnsupportedDocumentException": 1}},
  "review_queue": ["<key>"],
  "documents": [{"key": "<key>", "doc_id": "...", "status": "completed", "pages": 1,
                 "api": "AnalyzeDocument", "mean_confidence": 0.9723, "action": "HUMAN_REVIEW",
                 "review_reason": "5% of characters are in low-confidence lines; ...",
                 "result": "s3://<results-bucket>/.../result.json",
                 "fields": {"status": "completed", "ungrounded_count": 1,
                            "values": {"請求書番号": "INV-2026-0001", "担当者名": null},
                            "ungrounded": ["担当者名"]}}],
  "documents_truncated": false,
  "skipped": [{"key": "<key>", "reason": "unsupported_extension"}],
  "output": {"prefix": "invoices/<execution>", "manifest": "s3://<results-bucket>/.../manifest.json"},
  "data_classification": "RESTRICTED"
}
```

`fields` は項目抽出を有効にし、コレクションに `fields` があるときだけ付きます。値は 60 文字で切り、
根拠の引用は載せません（`fields.json` にあります）。入力不正と全件失敗の実行は FAILED になり、
`Error` と `Cause` に理由が入ります。一部だけ失敗した実行は SUCCEEDED で、`status` が
`completed_with_errors` になります。

## 状態の大きさ

Step Functions の状態は 1 つにつき 256 KiB（262,144 バイト）までです。3 か所で上限を抑えています。

| 場所 | 抑え方 |
|---|---|
| Map の各文書の記録 | 本文を載せない。項目抽出の記録は件数と S3 参照だけ（約 140 バイト）。値と根拠は `fields.json` に書き、`report` が読み直す |
| Map の終了時点の状態 | `discovery` が選ぶ文書数を、キーの長さを含めた見積りで制限する（下記） |
| 最終の実行結果 | `report` が文書ごとの大きさを見積もり、150,000 バイトを超える分を切り詰めて `documents_truncated: true` を立てる。全件は `manifest.json` |

Map が終わった時点の状態は、リクエスト、`discovery` の出力（`objects` と `skipped`）、文書ごとの結果
（`processed`）を同時に持ちます。キーは `objects` と `processed` の両方に現れるため、長いキーが多いと
文書数が 100 でも上限を超えます。実際の `discovery` と各ハンドラーの出力から状態を組み立てて計算すると、
次のとおりでした（項目抽出あり、各記録を最悪値で埋めた場合。2026-11-03、ローカルでの計算）。

| 文書数 | キーの長さ | 状態の大きさ |
|---|---|---|
| 100 | 約 105 バイト（日本語 30 文字） | 約 136 KB |
| 100 | 約 315 バイト（日本語 100 文字） | 約 188 KB |
| 100 | 約 900 バイト | 約 340 KB（上限超過） |

`discovery` は 1 文書あたり `キーのバイト数 × 2 + 1,700` の見積りを足し上げ、`2,000 + skipped の大きさ`
を含めて 230,000 バイトに収まる範囲で、キー順の先頭から文書を選びます。選びきれなかった場合は
`truncated: true` になります。この見積りが実際の状態より小さくならないことは
`tests/test_state_budget.py` が、実際のハンドラーの出力を最悪値で埋めて確かめます。
通常のキー（日本語 30 文字程度）では 100 件すべてが収まり、切り詰めは起きません。

## 実行履歴イベント

Standard ワークフローの実行履歴は 25,000 イベントまでです。実機の実行履歴を数えた結果は次のとおりです
（2026-11-03、ap-northeast-1）。

| 状態の種類 | イベント数 |
|---|---|
| Task | 5 |
| Wait / Choice | 2 |
| ポーリング 1 回（Wait + AsyncCheck + Choice） | 9 |
| 空のコレクション | 20 |
| 文書がある実行の枠（Map の開始と終了を含む） | 22 |
| sync の文書 1 件（失敗を失敗レコードで返した場合も同じ） | 13（項目抽出ありで +5） |
| async の文書 1 件 | 20 + 9 × ポーリング回数（項目抽出ありで +5） |

実測した実行は、メモ 1 件が 35、請求書 3 件が 61（項目抽出を 2 件に付けて 71）、契約書 PDF 1 件が
ポーリング 1 回で 51 イベントでした。待機は 5、10、15、20 秒のあと 30 秒刻みで、最悪（600 秒まで
待つ）はポーリングが約 23 回、項目抽出ありの 1 文書で約 232 イベント、100 文書で約 23,200 です。
`MaxFilesPerExecution` の上限を 100 にしたのは、この最悪値が 25,000 に収まるからです。23 回の
ポーリングに達する実行は再現できなかったため、最悪値は上の単価からの計算です。再試行の
イベントは見積りに含めていません。

## 失敗の扱い

`shared/textract_helper.py` が Textract の例外を 3 種類に分けます。

| 例外 | 元のコード | Step Functions の扱い |
|---|---|---|
| `TextractThrottled` | `ThrottlingException`、`ProvisionedThroughputExceededException`、`LimitExceededException` | 4 秒から倍々、最大 6 回、上限 60 秒、ジッターあり |
| `TextractTransient` | `InternalServerError`、`ServiceUnavailable`、`RequestTimeout`、接続・読み取りのタイムアウト | 5 秒から倍々、最大 3 回 |
| `TextractRejected` | `UnsupportedDocumentException`、`BadDocumentException`、`DocumentTooLargeException`、`InvalidParameterException`、`InvalidS3ObjectException`、`AccessDeniedException`、`InvalidKMSKeyException` | 再試行しない。失敗レコードとして返し、他の文書は続ける |

非同期ジョブの失敗とタイムアウトも、再試行しても結果が変わらないため、失敗レコードで返します。
`AsyncCheck` が失敗しても `AsyncCollect` へ進み、一時コピーを必ず削除します。項目抽出の失敗は
OCR の結果を捨てず、`fields.status: failed` を記録して、その文書を `HUMAN_REVIEW` に引き上げます。

## 認証と IAM

- Gateway は `GatewayAuthorizerType`（`NONE` | `AWS_IAM`）で切り替えます。`AWS_IAM` では呼び出し側が
  SigV4（サービス名 `bedrock-agentcore`）で署名し、`bedrock-agentcore:InvokeGateway` を持つ必要が
  あります。署名のない `tools/list` は 401、署名ありは 200 を返すことを実機で確認しました。
  authorizer の種類は作成後に更新できません。`NONE` から `AWS_IAM` へ変えるには新しいスタックが要ります。<!-- [E-017] -->
- `GatewayServiceRole` が Step Functions を呼びます。固定する 3 操作はステートマシンの ARN に、
  `DescribeExecution` と `GetExecutionHistory` はこのスタックの実行の ARN に限定します。
  `StopExecution` と `Send*` は公開せず、権限も付けません。
- Textract の操作にはリソースレベルの権限がないため `Resource: "*"` です。Action は関数ごとに
  必要なものだけを列挙します。Bedrock の権限は `EnableFieldExtraction=true` のときだけ付きます。
- 全関数は VPC の外に置きます。Internet origin の S3 Access Points を前提にしており、VPC origin の
  Access Point を使う場合は関数を VPC 内に置く構成が別途必要です。

## 失敗の想定と影響範囲

| # | 失敗 | 兆候 | 緩和 | 影響範囲 |
|---|---|---|---|---|
| 1 | 東京の同期 1 TPS でスロットリング | `TextractThrottled` の再試行が増える | adaptive リトライ、`MapConcurrency` 既定 2、PDF は非同期、クォータ引き上げ | その実行の所要時間 |
| 2 | 状態が 256 KiB を超える | `States.DataLimitExceeded` | 上の 3 か所の抑え方とテスト | 1 実行 |
| 3 | 一時コピーが残る | ステージングバケットにオブジェクトがある | 終端で削除、1 日のライフサイクル、公開ブロック、SSE-KMS | 同じリージョンの 1 日分 |
| 4 | エージェントの想定外の入力 | `InvalidInput` で FAILED | 許可リストの ID、厳格な検証、`Cause` に直し方を書く | なし（実行前に拒否） |
| 5 | 高い信頼度のまま誤読する | 信頼度が高いのに文字が違う | 信頼度は補助信号と明記、Human Review、正解つきサンプルで測定 | 下流の利用者 |
| 6 | Gateway が `NONE` のまま公開される | 第三者が OCR を起動できる | PoC 限定の明記、`AWS_IAM`、許可リストと件数上限。本文は返さない | 課金と処理負荷 | <!-- allow:not-a-claim: describes this pattern's own output, not a vendor capability -->
| 7 | LLM が項目を捏造する | 値が原文にない | 根拠の照合、根拠なしが 1 つでもあれば HUMAN_REVIEW | 項目抽出を有効にした文書 |
| 8 | 非同期ジョブが終わらない | `JobTimeout` | `AsyncJobMaxSeconds`。Textract はジョブを取り消せない | 課金が続く可能性 |
| 9 | 実行履歴が 25,000 イベントを超える | 実行の失敗 | 待機間隔の段階的な延長、件数の上限 | 1 実行 |
| 10 | Textract がないリージョンへのデプロイ | 実行時のエンドポイントエラー | 提供状況は公式の Endpoints and quotas で確認する（一覧は固定しない） | デプロイ直後の検証 |

ロールバックは `scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name <name>` です。
結果バケットは OCR テキストを持つため `Retain` で、`--delete-results` を付けたときだけ削除します。
監査証跡は Step Functions の実行履歴、`manifest.json`、CloudTrail です。このパターンはシークレットを持ちません。

## 扱わないもの

- 結果リーダー（`result.json` をページ単位で返す Lambda ターゲット）: 返す範囲が広がるため、呼び出し元ごとの
  コレクション制限と監査を決めてから追加します。
- Forms、Queries、AnalyzeExpense、AnalyzeID: 日本語に対応していない、または東京で利用が許可されて
  いません（[success-metrics.md](success-metrics.md) の測定条件を参照）。
- 数千件規模の処理: Distributed Map と `ResultWriter` を使う別の構成になります。
- `OutputDestination=FSXN_S3AP`: `shared/output_writer.py` にある機能ですが、このパターンの範囲外です。
