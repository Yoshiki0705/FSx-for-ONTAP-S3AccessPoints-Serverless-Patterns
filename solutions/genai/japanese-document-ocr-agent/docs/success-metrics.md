# Success Metrics：日本語文書 OCR × AI エージェント連携

Partner/SI の顧客会話で PoC の成否を判断するための指標です。数値は 1 つの環境で 4 件の架空文書を
1 回ずつ処理したサンプル実行のもので、本番の見積りではありません。文書の種類、解像度、枚数が変われば
結果も変わるため、自分の文書で測り直してください。測定条件は末尾にまとめています。

## Business Outcome

- 日本語を含むスキャン文書を、リージョンをまたがずに東京の Textract で読める。Textract の日本語対応と
  東京での提供開始は 2026-11-02 に発表された
  （[What's New](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)）。
- 原本は FSx for ONTAP に置いたまま処理できる。画像は bytes で渡すためコピーが作られず、PDF と TIFF は
  処理中だけ一時コピーが作られる（[architecture.md](architecture.md)）。
- エージェントが OCR を起動し、件数、信頼度、人の確認が必要な文書とその理由を確認できる。OCR の本文は
  エージェントに渡さない。人の確認に回す文書の絞り込みで、どれだけ作業が減るかは測っていない。

## Technical KPI

| 指標 | 測り方 | サンプル実行の値 |
|---|---|---|
| デプロイと削除 | `deploy-japanese-document-ocr-agent.sh` の所要時間 | CloudFormation の新規作成 2 分 46 秒、スタックの削除 3 分 35 秒（いずれも 1 回の測定） |
| 公開されるツール | `tools/list` | 5 |
| 画像 3 件（同期）の実行 | 実行の開始から終了まで | 約 11 秒（うち 1 件は壊れたファイルで失敗レコード） |
| 3 ページ PDF（非同期） | パターン経由の実行 | 約 12 秒（ポーリング 1 回） |
| 3 ページ PDF の Textract 直接 | `Start*` から結果の取得まで | `text` 11.8 秒、`structure` 6.3 秒 |
| 実行履歴イベント | `get_execution_history` の件数 | sync 1 件 13、async は 20 + 9 × ポーリング回数（[architecture.md](architecture.md)） |
| エージェントの往復 | Bedrock のツール利用ループ | 7 回と 11 回のツール呼び出し（[demo-guide.md](demo-guide.md)） |

東京の同期 API は 1 TPS のクォータです。同じ画像への `DetectDocumentText` を 20 回呼んだ結果は次のとおりです。

| クライアントのリトライ | 並列 | 成功 | スロットリング | 実効 TPS | 応答時間 p50（秒） |
|---|---|---|---|---|---|
| なし | 1 | 20 | 0 | 0.67 | 1.41 |
| なし | 2 | 16 | 4 | 0.89 | 1.62 |
| なし | 5 | 13 | 7 | 0.97 | 3.24 |
| adaptive（最大 5 回） | 1 | 20 | 0 | 0.56 | 1.65 |
| adaptive（最大 5 回） | 2 | 20 | 0 | 0.74 | 2.39 |
| adaptive（最大 5 回） | 5 | 20 | 0 | 0.74 | 5.81 |

`shared/textract_helper.py` のクライアントは adaptive の 5 回で、`MapConcurrency` の既定は 2 です。
リトライなしでは並列 2 から失敗が出ました。adaptive は失敗なく完了しましたが、並列を 5 に上げても
実効 TPS は 0.74 のままで、応答時間が伸びるだけでした。

## Quality KPI

4 件の架空文書を、このパターンの正規化（`text.txt`）のまま、正解テキストと比べた文字誤り率（CER）です。
NFKC 正規化と空白除去のうえで、編集距離を正解の文字数で割っています（`samples/score_ocr.py`）。

| 文書 | 経路 / プロファイル | 正解の文字数 | 編集距離 | CER | 主な違い | 平均信頼度 | 低信頼度の行にある文字 | 既定の閾値での判定 |
|---|---|---|---|---|---|---|---|---|
| 請求書 1（PNG） | sync / structure | 374 | 2 | 0.0053 | `〜` が `~`、`→` の欠落 | 0.9723 | 5% | HUMAN_REVIEW（表の結合セル） |
| 請求書 2（JPEG、回転とノイズ付き） | sync / structure | 344 | 15 | 0.0436 | `梱` が `栖`、`〜` が `~` | 0.9558 | 12% | HUMAN_REVIEW |
| メモ（PNG） | sync / text | 221 | 4 | 0.0181 | `→` の欠落 2、`〜` が `~`、`弧` が `孤` | 0.949 | 7% | HUMAN_REVIEW（0.949 < 0.95） |
| 契約書（PDF 3 ページ） | async / structure | 773 | 0 | 0.0 | なし | 0.9459 | 23% | HUMAN_REVIEW |

この表から読み取れることは次のとおりです。

- 信頼度は誤りの有無をどちらの向きにも示さなかった。契約書は誤りが 0 なのに、文字の 23% が信頼度 90 未満の
  行にあり、HUMAN_REVIEW になった。メモの「括弧」を「括孤」と読んだ行の信頼度は 98.2 だった。請求書 2 の
  `栖` の行は 64.8 だった。
- 4 件とも既定の閾値（自動承認 0.95、低信頼度の文字割合 0.05）で HUMAN_REVIEW になった。既定値は出発点で、
  4 件では調整できない。自分の文書で分布を測ってから決める。
- Textract は全角の記号や丸数字を別の文字で返す。`〜` は `~`、`①②③` は `1 2 3`、全角の記号は半角になり、
  `→` は落ちることがあった。比較や検索の前に NFKC で正規化する。

日本語に対する他の機能の挙動は次のとおりです（ap-northeast-1、2026-11-03）。

| 機能 | 結果 |
|---|---|
| Forms | リクエストは通る。請求書で 13 組、メモで 10 組のキーと値を返した。請求書は大半が合っていたが誤りもあり、メモは文を途中で分けた組（信頼度 53.7）だった。公式ドキュメントが日本語を非対応としているため提供しない |
| Queries（日本語の質問） | `InvalidParameterException` |
| AnalyzeExpense / AnalyzeID | `AccessDeniedException`（not allow listed）。提供しない |

## Cost KPI

Textract の費用はページ数と機能で決まります。東京リージョンの Price List（適用開始 2026-10-01、
バージョン 20261027）のページあたり単価は次のとおりです。

| 機能 | 単価（USD / ページ） |
|---|---|
| DetectDocumentText（`text`） | 0.0015 |
| AnalyzeDocument の Tables | 0.015 |
| AnalyzeDocument の Layout | 0.004 |
| Signatures（提供しない） | 0.0035 |
| Forms（提供しない） | 0.05 |

`structure` は Tables と Layout を使うため、単価の和で 0.019 / ページと見積もります（請求額とは
照合していません）。1,000 ページなら `text` が 1.5 USD、`structure` が 19 USD です。

そのほかに Step Functions（Standard、状態遷移課金）、Lambda（arm64）、AgentCore Gateway、項目抽出を
有効にした場合の Bedrock（モデルとトークン数に依存）、S3 と KMS がかかります。金額は時点情報のため、
提示する前に Pricing API で確認してください。

## Go / No-Go

進める条件は次のとおりです。DemoMode でワークフローが成功すること。`tools/list` が 5 つのツールを返すこと。
エージェントが起動、`DescribeExecution`（`ALL_DATA`）での確認、結果の報告を自律的に行えること。自分の文書で測った
CER と HUMAN_REVIEW の割合が、業務の許容範囲に収まること。共有環境では `AWS_IAM` を選んでいること。PDF と TIFF の
一時コピーを、運用が受け入れていること。

進めない典型的な理由は次のとおりです。日本語で Forms、Queries、AnalyzeExpense、AnalyzeID が必須であること。
共有環境の Gateway が `NONE` のままであること。原本のコピーを許さない運用で PDF の処理が必須であること。
VPC origin の Access Point を使うこと（関数を VPC 内に置く構成が別途必要です）。信頼度だけを自動承認の条件に
していること。

## 測定条件

- リージョン ap-northeast-1、測定日 2026-11-03、Textract のレスポンスの `model` は `1.0`。
- 文書は 4 件の架空文書で、OFL の日本語フォント（BIZ UD ゴシック）で描画した。請求書 2 は軽い回転と
  ノイズを加えた JPEG、契約書は画像だけの 3 ページ PDF（テキスト層なし）。各文書を 1 回ずつ処理したため、
  ばらつきは測っていない。
- スロットリングの測定は同じ画像への `DetectDocumentText` を 20 回呼んだもので、`AnalyzeDocument` では
  測っていない。
- 本番の見積りではなく、サンプル実行の値である。

## 測っていないもの

- 実際のスキャン文書（手書き、印影、傾きの大きいもの、低解像度、縦書き）の精度。
- 100 件規模の実行と、ポーリング 23 回に達する最悪ケースの実行履歴。
- 既存の S3 Access Points での OCR の成功。検証に使った環境の Access Point には画像と PDF がなく、共有ボリュームに
  書き込まなかったため、一覧の取得、bytes の取得、一時コピーと削除までを確認し、Textract の応答は
  テキストファイルへの拒否（`UnsupportedDocumentException` と `INVALID_IMAGE_TYPE`）だけを見た。
- 捏造された根拠を `grounded: false` にする動作の実機確認（単体テストのみ）。4 回の実機の実行で
  モデルは、書かれていない項目に `null` を返した。
- 文書の中に指示を書いた場合の挙動。
- Nova Pro 以外のモデル、AgentCore Runtime や Strands を使ったエージェント。
