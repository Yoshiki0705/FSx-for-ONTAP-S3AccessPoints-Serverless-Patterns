# ファイルポータル記事シリーズの計画

🌐 **Language / 言語**: 日本語 | [English](devto-file-portal-series.en.md)

dev.to のファイルポータルシリーズの構成です。S3 AP サーバーレスパターン集とは**別シリーズ**に
します（理由と命名規約は [シリーズ構成とタグ付けの規約](./devto-series-cleanup-guide.md)）。

- シリーズ名（EN）: `FSx for ONTAP File Portal`
- シリーズ名（JA）: `FSx for ONTAP ファイルポータル`
- タグ: `aws`, `amplify`, `fsxforontap` + 記事固有 1 個

## 状態

**Part 1〜3 は公開済みです。** もともと S3 AP シリーズに属していた 3 本を、2026-08-15 に
このシリーズへ移しました（`series` と `tags` を上表の定義に変更）。dev.to のシリーズ
ウィジェットは `FSx for ONTAP File Portal (3 Part Series)` を表示します。

| # | 記事 | 状態 |
|---|---|---|
| 1 | [Adding a File Portal to FSx for ONTAP S3 Access Points](https://dev.to/aws-builders/adding-a-file-portal-to-fsx-for-ontap-s3-access-points-choosing-between-amplify-gen2-and-887) | 公開済み（EN）/ [はてなブログ（JA）](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-1-browser-access) |
| 2 | [Embedding Storage Operations into a File Portal](https://dev.to/aws-builders/embedding-storage-operations-into-a-file-portal-from-arpai-incident-response-to-regulatory-1oih) | 公開済み（EN）/ [はてなブログ（JA）](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-2-ransomware-worm) |
| 3 | [Embedding AI Agents into a File Portal](https://dev.to/aws-builders/embedding-ai-agents-into-a-file-portal-from-agentcore-mcp-to-multi-agent-teams-part-3-19m1) | 公開済み（EN）/ [はてなブログ（JA）](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-3-ai-agent-mcp) |
| 4 | ONTAP の運用操作を載せる（174 アクション） | **下書きあり・未公開**。JA / EN の下書きは `drafts/blog/article-file-portal-part4-draft{,.en}.md`（`drafts/` は gitignore なのでリンクは張れません）|

**JA 側のシリーズ（`FSx for ONTAP ファイルポータル`）にはまだ記事がありません。** Part 1〜3 の
日本語版ははてなブログにあり、dev.to には投稿していません。dev.to の JA シリーズを立てるなら
先に記事を投稿する必要があります。

下の「記事構成（案）」は**まだ書いていないテーマの候補**です。公開済みの 3 本とは対応しません。

## なぜ別シリーズにするか

S3 AP シリーズの読者は、Lambda と Step Functions でデータ処理パイプラインを作る人です。
ファイルポータルの読者は、**FSx for ONTAP 上のファイルを非管理者に触らせる方法**を探している人で、
関心は認可設計、8 言語 UI、スマートフォンからの到達性、そして「そもそも作るべきか」に向いています。
重なるのは S3 AP をデータ経路として使う点だけなので、同じシリーズに混ぜると
どちらの読者にも半分が無関係になります。

## 記事構成（案）

各記事はリポジトリ内の既存ドキュメントを出典にします。書き下ろしが必要な部分は「新規」と記載。

| # | テーマ | 主な出典 | 記事固有タグ |
|---|---|---|---|
| 1 | **そもそも作る必要があるか** — Transfer Family web apps / Nextcloud / Amplify Gen2 / 作らない選択の比較と選び方 | [file-portal-amplify-gen2.md](./file-portal-amplify-gen2.md), [file-portal-service-gap.md](./aws-feature-requests/file-portal-service-gap.md) | `architecture` |
| 2 | **認可を二層で設計する** — Cognito グループと S3 AP / ONTAP 側の認可、監査証跡の連鎖 | [portal-authorization-design.md](./ja/portal-authorization-design.md), [s3ap-authorization-model.md](./s3ap-authorization-model.md) | `cognito` |
| 3 | **Amplify Gen2 で踏んだ制約** — クロススタック Data Source、cdk-nag の運用、sandbox の hotswap、SharedPythonLayer | [amplify-gen2-cdk-patterns.md](../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.md), [portal-cdk-quality-gates.md](./agent/portal-cdk-quality-gates.md) | `cdk` |
| 4 | **8 言語 UI を型で守る** — `ja.ts` を型の源にする、ハードコード文字列を機械で落とす、テーマトークン | [portal-i18n.md](./agent/portal-i18n.md), [CONTRIBUTING-UI.md](../solutions/amplify-portal/docs/CONTRIBUTING-UI.md) | `i18n` |
| 5 | **一度も動いたことがなかった機能をどう見つけたか** — 実機検証で判明した不具合（presign の SigV2 既定、FlexGroup 作成の FabricPool 制約、リバランスの実行時間制約）と、それを再発させない仕組み | [verification-results.md](../solutions/amplify-portal/docs/verification-results.md), [flexgroup-rebalance-verification.md](../solutions/amplify-portal/docs/flexgroup-rebalance-verification.md) | `testing` |
| 6 | **利用者に渡す** — スマートフォンからの到達性、引き渡し時に説明する範囲、一次対応 | [portal-user-guide.md](./ja/portal-user-guide.md), [portal-handover-guide.md](../solutions/amplify-portal/docs/portal-handover-guide.md), [portal-mobile-guide.md](./ja/portal-mobile-guide.md) | `webdev` |

## 公開時の注意

- **スクリーンショットは `docs/screenshots/` のマスク済みのものを使う。** 撮り直す場合は
  [撮影と置換の手順](./screenshots/SCREENSHOT_ADDITION_WORKFLOW.md) に従うこと
- 性能・コストの数値は、測定条件（リージョン、ONTAP バージョン、構成）を必ず併記する
- 「一度も動いていなかった」系の話は、**修正済みであることと、再発を防ぐ仕組み**まで書く。
  不具合の列挙だけでは読者の役に立たない
- 他サービス・他製品は対比の相手ではなく選択肢として書く（優劣の断定をしない）
