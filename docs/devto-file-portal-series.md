# ファイルポータル記事シリーズの計画

🌐 **Language / 言語**: 日本語 | [English](devto-file-portal-series.en.md)

dev.to のファイルポータルシリーズの構成です。S3 AP サーバーレスパターン集とは**別シリーズ**に
します（理由と命名規約は [シリーズ構成とタグ付けの規約](./devto-series-cleanup-guide.md)）。

- シリーズ名（EN）: `FSx for ONTAP File Portal`
- シリーズ名（JA）: `FSx for ONTAP ファイルポータル`
- タグ: `aws`, `amplify`, `fsxforontap` + 記事固有 1 個

## 状態

**未公開です。** 以下は計画であり、記事本文はまだありません。公開済みの記事があるかのように
リンクを張らないこと。

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
