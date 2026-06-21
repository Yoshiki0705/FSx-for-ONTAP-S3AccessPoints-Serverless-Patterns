# デモガイド — Content Edge Delivery（DemoMode）

FSx for ONTAP / 外部 CDN なしで、配信ワークフローのロジックを検証する手順です。

## 1. ユニットテスト（最速）

```bash
python3 -m pytest content-edge-delivery/tests/ -v
```

検証内容:
- `ORIGIN_PULL` がオブジェクトを複製しないこと
- `PUBLISH_PUSH` の DemoMode が外部 push をスキップすること
- `ApprovedPrefix` 外（例 `master/`）が配信対象に含まれないこと（permission-aware）
- 配信ログの IP マスク（デフォルト有効 / 無効化可能）

## 2. ローカルでの publish 動作確認（mock）

`tests/conftest.py` の `FakeS3Ap` を使うと、S3/FSx に接続せずに publish の入出力を確認できます。
配信マニフェスト JSON には `delivery_mode` / `cdn_target` / `data_classification` / `published` / `skipped`
が含まれます。

## 3. DemoMode デプロイ（任意）

実 AWS で確認する場合（FSx は不要、S3 AP alias の形式パラメータのみ必要）:

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery-demo \
  --parameter-overrides DemoMode=true DeliveryMode=PUBLISH_PUSH
```

DemoMode=true では外部ストアへの実 push を行わず、マニフェストの `skipped` に記録します。

## 4. 本番移行時の追加確認

| 項目 | DemoMode | 本番移行前 |
|---|---|---|
| publish ロジック | ✅ | — |
| ApprovedPrefix の権限境界 | ✅（テスト） | 実 S3 AP + ONTAP ID で確認 |
| ORIGIN_PULL の SigV4 直引き | ⚠️ 未検証 | サードパーティ CDN は実機検証 |
| PUBLISH_PUSH の外部ストア | ⚠️ スキップ | 実エンドポイント/認証で確認 |
| 視聴者トークン | — | CDN ネイティブ機構で実装 |
