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

1. **専用の出力ディレクトリに書き込む**（例: `/vol1/ai-outputs/`）。NFS クライアントからは読み取りのみとします。実効性があるのはこの緩和策です。競合を管理するのではなく、競合が起こり得ない構成にします
2. **ロックによる調停は期待できません**。S3 には open やロックの概念がなく、ONTAP のプロトコル間ロックは NFS と SMB の間の仕組みです。S3 AP の書き込みが、同一ファイルへの NFS 書き込みと直列化されることはありません
3. **パスで分離できない場合は時間で分離する**: NFS の書き込みが少ない時間帯に AI 処理をスケジュールします。ただしこれは窓を狭めるだけで、閉じるわけではありません
4. **事後に検知する**: 観測できるロックが存在しないため、ロック競合のカウンターではこの種の競合は見えません。見えるのはパスに対するアクセスイベントです。ONTAP の監査ログ、または EventBridge 経由の FPolicy（`solutions/event-driven/fpolicy/` 参照）であれば、同一ファイルへの S3 書き込みと NFS 書き込みが近接した 2 つのイベントとして現れます

## ONTAP の挙動

- S3 AP PutObject はアトミックです。オブジェクト全体を置き換えるため、読み取り側が書きかけの状態を見ることはありません
- ただしアトミックであることは排他であることとは違います。2 つの書き込みは順序付けられるだけで、阻止されません
- NFS のアドバイザリロックは S3 AP の操作からは参照されません
- ONTAP WAFL はブロックレベルでファイルシステムの整合性を保証します
- データ破損のリスクはありませんが、last-writer-wins のセマンティクスが適用されるため、2 つの書き込みのうち一方は無言で失われます

> 持ち帰るべきは最後の点です。「破損しない」はファイルシステムについての言明であって、
> データについての言明ではありません。ファイルは内部的に正しい状態で、
> 2 つのバージョンのうちちょうど一方を含みます。

## 参考資料

- [FSx for ONTAP: Multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/multiprotocol-access.html)
