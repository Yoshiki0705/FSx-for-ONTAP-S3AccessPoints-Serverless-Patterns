# 機能改善要望 — Amazon IVS Auto-Record の出力先に S3 Access Point（FSx for ONTAP 含む）を

> AWS サポート / IVS サービスチーム向けの、建設的な機能改善要望テンプレートです。非難ではなく、
> 機能追加のお願いと確認事項として記載しています。プレースホルダを埋め、末尾の証跡を添付してください。
> アカウント ID、内部 IP、サポートケース番号、個人名は記載しないでください。

## 要望サマリ（Request summary）

Amazon IVS の Auto-Record（Recording Configuration）の出力先として、標準 S3 バケット名だけでなく、
**S3 Access Point の alias または ARN**、特に **Amazon FSx for NetApp ONTAP** に紐づく
S3 Access Point を、`RecordingConfiguration.destinationConfiguration.s3.bucketName` に
明示的に指定できるようサポートを検討いただきたい。

## ビジネス / 技術的な動機（Business / technical motivation）

- ライブ配信後の VOD、編集、QC、承認、アーカイブのワークフローでは、ファイルプロトコル（NFS/SMB）と
  S3 API の **両方** が同一メディア上で必要になる。
- FSx for ONTAP は同一データを NFS/SMB と S3 Access Point の両方から扱えるため、メディアワークフローに
  適している（編集者と S3 API サービスの双方が使える単一の正となるコピー）。
- IVS の録画データを直接 FSx for ONTAP volume へ配置できれば、標準 S3 バケットから FSx への
  後続コピーを削減できる。
- ライブコマース、イベント配信、教育、スポーツ/フィットネス、社内配信アーカイブなどでニーズがある。

## 確認したい事項（Requested clarification）

以下について確認したい。

1. `destinationConfiguration.s3.bucketName` に **S3 Access Point alias** を指定することは
   IVS Auto-Record のサポート対象か。
2. その alias が **FSx for ONTAP S3 Access Point** を指す場合、動作はサポート対象か。
3. 現時点でサポート対象外の場合、今後の **ロードマップ / Feature Request** として受付可能か。
4. **S3 Access Point ARN** を出力先として対応する予定はあるか。
5. **IVS Service-Linked Role** と **S3 Access Point policy** / **FSx ファイルシステム identity**
   （UNIX/Windows）の推奨ポリシーパターンを提供いただけるか。
6. 直接録画が難しい場合、ライブ後メディアワークスペース / VOD 配信向けに、
   **IVS → S3 → FSx for ONTAP** の推奨リファレンスアーキテクチャを公式に整理いただけるか。

## 添付する証跡（Evidence to attach）

- IVS Recording Configuration の API/CLI は現状 `bucketName` を受け付ける
  （[API リファレンス](https://docs.aws.amazon.com/ivs/latest/LowLatencyAPIReference/API_CreateRecordingConfiguration.html)）。
- IVS ドキュメントは、アカウント所有の S3 バケットへの録画を説明している
  （[Auto-Record to S3](https://docs.aws.amazon.com/ivs/latest/LowLatencyUserGuide/record-to-s3.html)）。
- FSx for ONTAP S3 Access Points は `PutObject` / `GetObject` / `ListObjectsV2` 等の
  S3 object operation をサポートする
  （[FSx for ONTAP S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)）。
- FSx for ONTAP のドキュメントには、S3 Access Point + CloudFront による HLS 動画配信が既にある。
- 提案するアーキテクチャは、ライブ後メディアワークスペースと VOD 配信に有用である。
- **検証環境での観測（標準 S3 AP、FSx for ONTAP ではない）:** `create-recording-configuration` に
  Access Point の **alias** を `bucketName` として指定すると `ACTIVE` に到達した。一方、Access Point の
  **ARN** は `ValidationException: bucketName is required to have a maximum length of 63` で拒否された。
  これは IVS が config 作成時に `bucketName` を「63 文字以下・バケット名形状の文字列」としてのみ検証する
  ことを示す。録画時（ストリーム中）の AP 経由書き込みや FSx for ONTAP S3 AP の挙動は確認していない
  （config 作成 ≠ 録画成功）。ARN の明示サポートには 63 文字制約の緩和が必要。詳細は
  `direct-recording-experiment.md` を参照。
- （推奨する次の検証）ライブ配信 + FSx for ONTAP S3 AP でのエンドツーエンド結果 — Recording Start/End
  イベント、`ivs/v1/...` オブジェクトが AP 経由で書き込まれるか、IVS Service-Linked Role が呼び出す
  S3 API の CloudTrail エントリ。
