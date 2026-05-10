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
