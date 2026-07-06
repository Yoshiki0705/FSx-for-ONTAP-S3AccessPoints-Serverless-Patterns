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

## 5. 実 AWS で検証できる範囲（コスト別）

デモ/動作確認を段階的に行うためのガイド。順に A → B → C。

### A. ローカル / ゼロコスト（AWS 不要）

```bash
make test-media-ivs-vod-publishing         # 45 テスト（publish/moderation/transcode ロジック）
cfn-lint solutions/edge/media-ivs-vod-publishing/template.yaml   # 0 エラー
```

### B. 低コストで実 AWS 検証（FSx 不要が中心）

- **B3: IVS が S3 AP alias を録画先として受理するか（config 作成の検証のみ）**

  ```bash
  # 標準 S3 AP でも FSx for ONTAP S3 AP でも同じスクリプトで検証できる。
  # config 作成のみを検証し、作成した RecordingConfiguration は自動削除する（KEEP_RC=1 で保持）。
  FSX_S3AP_ALIAS="<your-s3-access-point-alias>" \
  FSX_S3AP_ARN="arn:aws:s3:<region>:<account-id>:accesspoint/<name>" \
    ./scripts/test-direct-fsx-s3ap-alias.sh
  ```

  観測（この検証環境）: **alias**（≤63 文字）→ `state: ACTIVE`。**ARN**（>63 文字）→ `ValidationException`
  （`bucketName` は最大 63 文字）。**標準 S3 AP と FSx for ONTAP S3 AP の両方**で alias が config 作成を
  通過し ACTIVE に到達することを確認済み。ただし **config 作成 ≠ 録画成功**（ライブ配信・volume 書き込み・
  二層認可は未検証）。詳細と公開ラベル方針は [../direct-recording-experiment.md](../direct-recording-experiment.md)。

- **B1: 推奨パスのコア（DemoMode）** — `sam deploy DemoMode=true` でスタックを作成し、IVS チャンネル +
  Recording Config を用意して短時間 RTMPS 配信 → Recording End イベント → Step Functions → publish Lambda。
  実配信はエンコーダー（OBS/FFmpeg）操作が必要。
- **B4: S3 Access Point → CloudFront（OAC）配信レグ** — 標準 S3 バケット + S3 AP + CloudFront で
  `.m3u8`/segments の SigV4 取得・TTL 挙動を確認（FSx 不要）。

### C. FSx for ONTAP を使う検証（既存リソースを活用）

新規に FSx for ONTAP を作らず、**既存のファイルシステム/ボリューム/S3 アクセスポイント接続を再利用**する。

- 既存の FSx for ONTAP S3 アクセスポイント接続を確認:

  ```bash
  aws fsx describe-s3-access-point-attachments --region ap-northeast-1 \
    --query "S3AccessPointAttachments[].{Name:Name,Vol:OntapConfiguration.VolumeId,Alias:S3AccessPoint.Alias}"
  ```

- 既存 S3 AP alias を CloudFront オリジンにして HLS を配信（[Stream video using CloudFront with FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html) を参照）。
- NFS/SMB と S3 API の二面アクセス、FlexCache、FabricPool 階層化、SnapMirror は既存構成の範囲で確認する。

> 注意: 共有の既存 FSx for ONTAP を使う場合は、**専用のプレフィックス/ボリューム**に限定し、既存データに
> 触れないこと。検証で作成した IVS RecordingConfiguration 等の一時リソースは完了後に削除する。
