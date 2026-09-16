# ファイルポータル記事シリーズ

🌐 **Language / 言語**: 日本語 | [English](devto-file-portal-series.en.md)

ファイルポータルシリーズは全 7 回で、日本語版ははてなブログ、英語版は dev.to にあります。
S3 AP サーバーレスパターン集とは**別シリーズ**です（理由と命名規約は
[シリーズ構成とタグ付けの規約](./devto-series-cleanup-guide.md)）。

- シリーズ名（dev.to）: `FSx for ONTAP File Portal`
- タグ: `aws`, `fsxforontap` ほか記事ごとに 2 個まで

## 公開済みの記事

| # | テーマ | 日本語 | English |
|---|---|---|---|
| 1 | ブラウザからの到達（Amplify Gen 2 と Nextcloud の使い分け） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-1-browser-access) | [dev.to](https://dev.to/aws-builders/adding-a-file-portal-to-fsx-for-ontap-s3-access-points-choosing-between-amplify-gen2-and-887) |
| 2 | ランサムウェア対応と WORM 保持（ARP/AI・SnapLock・監査ログ） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-2-ransomware-worm) | [dev.to](https://dev.to/aws-builders/embedding-storage-operations-into-a-file-portal-from-arpai-incident-response-to-regulatory-1oih) |
| 3 | AI エージェント統合（AgentCore の MCP と人の承認） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-3-ai-agent-mcp) | [dev.to](https://dev.to/aws-builders/embedding-ai-agents-into-a-file-portal-from-agentcore-mcp-to-multi-agent-teams-part-3-19m1) |
| 4 | 運用操作の委譲と記録（182 アクション、押せないボタン） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-4-storage-operations) | [dev.to](https://dev.to/aws-builders/putting-fsx-for-ontap-operations-on-a-file-portal-on-aws-182-actions-and-the-design-of-425g) |
| 5 | 実機で止められたもの（FlexGroup 作成、容量リバランス） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-5-what-only-the-cluster-tells-you) | [dev.to](https://dev.to/aws-builders/what-i-learned-driving-fsx-for-ontap-from-a-file-portal-on-aws-flexgroup-creation-capacity-3gkd) |
| 6 | ONTAP 機能の到達範囲（qtree・quota・FlexClone の実測） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-6-outside-the-portal) | [dev.to](https://dev.to/aws-builders/what-i-left-off-the-file-portal-on-aws-how-far-fsx-for-ontap-features-reach-and-the-work-handed-hk8) |
| 7 | 構築ツールの比較（Nx Plugin for AWS 1.0 / AWS Blocks / Amplify Gen 2） | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-7-nx-blocks-amplify-gen2) | [dev.to](https://dev.to/aws-builders/what-a-stack-deletion-leaves-behind-nx-plugin-for-aws-10-aws-blocks-and-amplify-gen-2-compared-10fg) |

**日本語版は dev.to に投稿していません。** dev.to のシリーズウィジェットは英語版 7 本で
`FSx for ONTAP File Portal (7 Part Series)` を表示します。

## 記事と出典の対応

各記事はリポジトリ内のドキュメントを出典にしています。記事より詳しい数値と再現手順は
出典側にあります。

| # | 主な出典 |
|---|---|
| 1 | [UI の選択肢](./file-portal-amplify-gen2.md), [ポータルとサービスの隙間](./aws-feature-requests/file-portal-service-gap.md) |
| 2 | [ARP/AI と EMS の罠](./agent/pitfalls-arp-ems.md), [SnapLock の罠](./agent/pitfalls-snaplock.md) |
| 3 | [生成 AI とエッジの罠](./agent/pitfalls-genai-edge.md) |
| 4 | [認可設計](./ja/portal-authorization-design.md), [認可モデル](./ja/portal-authorization-model.md) |
| 5 | [FlexGroup の罠](./agent/pitfalls-flexgroup.md), [ボリュームのライフサイクルの罠](./agent/pitfalls-volume-lifecycle.md) |
| 6 | [S3 AP と ONTAP の罠](./agent/pitfalls-s3ap-ontap.md), [4 機能の先へ](./ja/portal-parity-next-steps.md) |
| 7 | [アプリの構築ツールの選択肢](./ja/scaffolding-and-backend-toolkit-choices.md), [デプロイ検証と後片付けの手順](./ja/scaffolding-deploy-verification.md), [同じ 4 機能を 3 つの構築ツールで実装した記録](./ja/portal-parity-four-features.md) |

## 別シリーズにする理由

S3 AP シリーズの読者は、Lambda と Step Functions でデータ処理パイプラインを作る人です。
ファイルポータルの読者は、**FSx for ONTAP 上のファイルを非管理者に触らせる方法**を探している人で、
関心は認可設計、8 言語 UI、スマートフォンからの到達性、そして「そもそも作るべきか」に向いています。
重なるのは S3 AP をデータ経路として使う点だけなので、同じシリーズに混ぜると
どちらの読者にも半分が無関係になります。

## 公開時の注意

- **用語はブログ側を正とする。** 記事で言い換えた語（`synth` は「テンプレートの静的解析
  （`synth`）」、構築ツールを「土台」と呼ばない）は、リポジトリ側のドキュメントも揃える
- **スクリーンショットは `docs/screenshots/` のマスク済みのものを使う。** 撮り直す場合は
  [撮影と置換の手順](./screenshots/SCREENSHOT_ADDITION_WORKFLOW.md) に従うこと
- 性能・コストの数値は、測定条件（リージョン、ONTAP バージョン、構成）を必ず併記する
- 「一度も動いていなかった」系の話は、**修正済みであることと、再発を防ぐ仕組み**まで書く。
  不具合の列挙だけでは読者の役に立たない
- 他サービス・他製品は対比の相手ではなく選択肢として書く（優劣の断定をしない）
- 回数表記（「全 7 回」）はシリーズ全体に埋め込まれている。1 本増やすときは既存記事の
  本文と記事概要（`og_description`）も更新する
