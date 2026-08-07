# NFS / S3 AP 書き込み競合の考慮事項

> 🌐 言語: **日本語** | [English](../en/nfs-s3ap-write-conflict.md)

## 概要

FSx for ONTAP S3 Access Points は、NFS/SMB からアクセスできるデータと同一のデータを公開します。両方のプロトコルが同じファイルに同時に書き込む場合、ONTAP は WAFL（Write Anywhere File Layout）によって整合性を維持しますが、アプリケーションレベルの競合は依然として発生し得ます。

## 競合が発生するケース

| シナリオ | リスク | 緩和策 |
|----------|:---:|-----------|
| 同一ファイルへの NFS 書き込みと S3 AP PutObject | 高 | 出力パスを分離する |
| 同一ファイルへの NFS 読み取りと S3 AP GetObject | なし | 完全に安全（読み取り同士） |
| S3 AP 経由の AI 出力書き戻しと、同一ファイルを編集中の NFS クライアント | 中 | `OutputDestination=STANDARD_S3` を使用する |
| 異なるファイルへの S3 AP PutObject と NFS 追記 | なし | 競合しない |

## 推奨パターン

```
NFS/SMB clients → FSx for ONTAP Volume (source data, read-write)
                         ↓ (read via S3 AP)
AI Lambda → S3 AP GetObject (read source)
         → Standard S3 Bucket (write results)  ← OutputDestination=STANDARD_S3
```

これにより書き込み競合を完全に回避できます。AI の処理結果は ONTAP ボリュームに書き戻さず、別の S3 バケットに出力します。

## 書き戻しが必要な場合（OutputDestination=FSXN_S3AP）

AI の処理結果を同一ボリューム上の NFS/SMB ユーザーに見せる必要がある場合は、以下を実施します。

1. **専用の出力ディレクトリに書き込む**（例: `/vol1/ai-outputs/`）。NFS クライアントからは読み取りのみとします
2. **ONTAP のファイルロックを利用する**: S3 AP PutObject は書き込み中に排他ロックを取得します
3. **同時編集を避ける**: NFS の書き込みアクティビティが少ない時間帯に AI 処理をスケジュールします
4. **監視する**: ONTAP の `statistics` でボリュームごとのロック競合を確認できます

## ONTAP の挙動

- S3 AP PutObject はアトミックです（部分更新ではなくオブジェクト全体の置き換え）
- NFS のアドバイザリロックは S3 AP の操作からは参照されません
- ONTAP WAFL はブロックレベルでファイルシステムの整合性を保証します
- データ破損のリスクはありませんが、last-writer-wins のセマンティクスが適用されます

## 参考資料

- [FSx for ONTAP: Multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/multiprotocol-access.html)
