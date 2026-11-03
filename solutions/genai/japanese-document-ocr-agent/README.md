# 日本語文書 OCR × AI エージェント：Textract（東京）を S3 Access Points の上で動かす

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

FSx for ONTAP の S3 Access Points 上にあるスキャン文書（画像、PDF、TIFF）を、Amazon Textract の東京リージョンで
日本語 OCR し、その実行を Amazon Bedrock AgentCore Gateway の Step Functions コネクタ経由で AI エージェントの
ツールにするサンプルです。Textract の日本語対応と東京リージョンでの提供開始は 2026-11-02 に発表されました。

エージェントが決めるのは「どのコレクションを、どのプロファイルで、何件まで」だけです。手順の順序、再試行、
失敗の扱いはステートマシンが持ちます。OCR の本文はエージェントに渡さず、結果バケットに置きます。

## ユースケース

- 請求書、契約書、メモなどのスキャン文書を、ファイルサーバーに置いたまま日本語 OCR する
- 人の確認が必要な文書とその理由を、エージェントに洗い出させる
- Textract の Forms が使えない日本語の請求書から、合計金額などの項目を根拠つきで取り出す（任意）

## アーキテクチャ

```
AI エージェント ──MCP──▶ AgentCore Gateway（NONE | AWS_IAM）
                              │ GatewayServiceRole で states:StartExecution 等
                              ▼
                  Standard StateMachine（Discover → Map → Report）
                              │
        画像: bytes を渡して Textract 同期   PDF / TIFF: 一時コピー → Textract 非同期
                              │
        S3 Access Points（DemoMode は通常 S3） ──▶ 結果バケット（result.json / text.txt / manifest.json）
```

詳細は [docs/architecture.md](docs/architecture.md) を参照してください。

## 公開されるツール

| ツール | 入力 | 用途 |
|---|---|---|
| `ocr___StartExecution` | `input`（JSON 文字列） | OCR の起動。`executionArn` を返す |
| `ocr___DescribeExecution` | `executionArn`、`includedData: "ALL_DATA"` | 状況と結果の確認 |
| `ocr___ListExecutions` | `statusFilter`（任意） | 直近の実行の一覧 |
| `ocr___GetExecutionHistory` | `executionArn` | 停止箇所の調査（出力が大きい） |
| `ocr___DescribeStateMachine` | `includedData`（任意） | 定義の確認 |

固定したステートマシン ARN はツールに出ず、エージェントは変更できません。`includedData: "ALL_DATA"` を
付けない `DescribeExecution` は、`output` も、FAILED の `error` と `cause` も返しません。

## エージェントが渡す入力

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| キー | 必須 | 規則 |
|---|---|---|
| `collection` | はい | ASCII の ID（`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`）。許可リスト（`CollectionsJson`）にあるもの |
| `profile` | いいえ | `text`（文字だけ）または `structure`（文字、表、レイアウト）。省略するとコレクションの設定 |
| `max_files` | いいえ | 1 から `MaxFilesPerExecution` までの整数。キー順の先頭から選ぶ |
| `modified_after` | いいえ | `YYYY-MM-DD`。それ以降に更新された文書だけ |

S3 のパスやキーは受け取りません。未知のキーや規則違反は FAILED になり、`Cause` に直し方が入ります。

## 処理経路とプロファイル

| 文書 | 経路 | 備考 |
|---|---|---|
| PNG / JPEG、5 MiB 以下 | 同期。bytes を渡す | 一時コピーなし |
| PNG / JPEG、5 MiB 超 10 MiB 以下 | 非同期。一時コピー | |
| PDF / TIFF | 非同期。一時コピー | ページ数は推定しない |

`text` は `DetectDocumentText`、`structure` は `AnalyzeDocument`（`TABLES` と `LAYOUT`）です。Forms、Queries、
AnalyzeExpense、AnalyzeID は提供しません（日本語に非対応、または東京で利用が許可されていません）。

## エージェントに返るもの

`DescribeExecution`（`ALL_DATA`）の `output` に、状態、件数、平均信頼度、要レビューの一覧とその理由、
文書ごとの結果の S3 URI が入ります。OCR の本文は入りません。ただし原本のキー（ファイル名）は返ります。
項目抽出を有効にした場合は、項目の値（60 文字まで）が入ります。全文書の完全な一覧は結果バケットの
`manifest.json` にあります。

## パラメータ

| パラメータ | 説明 | デフォルト |
|---|---|---|
| `S3AccessPointAlias` | S3 Access Points の alias（DemoMode では通常のバケット名） | (必須) |
| `DemoMode` | `true` で FSx for ONTAP なしで動く | `false` |
| `CollectionsJson` | コレクションの許可リスト（JSON）。空なら `FilePrefix` から 1 つ作る | `""` |
| `MaxFilesPerExecution` | 1 実行あたりの最大文書数（1〜100） | `50` |
| `MapConcurrency` | 並列に処理する文書数。東京の同期 API は 1 TPS | `2` |
| `AsyncJobMaxSeconds` | 非同期ジョブを待つ秒数 | `600` |
| `EnableFieldExtraction` | Bedrock による項目抽出。無効なら Bedrock の権限を付けない | `false` |
| `BedrockModelId` | 項目抽出のモデルまたは推論プロファイル ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | 出力に付けるデータ分類の既定 | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | 平均信頼度の閾値 | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | 低信頼度の行の基準と、文書を要レビューにする文字割合 | `90` / `0.05` |
| `HandwritingWordRatioLimit` | 手書きと判定された単語の割合の上限 | `0.05` |
| `GatewayAuthorizerType` | `NONE`（PoC 専用）または `AWS_IAM` | `NONE` |
| `GatewayName` | Gateway 名 | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS 通知先（空でスキップ） | `""` |

## デプロイ

deploy スクリプトは `sam build`、`sam package`、`aws cloudformation deploy` の順に実行し、デプロイ後に
`CollectionsJson` の値と `tools/list` を確認します。

```bash
# DemoMode（FSx for ONTAP 不要）
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points。呼び出し側に署名を求め、項目抽出を有効にする
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# 後片付け（--delete-results を付けると OCR テキストを持つ結果バケットも削除）
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

コレクションの書き方、エージェントのシステムプロンプト、会話例は [docs/demo-guide.md](docs/demo-guide.md) にあります。

## Human Review 閾値

OCR の平均信頼度（文字数で重み付け）を `shared/human_review.py` で評価し、次の条件で引き上げます。

| 条件 | 判定 |
|---|---|
| 平均信頼度が `ReviewAutoApproveThreshold`（0.95）以上で、下の条件がない | AUTO_APPROVE |
| 平均信頼度が 0.95 未満 | HUMAN_REVIEW |
| 平均信頼度が `ReviewRejectThreshold`（0.30）未満 | REJECT |
| 信頼度 90 未満の行にある文字が全体の 5% を超える | HUMAN_REVIEW に引き上げ |
| 手書きと判定された単語が 5% を超える | HUMAN_REVIEW に引き上げ |
| 結合セルなど、構造が疑わしい表がある | HUMAN_REVIEW に引き上げ |
| 行が 1 つも検出されない | HUMAN_REVIEW |
| 項目抽出で根拠のない項目がある、または抽出に失敗した | HUMAN_REVIEW に引き上げ（REJECT は変えない） |

既定の閾値は出発点で、最適値を測ったものではありません。4 件の架空文書では、誤りが 0 の契約書を含む 4 件
すべてが既定の閾値で HUMAN_REVIEW になりました（[docs/success-metrics.md](docs/success-metrics.md)）。
自分の文書で分布を測ってから決めてください。判定は結果に含めるだけで、このパターンは最終判断をしません。
`result.json` は OCR だけの判定を持ち、項目抽出を含めた最終の判定は `manifest.json` と実行結果にあります。

## データ分類

出力には `shared/data_classification.py` 由来の `data_classification` が付きます。既定は `INTERNAL` で、
`DataClassification` で変えるか、コレクションごとに `classification` で上書きします。結果バケットは SSE-KMS、
公開ブロック、TLS 以外の拒否を設定し、スタックを削除しても残ります。

## 項目抽出（任意）

`EnableFieldExtraction=true` で、コレクションの `fields` に書いた項目（20 個まで、各 40 文字まで）を Bedrock の
Converse API で取り出します。モデルには値と一緒に原文からの引用を返させ、引用が OCR テキストに実在するか
（NFKC 正規化と空白除去のうえで部分一致）を機械的に確かめます。実在しない項目は `grounded: false` で、
1 つでもあれば文書は HUMAN_REVIEW になります。書かれていない項目も根拠なしに数えるため、`fields` には
そのコレクションのすべての文書にある項目だけを挙げてください。

## Governance Note

- OCR の信頼度は補助信号であり、最終判断ではありません。実測では、誤りが 0 の文書で文字の 22.6% が信頼度
  90 未満の行にあり、誤読された「括孤」の行の信頼度は 98.2 でした。信頼度だけを自動承認の条件にしないでください。
- 項目抽出の値は LLM の出力です。引用の照合は捏造を減らしますが、正しさを保証しません。
- 文書の中身から取り出した値は、エージェントにとって信頼できない入力です。値に指示のような文が入っても
  従わないよう、システムプロンプトで伝えてください。文書に指示を書いた場合の挙動は測っていません。
- PDF と TIFF は、処理の間だけ同じアカウント・同じリージョンの一時バケットにコピーされます（SSE-KMS、
  公開ブロック、終了時に削除、1 日のライフサイクルが保険）。コピーを許さない運用では、コレクションの
  `suffixes` を画像に絞ってください。
- `GatewayAuthorizerType=NONE` は URL を知る誰もが OCR を起動できます（本文は返りません）。PoC 専用で、
  共有環境では `AWS_IAM` を使います。authorizer の種類は作成後に変更できません。<!-- [E-017] -->
- Textract は起動したジョブを取り消せません。`AsyncJobMaxSeconds` で待つのをやめても、課金は続きえます。<!-- [E-018] -->
- これはガバナンスの指針であり、法務・コンプライアンス上の判断を代替しません。

## Performance Considerations

- 東京の同期 API は 1 TPS です。20 回の連続呼び出しで、リトライなしのクライアントは並列 2 で 4 回、並列 5 で
  7 回スロットリングされ、adaptive（最大 5 回）は並列 1、2、5 とも 0 回でした。`MapConcurrency` の既定は 2 です。
- 3 ページの PDF（非同期）は、パターン経由で約 12 秒でした。
- 実行履歴のイベントは、sync の文書 1 件で 13、async は 20 + 9 × ポーリング回数です。最悪でも 100 文書で約
  23,200 と見積もり、Standard の上限 25,000 に収まります。
- Map の状態が 256 KiB を超えないよう、キーが非常に長い場合は `max_files` より少ない件数を選び、`truncated`
  を返します。
- 費用は Textract がページ数で決まります。東京の Price List では `text` が 0.0015 USD / ページ、`structure`
  （Tables と Layout の和）が 0.019 USD / ページです（適用開始 2026-10-01。請求額とは照合していません）。

## テスト

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## 既知の注意点

- Forms は日本語に対応していません。リクエストは通りますが、メモでは文を途中で分けた組を返しました。
- `DescribeExecution` は `includedData: "ALL_DATA"` が必要です。`GetExecutionHistory` はページを送れません。
- Gateway の入力に日本語を渡すと `??` になります。このパターンは ASCII の ID だけを渡します。
- `max_files` はキー順の先頭から選ぶため、先頭の文書が壊れていると毎回その文書が選ばれます。
- 検証に使った環境の S3 Access Points には画像と PDF がなく、実機で OCR の成功までは確認していません
  （一覧、取得、一時コピーの削除は確認）。詳細は [docs/demo-guide.md](docs/demo-guide.md) の「既知の注意点」にあります。

## 参考

- [Amazon Textract が日本語を含むサポート言語を追加し、東京リージョンで提供開始（What's New）](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target（公式）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- 関連パターン: [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## 本番に出す前に読むもの

デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあります。同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。

- [データ活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-utilization) — S3 Access Point 経由の制約（全パターン共通）
- [セキュリティ・ガバナンス](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/security-governance) — このパターンで判断が集中するところ
- [構築](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/04-build) — 本番前に通す（全パターン共通）
<!-- playbook-reading:end -->
