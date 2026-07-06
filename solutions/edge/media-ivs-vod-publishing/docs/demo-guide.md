# デモガイド — Media IVS VOD Publishing（DemoMode）

FSx for ONTAP / Amazon IVS なしで、VOD publish ワークフローのロジックを検証する手順です。

## 1. ユニット/プロパティテスト（最速）

```bash
make test-media-ivs-vod-publishing
# または
python3 -m pytest solutions/edge/media-ivs-vod-publishing/tests/ -v
```

検証内容:
- `Recording End` イベントで publish が起動し、`master.m3u8` 検証が働くこと
- `Recording Start` / `Recording End Failure` 等、Recording End 以外はスキップされること
- DemoMode では FSx への実コピーをスキップし、記録のみ行うこと
- master manifest 欠落時に Human Review が `HUMAN_REVIEW` / `REJECT` を返すこと
- 取り込みが録画プレフィックス配下に限定されること（permission-aware）
- publish マニフェストに `data_classification`（PUBLIC）が付与されること

## 2. ローカルでの publish 動作確認（mock）

`tests/conftest.py` の `FakeS3Ap` を使うと、S3/FSx に接続せずに publish の入出力を確認できます。
publish マニフェスト JSON には `master_manifest_present` / `human_review` / `published` /
`skipped` / `data_classification` が含まれます。

サンプルイベントは [../samples/eventbridge-recording-ended.json](../samples/eventbridge-recording-ended.json) を参照。

## 3. DemoMode デプロイ（任意）

実 AWS で確認する場合（FSx は不要、S3 AP alias の形式パラメータのみ必要）:

```bash
sam build --template solutions/edge/media-ivs-vod-publishing/template.yaml
sam deploy --guided \
  --template solutions/edge/media-ivs-vod-publishing/template.yaml \
  --stack-name fsxn-media-ivs-vod-publishing-demo \
  --parameter-overrides DemoMode=true TriggerMode=EVENT_DRIVEN
```

DemoMode=true では FSx への実コピーを行わず、マニフェストの `skipped` に記録します。

## 4. 本番移行時の追加確認

| 項目 | DemoMode | 本番移行前 |
|---|---|---|
| publish ロジック / Recording End 分岐 | ✅（テスト） | — |
| master manifest 検証 / Human Review 判定 | ✅（テスト） | 実 HLS パッケージで確認 |
| S3 → FSx 取り込み（S3 AP PutObject） | ⚠️ スキップ | 実 S3 AP + ONTAP ID で確認 |
| 大容量/多数セグメント | — | DataSync / ECS・Batch（NFS/SMB）を検討 |
| CloudFront 配信（OAC + SigV4） | — | 実機で `.m3u8`/segments の SigV4 取得を確認 |
| 直接録画（IVS→FSx for ONTAP S3 AP） | — | Experimental（[../direct-recording-experiment.md](../direct-recording-experiment.md)） |
