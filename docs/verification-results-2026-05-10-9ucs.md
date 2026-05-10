# AWS 動作検証レポート: UC1–UC13（UC6/11/14 除く）一括再デプロイ

**検証日**: 2026-05-10
**リージョン**: ap-northeast-1 (東京)
**AWS アカウント**: <ACCOUNT_ID>
**対象 UC**: UC1 / UC2 / UC3 / UC5 / UC7 / UC8 / UC10 / UC12 / UC13 （9 UC）
**スキップ対象**: UC4 (Deadline Cloud 依存) / UC9 (依存 Lambda 未解決参照) / UC6 (前回検証済み) / UC11/UC14 (並行スレッドで OutputDestination 対応中)

## 結果サマリー

| UC | ディレクトリ | デプロイ | Step Functions | 備考 |
|----|-------------|---------|----------------|------|
| UC1 | legal-compliance | ✅ | ✅ SUCCEEDED 49s | SG inbound 追加で ONTAP Secrets Manager 到達可 |
| UC2 | financial-idp | ✅ | ✅ SUCCEEDED 18s | OCR / EntityExtraction / Summary すべて成功 |
| UC3 | manufacturing-analytics | ✅ | ✅ SUCCEEDED 17s | Parallel / Map / AthenaAnalysis すべて成功 |
| UC5 | healthcare-dicom | ✅ | ✅ SUCCEEDED 18s | **discovery handler NameError 修正** + DICOM プリアンブル対応 |
| UC7 | genomics-pipeline | ✅ | ✅ SUCCEEDED 3m03s | Parallel (QC / VariantAggregation) + Athena 成功 |
| UC8 | energy-seismic | ✅ | ✅ SUCCEEDED 3m03s | SeismicMetadata / AnomalyDetection / ComplianceReport 成功 |
| UC10 | construction-bim | ✅ | ✅ SUCCEEDED 2m57s | BimParse / OCR / SafetyCheck 成功 |
| UC12 | logistics-ocr | ✅ | ✅ SUCCEEDED 2m54s | OCR / DataStructuring / GenerateReport 成功 |
| UC13 | education-research | ✅ | ✅ SUCCEEDED 3m03s | OCR / Classification / CitationAnalysis / Metadata 成功 |

**結果**: 9/9 全 UC で Step Functions SUCCEEDED 確認。

## 発見された問題と恒久対応

### 1. UC5 healthcare-dicom discovery Lambda の NameError

**症状**: Step Functions が `States.ReferencePathConflict` で失敗し、discovery が `NameError: name 'objects' is not defined` を返す。

**原因**: `healthcare-dicom/functions/discovery/handler.py` の EMF メトリクス出力で、変数が `dicom_objects` のみ定義されているのに `float(len(objects))` を呼び出していた。

**対応（コミット済み）**: `float(len(dicom_objects))` に修正。

```diff
-    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
+    metrics.put_metric("FilesProcessed", float(len(dicom_objects)), "Count")
```

### 2. Lambda VPC SG が Secrets Manager / その他 VPC Endpoint に到達できない

**症状**: UC1 (legal-compliance) の discovery Lambda が Secrets Manager からの credential 取得でタイムアウト（3 回リトライ × 300 秒）。

**原因**: UC6 作成時の VPC Endpoint SG (`<SG_ID>`) の inbound 443 が、UC6 の Lambda SG (`<SG_ID>`) のみを許可していた。新規に作成される各 UC の Lambda SG はブロックされる。

**対応（本検証で適用）**: 新規 UC の Lambda SG (`<SG_ID>`, `<SG_ID>`) を VPC Endpoint SG の inbound 許可に追加。

```bash
aws ec2 authorize-security-group-ingress \
  --region ap-northeast-1 \
  --group-id <SG_ID> \
  --protocol tcp --port 443 \
  --source-group <SG_ID>
```

**今後の恒久対応（テンプレート側）**: 各 UC のテンプレート `LambdaSecurityGroup` に「VPC Endpoint SG への outbound 443」を明示的に追加し、かつ既存 VPC Endpoint SG への inbound 許可を自動追加する仕組みが必要。現状は手動で `authorize-security-group-ingress` を実行する運用。

### 3. UC5 サンプルファイルフォーマット

**症状**: `.json` を DICOM として upload しても UC5 discovery の `SUFFIX_FILTER=.dcm` で弾かれる。

**対応（本検証で適用）**: 128 バイトのプリアンブル + "DICM" マジックナンバー + ダミー body の最小有効 `.dcm` ファイルを生成し、`s3://eda-demo-s3ap/dicom/2026/05/patient001.dcm` にアップロード。

```python
preamble = b"\x00" * 128
magic = b"DICM"
body = b"\x00" * 100
open('/tmp/uc5_sample.dcm', 'wb').write(preamble + magic + body)
```

`build/gen_samples.py` に UC5 用 `.dcm` 生成処理を追加することを推奨（将来タスク）。

## 撮影した UI/UX スクリーンショット

9 UC すべての Step Functions Graph view (SUCCEEDED 状態) を撮影済み。

```
docs/screenshots/originals/uc{1,2,3,5,7,8,10,12,13}-demo/uc{N}-stepfunctions-graph.png
docs/screenshots/masked/uc{1,2,3,5,7,8,10,12,13}-demo/uc{N}-stepfunctions-graph.png
```

各 UC の `docs/demo-guide.md` に「2026-05-10 再デプロイ検証で撮影（UI/UX 中心）」セクションを追加し、マスク済み画像への参照を埋め込み済み。

## 撮影対象の考え方（今後の拡張のため）

**エンドユーザーが日常的に確認する画面を重点化**:

- ✅ Step Functions Graph view (SUCCEEDED): 処理フロー全体の成功を視覚化
- ⚪ S3 出力バケット: UC11/14 で実施済み、他 UC は output bucket 命名が各 UC 異なるため個別撮影が必要
- ⚪ Athena クエリ結果 (UC6/UC7/UC8): SUCCEEDED 確認済み、実際の SELECT 画面は未撮影
- ⚪ Bedrock 生成レポート (UC1/UC8): CloudWatch Logs で確認済み、HTML プレビューは未生成

技術者向けビュー（CloudFormation スタックイベント、CloudWatch Logs 等）は本レポートに集約し、UC 個別ガイドからは除外。

## クリーンアップ状況

**スタックは保持**: 本検証直後、並行スレッド (UC11/UC14 OutputDestination 対応) との衝突回避のため、今回デプロイした 9 UC スタックは即削除せず保持。

**削除タイミング**:
- スクリーンショット撮影完了後 (本レポート時点で完了)
- 並行スレッド作業完了通知後に一括 `scripts/cleanup_generic_ucs.sh UC1 UC2 UC3 UC5 UC7 UC8 UC10 UC12 UC13`

## 並行スレッドへの引き継ぎ事項

- UC11/UC14 以外の UC (UC1/2/3/5/7/8/10/12/13) は本セッションで STANDARD_S3 モードで検証完了
- UC11/UC14 が FSXN_S3AP モードで検証完了後、全 UC を一括削除予定
- 新規追加された VPC Endpoint SG inbound rules は次回デプロイまで維持（次回も再利用可能）
