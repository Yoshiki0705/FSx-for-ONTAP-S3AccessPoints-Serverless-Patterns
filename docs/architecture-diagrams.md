# 構成図インデックス（ライト / ダーク）

🌐 **Language / 言語**: 日本語 | [English](architecture-diagrams.en.md)

このリポジトリの構成図は、**ライトテーマ（白背景）** と **ダークテーマ（濃色背景）** の 2 種類を同じ内容で公開しています。

- **ライトテーマが既定**です。README・ドキュメント・ブログ記事に表示されるのはすべてライト版です。白背景の資料や印刷、スライドへの貼り込みでそのまま使えます。
- **ダークテーマ**は、OS やブラウザをダークモードで使っている読者向けの選択肢です。下表の「ダーク」列から開けます。

どちらも配色以外は同一で、レイアウト・ラベル・注記は一致しています。図はテーマを固定してエクスポートしてあるため、閲覧環境のダークモード設定によって勝手に反転することはありません。

> **配色に関する補足**: ダーク版は AWS Architecture Icons 公式アセットパッケージの `Res_*_48_Dark`（白い線画）を使用しています。ライト版の `Res_*_48_Light`（濃紺の線画）を濃色背景にそのまま置くと判読できないため、アイコン素材ごと差し替えています。サービスアイコン（`Arch_*`）は公式に単色タイル 1 種類のみのため、両テーマで共通です。

## Part 1 — ファイルポータルの全体構成

| 図 | 内容 | ライト（既定） | ダーク |
|----|------|:---:|:---:|
| 全体構成 | 2 つのフロントエンドが同一の S3 Access Point を経由して同じボリュームを参照する | [表示](images/architecture-overview.svg) | [表示](images/architecture-overview-dark.svg) |
| Amplify Gen2 ポータル | AI 処理ポータルの構成（VPC 外 Lambda / S3 AP / 監査ログ） | [表示](images/amplify-vpc-split.svg) | [表示](images/amplify-vpc-split-dark.svg) |
| Nextcloud | External Storage App で S3 Access Point をマウントするファイル共有 UI | [表示](images/nextcloud-external-storage.svg) | [表示](images/nextcloud-external-storage-dark.svg) |
| 併用構成 | Amplify Gen2 と Nextcloud が同一ボリュームを共有し NFS / SMB と共存する | [表示](images/coexistence-3path.svg) | [表示](images/coexistence-3path-dark.svg) |

## Part 2 — ストレージ運用機能

| 図 | 内容 | ライト（既定） | ダーク |
|----|------|:---:|:---:|
| 管理操作の経路 | ブラウザから Cognito・AppSync・VPC 内 Lambda 経由で ONTAP を操作する | [表示](images/part2-admin-operations.svg) | [表示](images/part2-admin-operations-dark.svg) |
| ARP/AI ライフサイクル | インシデントを 4 状態（検知 / 封じ込め / 調査中 / 解決済み）で管理する | [表示](images/part2-arp-incident-lifecycle.svg) | [表示](images/part2-arp-incident-lifecycle-dark.svg) |
| 監査ログの確認経路 | CloudTrail のデータイベントを Glue Data Catalog 経由で Athena が集計する | [表示](images/part2-audit-log-pipeline.svg) | [表示](images/part2-audit-log-pipeline-dark.svg) |
| ONTAP REST API 経路 | 管理 LIF がプライベートなため Lambda を VPC 内に置く理由 | [表示](images/part2-ontap-rest-api-path.svg) | [表示](images/part2-ontap-rest-api-path-dark.svg) |
| PoC から本番へ | 3 フェーズでの接続追加とハードニング | [表示](images/part2-poc-to-production.svg) | [表示](images/part2-poc-to-production-dark.svg) |

## Part 3 — AI エージェント

| 図 | 内容 | ライト（既定） | ダーク |
|----|------|:---:|:---:|
| AI エージェント全体構成 | Bedrock Converse と AgentCore（MCP）でファイルにアクセスする | [表示](images/part3-ai-agent-overview.svg) | [表示](images/part3-ai-agent-overview-dark.svg) |
| AgentChat の 3 モード | mode=kb / mode=agent / mode=multi の分岐とツール呼び出し | [表示](images/part3-agentchat-modes.svg) | [表示](images/part3-agentchat-modes-dark.svg) |
| セマンティック検索 | Bedrock Knowledge Bases と OpenSearch Service によるベクトル検索 | [表示](images/part3-semantic-search.svg) | [表示](images/part3-semantic-search-dark.svg) |
| マルチエージェント協調 | Supervisor / Collaborator / Reviewer の役割分担 | [表示](images/part3-agent-teams.svg) | [表示](images/part3-agent-teams-dark.svg) |

## SaaS からの移行

| 図 | 内容 | ライト（既定） | ダーク |
|----|------|:---:|:---:|
| 群 A の 2 経路 | ストレージエンドポイントを持つ移行元の、DataSync 直行と S3 経由 2 段 | [表示](images/saas-migration-group-a-routes.svg) | [表示](images/saas-migration-group-a-routes-dark.svg) |
| 群 B の中央実行構成 | 管理者 API を呼ぶ移行ワーカーを Step Functions で分割実行する | [表示](images/saas-migration-group-b-worker.svg) | [表示](images/saas-migration-group-b-worker-dark.svg) |

## ファイル形式と命名規則

| 用途 | パス | 備考 |
|------|------|------|
| ドキュメント表示 | `docs/images/<name>.svg` | ライト。README とドキュメントからの相対参照 |
| ドキュメント表示（ダーク） | `docs/images/<name>-dark.svg` | 上表の「ダーク」列 |
| ブログ表示 | `docs/images/png/<name>@2x.png` | ライト。絶対 raw URL 参照 |
| ブログ表示（ダーク） | `docs/images/png/<name>-dark@2x.png` | — |
| 編集用ソース | `docs/diagrams/<name>.drawio` | ライトが唯一の手編集対象 |
| 編集用ソース（ダーク） | `docs/diagrams/dark/<name>.drawio` | 生成物。手編集しない |

英語版の図はファイル名に `-en` が付きます（例: `amplify-vpc-split-en.svg` / `amplify-vpc-split-en-dark.svg`）。

## 図の再生成

ダーク版はライト版から生成するため、ライト版を編集したあとに続けて実行します。アイコンパッケージは[公式ページ](https://aws.amazon.com/architecture/icons/)から取得したものをリポジトリ外に展開して指定します。

```bash
# 1. ダークテーマのソースを再生成
python3 scripts/make-dark-diagrams.py --icon-root /tmp/awsicons

# 2. ライト / ダーク両方を SVG + PNG@2x にエクスポート
bash scripts/export-diagrams.sh
```

## 関連ドキュメント

- [ファイルポータル UI 選定ガイド（Amplify / Nextcloud / Custom）](file-portal-amplify-gen2.md)
- [Amplify Gen2 ポータル README](../solutions/amplify-portal/README.ja.md)
- [ポータル実装ガイド](../solutions/amplify-portal/docs/IMPLEMENTATION.md)
