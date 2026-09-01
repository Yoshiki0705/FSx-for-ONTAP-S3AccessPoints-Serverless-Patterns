# Errata — FPolicy does not see the S3 Access Point path

🌐 **Language / 言語**: 日本語 | [English](errata-fpolicy-s3ap-coverage.en.md)

<!-- drift-exempt-file: this errata sheet has to carry the corrected-from text verbatim to be usable as one -->

このシリーズの複数の記事は、FSx for ONTAP S3 Access Points がネイティブのイベント通知を
提供しないことへの回避策として FPolicy を提示していました。実機測定の結果、その提示は
**書き込みが S3 Access Point 経由で届く場合には成り立たない**ことが分かりました。
本ページは、公開済み記事に追記する訂正文と、対象記事の一覧を置いています。

## 誤りの内容

| 記事が述べていたこと | 実測 |
|---|---|
| S3 AP はイベント通知を持たないので、代わりに FPolicy を使う | S3 AP 経由の操作は FPolicy 通知を**発火しない**ため、代わりにならない |
| `mandatory` 指定の同期ポリシーなら遮断できる | AP 経由の操作は**遮断されない** |
| FPolicy は S3 AP 経由の操作も監査に載る | 載らない。ONTAP ネイティブ監査ログ（`vserver audit`）なら載る |

FPolicy が検知するのは NFS / SMB 経由のファイル操作です。書き込みが NFS / SMB で届く
ボリュームでは、記事の構成はそのまま成立します。

## 測定内容

| 測定項目 | 結果 |
|---|---|
| 無操作 90 秒（対照） | 通知 0 件 |
| S3 AP データプレーン 9 回（PUT 3 / GET 3 / HEAD 1 / LIST 1 / DELETE 1） | 通知 **0 件** |
| 同一ボリュームへの NFSv3 create + read + delete（対照） | 通知 3 件 |
| `mandatory` 指定の同期ポリシー + 応答するエンジン | AP 経由の操作は**遮断されない** |
| UNIX identity + NFS / WINDOWS identity + SMB | どちらも同じ結果 |

構造的な根拠: FPolicy event が受け付ける `protocol` は `cifs` / `nfsv3` / `nfsv4` の 3 値のみで、
`s3` / `object` / `http` はいずれも HTTP 400 で拒否されます。S3 AP 経由の書き込みがボリュームに
到達していることは、同じボリュームを NFS でマウントして確認しています。

測定条件: 2026-08-26、ap-northeast-1、ONTAP 9.18.1P3D1、SINGLE_AZ_1 / 128 MBps。

詳細な検証記録: [FPolicy と S3 Access Point のカバレッジ実測](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/s3ap-monitoring-coverage-implications.md)

## 追記テキスト（各記事末尾にコピー＆ペースト）

```markdown
---

## 📢 訂正 (2026-08-26)

本記事は、FSx for ONTAP S3 Access Points がネイティブのイベント通知を提供しないことへの
回避策として FPolicy を提示しています。実機測定により、これは **書き込みが NFS / SMB 経由で
届く場合にのみ成り立つ**ことが分かりました。

S3 Access Point 経由の操作は FPolicy 通知を発火せず、`mandatory` 指定の同期ポリシーでも
遮断されません（2026-08-26、ap-northeast-1、ONTAP 9.18.1P3D1。S3 AP データプレーン 9 回で
通知 0 件、同一ボリュームの NFSv3 対照は 3 件。FPolicy の event が受け付けるプロトコルは
`cifs` / `nfsv3` / `nfsv4` のみで、`s3` は HTTP 400 で拒否されます）。

AP 経由で書き込まれるデータを起点にする場合は、EventBridge Scheduler のポーリングか、
ONTAP ネイティブ監査ログ（AP 経由の操作を `Source=HTTP` / `Source=S3` で記録。ただし要求者は
記録されないため、要求元は CloudTrail データイベントと時刻で突き合わせます）を使います。

👉 [検証記録](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/s3ap-monitoring-coverage-implications.md)
```

## 対象記事

| Phase / Part | 記事 | 追記が必要な箇所 |
|---|---|---|
| Phase 10 | [dev.to](https://dev.to/aws-builders/fpolicy-event-driven-pipeline-multi-account-stacksets-and-cost-optimization-fsx-for-ontap-s3-5bd6) | TL;DR の「FR-2 の代替パス」、および「なぜ FPolicy か」 |
| Part 4（FPolicy Event-Driven） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-s3ap-serverless-part4-event-driven-fpolicy) | TL;DR |
| Phase 13 / Part 5 | [dev.to](https://dev.to/aws-builders/from-serverless-patterns-to-field-ready-reference-architecture-fsx-for-ontap-s3-access-points-dhj) / [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-s3ap-serverless-part5-field-ready-28-patterns) | "Trigger strategy matters" の EVENT_DRIVEN |

リポジトリ側の該当箇所は本 PR で修正済みです。再発防止として
`scripts/check_portal_drift.py` の `MEASURED_FALSE` ルールが、全追跡ドキュメントと
`scripts/check_published_articles.py` 経由で公開記事の本文を走査します。

## この訂正が変えないこと

- 書き込みが NFS / SMB 経由で届くボリュームでの FPolicy パイプラインの設計と実装
- FPolicy サーバの実装、Fargate テンプレート、EventBridge ルーティング
- ネイティブイベント通知を求める機能要望の妥当性。むしろ、AP 経由の書き込みには現時点で
  ストレージ層のイベント駆動手段が存在しないという形で、要望の根拠が強くなりました
