# AWS Support Case 177840169000484 — 返信案

## 宛先: Ryo M. 様

---

お世話になっております。
ご検証いただきありがとうございます。

## 1. OutputLocation での FSx for ONTAP S3 Access Point alias 指定について

当方環境で検証いたしましたところ、以下のエラーが発生しました。

**実行コマンド:**
```
aws athena start-query-execution \
  --query-string "SELECT 1 AS test" \
  --result-configuration "OutputLocation=s3://<FSxN-S3AP-alias>/athena-results/" \ <!-- allow:naming -->
  --work-group primary \
  --region ap-northeast-1
```

**エラー:**
```
InvalidRequestException: The specified bucket is not valid.
(Service: Amazon S3; Status Code: 400; Error Code: InvalidBucketName;
 Request ID: T6MRW5R4TEENHS6J)
AthenaErrorCode: INVALID_INPUT
```

### 確認いただきたい点

AWS サポート様の検証環境で使用された S3 Access Point は、以下のどちらでしょうか？

| 種類 | alias 形式 | データプレーン | 作成方法 |
|------|-----------|--------------|---------|
| **通常の S3 Access Point** | `xxx-s3alias` | S3 データプレーン | `s3control create-access-point` |
| **FSx for ONTAP S3 Access Point** | `xxx-ext-s3alias` | FSx for ONTAP データプレーン | FSx コンソール / FSx API |

当方の要望は、**FSx for ONTAP ボリュームにアタッチされた S3 Access Point**（alias が `-ext-s3alias` で終わるもの）を Athena の OutputLocation として使用することです。

AWS ドキュメント [1] に記載の通り、FSx for ONTAP S3 Access Point は通常の S3 Access Point とは異なるデータプレーンを使用しており、alias 形式も `-ext-s3alias` と区別されています。

> `{{ACCESS POINT NAME}}-METADATA-ext-s3alias` (for access points attached to an non-S3 bucket data source)

また、FSx for ONTAP S3 Access Point は PutObject をサポートしている [2] ため、技術的には Athena の結果ファイル（CSV, metadata）を書き込むことが可能なはずです。

### 想定される原因

Athena が OutputLocation を処理する際に、S3 AP alias をバケット名として S3 データプレーンに解決しようとしているが、FSx for ONTAP S3 AP（`-ext-s3alias`）は S3 データプレーンではなく FSx データプレーンを経由するため、`InvalidBucketName` エラーが返されていると推測しています。

通常の S3 AP（`-s3alias`）であれば S3 データプレーン内で解決されるため動作するが、FSx for ONTAP S3 AP（`-ext-s3alias`）は Athena 側で未対応の可能性があります。

## 2. SSE-FSX について

ご説明いただいた通り、FSx for ONTAP は KMS による透過的な暗号化がデフォルトで有効であることを理解しております [2]。Athena 側で暗号化タイプを明示的に指定する必要がないことも理解しました。この点については要望を取り下げます。

## 3. 5GB サイズ制限について

機能改善要望としてフィードバックいただきありがとうございます。
当面は LIMIT 句や CTAS + bucketing 等の回避策で対応いたします。

## まとめ

最も重要な要望は「FSx for ONTAP S3 Access Point（`-ext-s3alias`）を Athena の OutputLocation として使用し、クエリ結果を FSx for ONTAP ボリュームに直接書き戻す」ことです。

当方環境では `InvalidBucketName` エラーが発生しており、現時点では動作しない状況です。AWS サポート様の検証が通常の S3 AP（`-s3alias`）で実施されたものであれば、FSx for ONTAP S3 AP（`-ext-s3alias`）での再検証をお願いできますでしょうか。

以上、よろしくお願いいたします。

---

## 参考ドキュメント

[1] Amazon S3 Access Point Aliases — `-ext-s3alias` 形式の説明
https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-naming.html

[2] FSx for ONTAP S3 Access Points — サポートされる API 操作（PutObject 含む）と制約
https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html

[3] Athena — クエリ結果の出力先指定
https://docs.aws.amazon.com/athena/latest/ug/query-results-specify-location-workgroup.html
