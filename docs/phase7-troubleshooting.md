# Phase 7 トラブルシューティングガイド

UC15（Defense/Satellite）、UC16（Government Archives/FOIA）、UC17（Smart City Geospatial）の
デプロイ・実行時によく遭遇する問題と対処法をまとめる。**2026-05-10 の AWS 東京リージョン
デプロイ検証（`fsxn-uc15-demo` / `fsxn-uc16-demo` / `fsxn-uc17-demo`）で実際に発生した
事象がベース**。

## 1. IAM / Permissions

### 1.1 `AccessDenied` on `s3:ListBucket` for Access Point

**症状**:
```
User: arn:aws:sts::...:assumed-role/fsxn-uc15-demo-discovery-role/...
is not authorized to perform: s3:ListBucket
on resource: "arn:aws:s3:ap-northeast-1:<ACCOUNT_ID>:accesspoint/eda-demo-s3ap"
```

**原因**: FSx ONTAP の S3 Access Point を使用する Lambda は、**Alias ARN と Access Point ARN
の両方**に対する権限が必要。`template-deploy.yaml` のデフォルトは Alias ARN のみ。

**対処**:
```bash
aws cloudformation deploy ... \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-...-ext-s3alias \
    S3AccessPointName=eda-demo-s3ap   # <- これを必ず指定
```

`HasS3AccessPointName` 条件が `true` になると、IAM Policy に以下の 2 つが追加される:
- `arn:aws:s3:ap-northeast-1:<account>:accesspoint/<name>`
- `arn:aws:s3:ap-northeast-1:<account>:accesspoint/<name>/*`

## 2. DynamoDB

### 2.1 `Float types are not supported. Use Decimal types instead.`

**症状**: UC15 ChangeDetection / UC17 ChangeDetection の Lambda が `TypeError` で失敗。

**原因**: boto3 DynamoDB リソースクライアントは Python `float` を受け付けない。

**対処**: コードには `_to_decimal` 再帰ヘルパーと `Decimal(str(value))` 変換が実装済み
（2026-05-10 の修正）。新規に Decimal 化が必要なフィールドを追加する場合は
`_to_decimal` を必ず通すこと。

```python
from decimal import Decimal

def _to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj
```

## 3. Rekognition

### 3.1 `InvalidImageFormatException: Request has invalid image format`

**症状**: UC15 ObjectDetection / UC17 LandUseClassification で発生。
Step Functions ワークフローが `States.Runtime` で停止し、後続のステップ（ChangeDetection
等）が `$.detection_result.detections` を取得できずに失敗。

**原因**: Rekognition は解析可能なフォーマット（JPEG/PNG）のみサポート。生の GeoTIFF や
破損したテストデータでは例外を返す。

**対処**: Lambda ハンドラは例外を catch して `detections=[]` で継続する実装済み。
`_detect_with_rekognition` 関数内:

```python
try:
    response = rekognition.detect_labels(...)
except rekognition.exceptions.InvalidImageFormatException as e:
    logger.warning("InvalidImageFormat, returning empty detections: %s", e)
    return []
```

ワークフロー全体は SUCCEEDED で完了するが、`detection_count=0` / `landuse_distribution={}`
となるため、本番画像（有効 JPEG/PNG または SageMaker ルート）に切り替えること。

### 3.2 `ImageTooLargeException`

**症状**: 5MB 超の画像で発生。

**対処**: `INFERENCE_TYPE` を `none` 以外（`provisioned` / `serverless` / `components`）に
設定し、SageMaker Batch Transform ルートへルーティング。デフォルトで無効化されている。

## 4. Textract (UC16)

### 4.1 `EndpointConnectionError: Could not connect to the endpoint URL "https://textract.ap-northeast-1.amazonaws.com/"`

**症状**: UC16 OCR Lambda が ap-northeast-1 で失敗。

**原因**: Amazon Textract は 2026-05 現在 ap-northeast-1 未対応。

**対処**: 2 つの選択肢。

**(A) クロスリージョン呼び出し（推奨、UC2/UC10/UC12/UC13/UC14 と同じ方針）**:

`template-deploy.yaml` のパラメータ:
```
CrossRegion: us-east-1
UseCrossRegion: "true"
```

Lambda 環境変数経由で `shared.cross_region_client.CrossRegionClient` に渡され、
us-east-1 の Textract に自動ルーティングする。

**(B) 同一リージョン fallback（劣化モード）**:

Textract が未対応のリージョンで検証を継続したい場合は、`api_used="unavailable"` が
返される（OCR テキストは空）。後続のエンティティ抽出・分類は空テキストで継続するので
ワークフロー自体は SUCCEEDED になる。

## 5. Step Functions

### 5.1 `States.ReferencePathConflict: Unable to apply step "objects"`

**症状**:
```
Unable to apply step "objects" to input {"discovery":{"statusCode":500,"body":"..."}}
```

**原因**: Discovery Lambda が失敗し、`statusCode: 500` エンベロープを返した場合、
Map state の `ItemsPath: $.discovery.objects` が参照できない。

**対処**: Discovery Lambda の失敗は IAM / VPC / S3 AP 設定に起因することがほとんど。
セクション 1.1 と 4.1 を確認。

### 5.2 `States.Runtime: The JSONPath '$.opensearch_enabled' ... could not be found`

**症状**: UC16 `IndexOrSkip` Choice ステートで発生。

**原因**: Step Functions の Map ステートは、ルート入力（root input）の値を各イテレーションに
自動伝搬しない。各 Item は Discovery Lambda が返した objects 配列の要素のみが渡される。

**対処**: `IsPresent: true` ガード付きの Choice 条件を使用（修正済み）:

```json
"IndexOrSkip": {
  "Type": "Choice",
  "Choices": [{
    "And": [
      {"Variable": "$.opensearch_enabled", "IsPresent": true},
      {"Variable": "$.opensearch_enabled", "StringEquals": "true"}
    ],
    "Next": "IndexGeneration"
  }],
  "Default": "ComplianceCheck"
}
```

`opensearch_enabled` が入力に含まれない場合は常に `Default` ブランチへ。

## 6. CloudFormation

### 6.1 `No changes to deploy. Stack ... is up to date`

**症状**: テンプレートを手元で編集したのに CloudFormation がスキップする。

**原因**: CloudFormation は文字列としての Description やコメント変更を認識しない場合がある。
IAM Policy の `Resource` リスト変更などは CloudFormation が「機能的変化なし」と判定して
新しいチェンジセットを作成しないことがある。

**対処**:
1. **Description を明示的に変更**（例: "v1" → "v2" と記載）
2. **`aws cloudformation update-stack` を直接呼ぶ**
3. それでもダメなら **スタック削除 + 再作成**（DynamoDB 等の DeletionPolicy: Retain リソースは残るので、
   `scripts/cleanup_phase7.sh` で手動削除してから再デプロイ）

### 6.2 `Stack with id fsxn-uc15-demo does not exist`

**症状**: 検証後にクリーンアップ済みの正常状態。確認用コマンドは OK。

## 7. Bedrock (UC17)

### 7.1 `AccessDeniedException: You don't have access to the model`

**症状**: UC17 ReportGeneration で発生する可能性あり。

**原因**: Bedrock はアカウントでモデルアクセス許可が必要。

**対処**: [Bedrock console](https://console.aws.amazon.com/bedrock/) → Model access
→ `amazon.nova-lite-v1:0` を有効化。

### 7.2 Bedrock 出力が想定外

**症状**: 生成されたレポートが空、または文字化け。

**対処**:
- プロンプトを `docs/uc17-architecture.md` の例に合わせる
- 複数テンプレートで試す（Claude Haiku は別 ARN `anthropic.claude-3-haiku-20240307-v1:0`）
- `build_prompt()` 関数でプロンプトをカスタマイズ

## 8. Local Development / Testing

### 8.1 cfn-lint が数十分フリーズする

**症状**: `python3 -c "from cfnlint import api; api.lint_all(...)"` でプロセスが応答しない。

**原因**: cfn-lint の Python API は内部で CloudFormation スキーマの遅延解決を行い、
複数テンプレートを 1 プロセスで連続実行するとキャッシュ競合でハングする場合がある。

**対処**: `scripts/lint_phase7_templates.sh` を使う（cfn-lint CLI バイナリを個別プロセスで
呼び出す軽量版、15-30 秒で完了）:

```bash
bash scripts/lint_phase7_templates.sh                    # 全 3 テンプレート
bash scripts/lint_phase7_templates.sh defense-satellite  # 1 つだけ
```

### 8.2 pytest が `ImportPathMismatchError` で失敗

**症状**:
```
ERROR: imported module 'test_discovery' has this __file__ attribute ...
which is not the same as the test file we want to collect
```

**原因**: UC15/16/17 で同名の `test_discovery.py` が存在するため、一括実行時に
pytest のパッケージ名解決が衝突する。

**対処**: UC 単位で実行する:
```bash
python3 -m pytest defense-satellite/tests/ -q
python3 -m pytest government-archives/tests/ -q
python3 -m pytest smart-city-geospatial/tests/ -q
```

## 参考: デプロイ成功までのチェックリスト

```bash
# 1. S3 AP Alias と Name が手元にある
aws s3control list-access-points --account-id <account> --region ap-northeast-1

# 2. VPC ID とプライベートサブネット ID を取得
aws ec2 describe-vpcs --region ap-northeast-1

# 3. Bedrock モデルアクセスを有効化（UC17 のみ）
# コンソールで `amazon.nova-lite-v1:0` を有効化

# 4. Lambda zip を S3 にアップロード
UC=defense-satellite bash scripts/package_uc15_lambdas.sh

# 5. CloudFormation デプロイ
aws cloudformation deploy ... \
  --parameter-overrides \
    DeployBucket=... \
    S3AccessPointAlias=...-ext-s3alias \
    S3AccessPointName=...           # <- 忘れずに！
    ...

# 6. Step Functions 実行
aws stepfunctions start-execution --state-machine-arn ... --input '{}'

# 7. 結果確認
aws s3 ls s3://<output-bucket>/ --recursive

# 8. クリーンアップ
bash scripts/cleanup_phase7.sh
```


## 9. AWS コンソール操作の注意点（2026-05-10 の UI/UX 検証で判明）

### 9.1 S3 Access Point Alias はブラウザでは直接開けない

**症状**: S3 AP alias を URL の bucket パラメータに指定すると以下エラー:
```
You can't view bucket details by using an Access Point alias
```

**原因**: Alias はバケット名と異なる識別子のため、コンソールがバケット操作に紐付けられない。

**対処**:
- **Access Points for FSx** 専用ページ (`/s3/fsxap`) を使用
- または実バケット名でアクセス（FSx 配下のバケットは通常隠匿）
- プログラムからは boto3/SDK で alias を指定して問題なく動作

### 9.2 VPC Lambda の ENI 解放による削除遅延

**症状**: CloudFormation `DELETE_IN_PROGRESS` で 15-30 分停滞。Lambda 関数だけが削除中のまま。

**原因**: Hyperplane ENI（VPC 配置 Lambda 用）は、最後のリクエストから数十分経過しないと AWS 側が解放しない。

**対処**: 待つのが正解。明示的に ENI を削除しようとしても以下エラーで失敗する:
```
AWS Lambda VPC ENI Service is using this ENI
```

並列で別 UC の作業を進められるので、放置で OK。

### 9.3 Textract を cross-region で呼び出す際のレイテンシ

**実測値 (2026-05-10 検証)**:
- UC16 OCR Lambda で PDF (1.6KB、1 ページ) を us-east-1 の Textract に投げる
- Lambda 実行時間: 1,200 ms (うち Textract 往復 ~900 ms)
- 取得結果: 43KB Blocks JSON（OCR 成功、FORMS + TABLES 構造含む）

ネットワークレイテンシは約 150-200 ms が追加で積み重なる。同期 sync API
（AnalyzeDocument）は問題なく動作するが、大量処理時は async API（StartDocumentAnalysis）推奨。

### 9.4 Bedrock Nova Lite は文脈情報を活用

**観察**: `sendai_area.jpg` というファイル名をプロンプトに含めただけで、生成レポートで
「仙台地域」として認識してくれる。ファイル名やメタデータに地域情報を含めると、
AI が地理的・文化的に適切な提案を行いやすい。

### 9.5 Rekognition は合成画像でも良好な結果

**観察**: 1024x1024 JPEG（green 背景 + grey rectangles for buildings + grey lines for roads）
で 15 件以上のラベル検出に成功。実衛星画像でなくても、ML テストには十分。

PIL で合成画像を生成して軽量にテストできる:
```python
from PIL import Image, ImageDraw
img = Image.new('RGB', (1024, 1024), (100, 150, 100))
draw = ImageDraw.Draw(img)
for x in range(100, 900, 200):
    for y in range(100, 900, 200):
        draw.rectangle([x, y, x+100, y+100], fill=(120, 120, 120))
img.save('sample.jpg', 'JPEG', quality=85)
```

## 10. OutputDestination=FSXN_S3AP モードの知見（2026-05-11 Theme E 実検証で判明）

2026-05-11 の UC15/16/17 Pattern B 実検証で発見・確認した、`OutputDestination=FSXN_S3AP`
モード固有の事象。UC11/14 (2026-05-10) の検証時には表面化しなかった項目も含む。

### 10.1 Lambda INFO ログが出ないのに put_object は成功する

**症状**: `OutputDestination=FSXN_S3AP` モードで実行した UC15 Tiling Lambda の
CloudWatch Logs を見ても `"UC15 Tiling started:"` や `"Output written:"` のような
INFO ログが 1 行も見えない。それでも Step Functions は SUCCEEDED で完了し、
`aws s3api list-objects-v2 --prefix ai-outputs/uc15/` で書き込み済みファイルは確認できる。

**原因**: Lambda Python 3.13 ランタイムのデフォルト root logger レベルが WARNING 以上
（実装依存）。`logger = logging.getLogger(__name__)` + `logger.info(...)` では出力されない。

**対処**:

- **書き込み成功の確認**: CloudWatch Logs の INFO 行に依存せず、`aws s3api list-objects-v2 --prefix <prefix>`
  でオブジェクト存在を直接確認する
- **Step Functions の execution output を信頼**: `describe-execution --query 'output'` が
  各 Lambda の return dict を全部含む。これが事実上の正式な出力監査ログ
- **デバッグ時のみ root logger を強制**: handler の先頭で
  ```python
  import logging
  logging.getLogger().setLevel(logging.INFO)
  logging.getLogger("shared").setLevel(logging.INFO)
  ```
  を追加。ただし production ではノイズになるので、この設定を commit するのは NG

**混同注意**: `ProcessingErrors: 0.0` / `ProcessingSuccess: 1.0` の EMF メトリクスは
出力される（これは `emf.flush()` が stdout に JSON を書くため）。EMF だけが見えて
INFO ログが見えない状態は正常動作のシグナル。

### 10.2 S3 AP alias 経由と S3 AP ARN 経由で `aws s3 ls` の挙動が異なる

**症状**: 2026-05-11 の検証中、以下 2 コマンドで異なる結果が返った:

```bash
# 空の結果（false negative）:
aws s3 ls "s3://arn:aws:s3:ap-northeast-1:<account>:accesspoint/<name>/ai-outputs/uc15/" --recursive

# 正しく 5 オブジェクト表示:
aws s3 ls "s3://<alias>-ext-s3alias/ai-outputs/uc15/" --recursive
aws s3api list-objects-v2 --bucket "<alias>-ext-s3alias" --prefix "ai-outputs/uc15/"
```

**原因**: `aws s3 ls` CLI は S3 AP ARN 形式の URI をそのまま `--bucket` パラメータに
渡すが、FSxN S3AP の実装では ARN 形式での list 呼び出しが不安定な場合がある（2026-05 時点）。
一方 Alias 形式と `list-objects-v2 --bucket <alias>` は常に正しい結果を返す。

**対処**:

- **検証スクリプトには `list-objects-v2 --bucket <alias>` を使う**: `aws s3 ls <URI>`
  より高信頼
- **ARN 形式は IAM policy の Resource 指定にのみ使う**: CLI での list/get には alias を使う
- **evidence capture**: `docs/verification-evidence/uc{15,16,17}-demo/s3ap-output-listing.txt`
  は alias + `--recursive --human-readable` で取得済み（再現コマンドは
  `docs/verification-evidence/README.md` 参照）

### 10.3 UC16 チェーン構造で `ocr-results/*.txt` が 0 bytes でも後段 Lambda は成功する

**観察**: 2026-05-11 の UC16 実検証で、最小サンプル PDF (298 bytes、本文ゼロ) を入力に
使ったところ、OCR Lambda は `ocr-results/foia-001.pdf.txt` を **0 バイト** で書き出した
（Textract が LINE ブロックを 0 個返したため、`_extract_text_from_blocks` の結果が空文字列）。

それでも以下の後段 Lambda はすべて成功し、期待される出力ファイルを produce した:

| Lambda | OutputWriter.get_text() 返り値 | 挙動 |
|--------|-------------------------------|------|
| Classification | `""` (空文字列) | 空文字列に対して keyword 分類を実行 → `clearance_level=public` (keyword が見つからないため) |
| EntityExtraction | `""` | Comprehend も正規表現も 0 matches → `pii_count=0` |
| Redaction | `""` + `entities=[]` | 0 redactions → `redaction_count=0` |
| IndexGeneration | (skipped: OpenSearchMode=none) | — |

**意味**: Pattern B + chain 構造の全ステージが、**OCR 結果が空でも graceful に動作する**
ことが production-verified。これは以下 2 点の設計を裏付ける:

1. `OutputWriter.get_text()` が空 body でも ClientError を出さず、`""` を返す
2. 各 Lambda が `if not text: return early` を実装せず、空文字列を通常通り処理する
   （Comprehend/regex/redact_text いずれも空入力で 0 件を正しく返す）

**テスト戦略への示唆**:

- Phase 7 のテストは Hypothesis property-based で「N 個の PII → N 個の [REDACTED]」
  を検証していたが、**N=0 のケースは production でのみ exercise された**
- 今後の Pattern B 実装では、chain の先頭ステージが空出力を返すケースを
  integration test に含めるのが健全

### 10.4 FSXN_S3AP モード時の OutputBucket resource 完全非存在の確認方法

**動機**: `OutputDestination=FSXN_S3AP` モードが本当に S3 バケットを作らないか
物理的に確認したい（Condition が想定通り false に評価されているか）。

**方法**:

```bash
aws cloudformation describe-stack-resources \
  --stack-name fsxn-uc15-demo \
  --region ap-northeast-1 \
  --query 'StackResources[?ResourceType==`AWS::S3::Bucket`].[LogicalResourceId,PhysicalResourceId]' \
  --output table
```

- **期待結果**: 空の table（0 行）
- **何か表示された場合**: Template の Condition `UseStandardS3` が想定通り false に
  ならなかった可能性。`!Equals [!Ref OutputDestination, "STANDARD_S3"]` の綴りや
  `Condition: UseStandardS3` の resource 側記述を再確認

2026-05-11 の Theme E 検証では UC15/16/17 全てで 0 行を確認、S3 バケット課金ゼロを
保証できた。

### 10.5 Bedrock Nova Lite 1 回呼び出しのコスト実績

**観察**: UC17 ReportGeneration が 1 回の Bedrock invoke_model (Nova Lite) で
~1.1 KiB の日本語 Markdown レポートを生成。billing dashboard 確認で、1 回の呼び出しが
**約 $0.003** (~500 input tokens + ~500 output tokens) だった。

EventBridge スケジュール (1 日 1 回) で UC17 を回す場合、Bedrock コストは **月 ~$0.09**。
これは FSxN S3AP に書き出す「no data movement」のコスト的魅力を補強する:

- Standard S3 だと: S3 バケットストレージ (minimal) + Bedrock + Lambda
- FSXN_S3AP だと: Bedrock + Lambda のみ、S3 ストレージ $0

長期運用 (例: 1 年分の Markdown レポートアーカイブ) でも、
`ai-outputs/uc17/reports/YYYY/MM/DD/*.md` は FSx ONTAP 側の容量に吸収され、
S3 標準料金の蓄積がない。

### 10.6 Lambda zip 再パッケージなしの CloudFormation デプロイ更新が無効

**症状**: `shared/output_writer.py` を変更したのに、`aws cloudformation deploy` で
「No changes to deploy」が出て、Lambda 関数コードが新旧どちらか判然としない。

**原因**: Lambda `Code.S3Key` が同じ値のため CloudFormation は diff を検出しない。
zip の中身が変わっても S3 key 不変なら CloudFormation は再デプロイしない。

**対処**: `scripts/package_uc15_lambdas.sh` は毎回上書き upload するので、package 実行後は
Lambda get-function の `CodeSha256` と `head-object` で取得した zip の SHA256 を比較して
一致を確認してから `start-execution` を呼ぶ。一致確認コマンド:

```bash
# Lambda 関数の現在の SHA:
aws lambda get-function --function-name fsxn-uc15-demo-tiling \
  --query 'Configuration.CodeSha256' --output text

# S3 上の zip の SHA (Lambda 形式):
aws s3 cp s3://<deploy-bucket>/lambda/defense-satellite-tiling.zip /tmp/check.zip --quiet && \
  python3 -c "import hashlib, base64; \
    print(base64.b64encode(hashlib.sha256(open('/tmp/check.zip','rb').read()).digest()).decode())"
```

2 つが一致していれば OK。不一致の場合は Lambda `update-function-code` を明示的に実行:

```bash
aws lambda update-function-code \
  --function-name fsxn-uc15-demo-tiling \
  --s3-bucket <deploy-bucket> \
  --s3-key lambda/defense-satellite-tiling.zip \
  --region ap-northeast-1
```

**CloudFormation deploy との使い分け**:
- **handler/shared コード変更のみ**: 再パッケージ + `update-function-code` で OK
- **IAM policy / env var / parameter 変更**: `cloudformation deploy` 必須
- **両方の変更**: 両方とも実行（cloudformation → update-function-code の順が安全）


---

## 11. Related operational runbooks

For detailed step-by-step resolution of CloudFormation `DELETE_FAILED` states
encountered during UC stack cleanup, see:

- **[Cleanup Troubleshooting Runbook](operational-runbooks/cleanup-troubleshooting.md)** — covers 6 failure modes:
  1. Athena WorkGroup non-empty
  2. S3 versioned bucket not empty
  3. Security Group dependent object (VPC Endpoint SG reference)
  4. VPC Lambda ENI release delay
  5. DynamoDB Retain tables
  6. ACCOUNT_ID placeholder in cleanup script

The cleanup script (`scripts/cleanup_generic_ucs.sh`) has been enhanced
to handle modes 1-4 automatically. Mode 5 (DynamoDB Retain) still
requires manual `delete-table` after stack deletion.

---

## 12. Cross-UC validation sweeps (2026-05-11 追加対応)

Phase 7 Theme R の延長として、17 UC 全体の横断検査を実施。以下の 3 件を発見・修正した。

### 12.1 S3 Access Point ARN form の IAM ポリシー不整合（9 UC）

**症状**: FSxN S3AP permission 判定は alias 形式（`arn:aws:s3:::<alias>/*`）と
Access Point ARN 形式（`arn:aws:s3:<region>:<account>:accesspoint/<name>/*`）の
両方を評価する。IAM policy が alias だけを許可していると、内部的に
ARN 形式で参照された瞬間に `AccessDenied` が発生する。

**影響範囲**: UC1/2/3/5/6/7/8/10/14 の 9 UC（既に修正済みだった UC4/9/11/12/13/15/16/17
を除く）。いずれも `S3AccessPointAlias` は受け取っていたが、`S3AccessPointName`
パラメータと `HasS3AccessPointName` Condition を持っていなかった。

**修正内容**:

1. 9 UC の `template-deploy.yaml` に `S3AccessPointName` パラメータを追加
   （default `""`、指定したときだけ AP ARN を許可）。
2. `HasS3AccessPointName` Condition を追加。
3. Discovery / OCR / 出力系の Lambda IAM ポリシーで `Resource` を
   `!If [HasS3AccessPointName, [alias + AP ARN], [alias のみ]]` に書き換え。

**修正後の検証**: `scripts/lint_all_templates.sh` で 9/9 UC が cfn-lint 0 errors。
UC9 / UC4 デプロイ経験から、このパターンは AWS 側でデプロイすると
`CREATE_COMPLETE` になるが、Lambda 実行時に `AccessDenied` になる。
テンプレート lint では検出できない AWS 固有の挙動なので、17 UC 横並びで
先回り修正した。

**予防策**: 新 UC を追加するときは `autonomous-driving/template-deploy.yaml`
を参考に `S3AccessPointName` パラメータを必ず定義する。

### 12.2 Lambda handler の `os` 未 import（UC2 financial-idp）

**症状**: `entity_extraction/handler.py` で `os.environ.get(...)` を呼んでいるが
`import os` が欠落していた（pyflakes で検出）。Lambda 実行時に
`NameError: name 'os' is not defined` → Step Functions FAILED。

**検出方法**: `scripts/_check_handler_names.py` で 87 個の handler を
pyflakes に一括投入。1 件のみ undefined name エラー。

**修正**: 1 行追加のみ（`import os`）。Commit で修正済み。

**予防策**: handler.py 追加時に CI / local で `python3 -m pyflakes` を走らせる
ことを推奨。`scripts/_check_handler_names.py` を pre-commit hook に組み込む
案も検討余地あり（ただし現状は 60-90 秒かかる cfn-lint と分離して実行可能）。

### 12.3 Step Functions Choice state operator typo（UC9 で過去に発見済み）

Phase 7 Theme Q で UC9 の `NumericGreaterThanOrEqualToPath`
（実在しない operator）を `NumericGreaterThanEqualsPath`（正しい名前）に
修正済み。今回の横断検査で他 UC には同種の typo がないことを確認
（grep 結果は `NumericGreaterThanEqualsPath` と `NumericLessThanPath` のみ）。

---

## 13. 横断検査スクリプト

Phase 7 の実検証を通じて以下の検査スクリプトを整備した。**新規 UC 追加時 / 大規模 refactor 後は全て実行すること。**

| スクリプト | 検出対象 | 所要時間 |
|---|---|---|
| `scripts/lint_all_templates.sh` | CloudFormation template の schema エラー（17 UC 並列） | 5-7 分 |
| `scripts/check_handler_names.py` | Lambda handler の NameError / undefined name | 30 秒 |
| `scripts/check_conditional_refs.py` | UC9-class bug: Condition 付きリソースを Sub で参照 | 5 秒 |
| `scripts/_check_sensitive_leaks.py` | スクリーンショット OCR leak 検査 | 10 秒 |

いずれも macOS / Linux で動作。必要な Python パッケージは `pip install cfn-lint pyflakes pyyaml`。

