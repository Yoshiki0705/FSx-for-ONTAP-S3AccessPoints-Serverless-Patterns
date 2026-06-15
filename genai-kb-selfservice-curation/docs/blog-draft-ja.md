# 業務部門がWindowsドラッグ＆ドロップでAIナレッジを自助運用する — FSx for ONTAP S3 アクセスポイント × Bedrock Knowledge Base

> ドラフト（レビュー用）。公開前にペルソナレビューボードの指摘を反映する。

## TL;DR

「AIに使わせたいデータは、このWindowsフォルダーに置いて、自分でメンテナンスしてください」——
IT部門の手作業（コピー・S3アップロード・手動取り込み）を排除し、業務部門が**使い慣れたWindowsエクスプローラーのドラッグ＆ドロップだけ**でAmazon Bedrock Knowledge Baseのデータソースを維持できるようにするパターン（UC29）を実装・検証した。

取り込みトリガーは運用成熟度に応じて3段階を用意する:

- **シナリオA（手動）**: Windowsで配置 → 人がコンソール/CLIで同期
- **シナリオB（定期自動化）**: EventBridge Scheduler + Step Functionsで15分間隔の差分同期
- **シナリオC（FPolicyイベント駆動）**: ファイル配置の瞬間にFPolicyが検知 → リアルタイム同期

データはFSx for ONTAP上の**正本のまま**（S3へのコピーなし）、S3 Access Point経由で読み取りのみ。

## なぜこのパターンか

エンタープライズのAIナレッジ運用でよくある課題:

| 課題 | 従来 | 本パターン |
|------|------|-----------|
| ナレッジ更新がIT部門待ち | 依頼チケット → 手作業ETL | 現場がドラッグ＆ドロップ |
| S3コピーによる二重管理 | 正本とS3コピーが乖離 | S3 AP経由で正本を直接データソース化 |
| 取り込み忘れ | 人手依存 | 自動Ingestion（B/C） |
| 専門スキル必須 | ETL/S3/Bedrock知識 | Windows操作のみ |

## アーキテクチャ

業務ユーザーはFSx for ONTAPの**AI専用ボリューム**（SMB共有、NTFS ACLで部署別に権限分離）へドラッグ＆ドロップする。同じボリュームをS3 Access Point経由でBedrock Knowledge Baseのデータソースに接続し、ファイル変更を検知して取り込む。

ロール構成はAmazon Quickが対象とする業務ロールに合わせる: sales / marketing / finance / information-technology / operations / legal / developers の7ロール。

## シナリオC: FPolicyイベント駆動リアルタイム同期

シナリオBの「15分間隔ポーリング」を、FPolicyのリアルタイム検知に置き換える。

```
Windows/NFS ファイル操作
  → FPolicy 即時検知（CREATE/WRITE/DELETE/RENAME）
  → FPolicy Server → SQS → Bridge Lambda → EventBridge カスタムバス
  → EventBridge Rule（file_path prefix = ai_knowledge）
  → KB Trigger Lambda（デバウンス）→ StartIngestionJob
  → Bedrock KB → 数十秒〜数分で反映
```

FPolicy → SQS → Bridge → EventBridge の前段は既存のevent-driven-fpolicyパターンの基盤を再利用し、UC29側はEventBridgeルールとKB Trigger Lambdaを追加するだけ。

> ⚠️ **取りこぼし対策**: Bedrock Ingestionはジョブ開始時点のソース全走査のため、ジョブ実行中に追加されたファイルはその実行に含まれない（lost-update window）。シナリオCは単独で取りこぼしゼロを保証しない。**必ずシナリオB（定期リコンサイル同期）と併用**し、後追い取り込みの安全網とする。失敗イベントはEventBridgeのリトライとDLQで捕捉する。

### 名前空間の落とし穴

実装で得た重要な学び: FPolicyが報告するファイルパスはONTAPボリュームパス名前空間（`ai_knowledge/...`、アンダースコア）であり、KBのS3取り込みプレフィックス（`ai-knowledge/`、ハイフン）とは**別物**。初回実装で両者を混同し、プレフィックス不一致で誤スキップした。EventBridgeルールとLambdaの二次フィルタはFPolicyパスで判定するよう専用パラメータに分離した。

## 実機検証で得た学び

### Windows identity S3 アクセスポイントは専用ADで成功

リテラルなWindowsドラッグ＆ドロップ体験を実証するため、専用のAWS Managed Microsoft AD + Windows EC2 + AD連携SVMを構築した。

- **AD連携SVMのOU指定**: AWS Managed Microsoft ADでは`OU=Computers,DC=...`はAWS管理で委任権限がなくMISCONFIGUREDになる。ドメイン名と同名のOU（`OU=<domain>,DC=...`）を指定する
- **CIFS共有作成**: ファイルシステム管理LIF（SVM管理LIFではない）に対してONTAP REST APIを実行する
- **Windows identity S3 AP**: 稼働中の専用ADでは問題なく作成でき、Windowsでドラッグ＆ドロップしたファイルがS3 AP経由で読み取れることを実証した

### 削除ライフサイクル

「現場がファイルを消したらAIからも消える」を実機で実証: ファイル削除 → 同期で`numberOfDocumentsDeleted=1` → 再クエリで「情報が見つかりません」。データソースの`dataDeletionPolicy=DELETE`による。反映は次回同期まで遅延するため、緊急失効が必要なら直接Ingestion APIを併用する。

## アクセス制御の3層

S3 APのデータソース境界はボリューム/プレフィックス単位。利用者個人ごとの可視範囲制御が必要な場合は用途別に選ぶ:

1. **検索絞り込み** = Bedrock KBメタデータフィルタ（本UC、AWS認可ではない）
2. **文書レベルACL** = Amazon Quick S3ナレッジベース（UC30、利用者・グループ単位）
3. **チャンク単位の権限フィルタ** = カスタムPermission-aware RAG（FC3、AD SID/NTFS ACL、規制業種向け）

## コスト考慮

> 概算であり保証値ではない。最新はAWS Pricing Calculatorで確認すること（time-sensitive）。

- サーバーレス従量課金（Lambda / S3 API / EventBridge / Bedrock）
- シナリオCはFPolicy Server（Fargate）とPersistent Storeが追加で必要
- ベクトルストア（OpenSearch Serverless or S3 Vectors）のコストに留意

## まとめ

UC29は、エンタープライズの非構造化ナレッジ運用を「IT部門の手作業」から「現場主導のセルフサービス」へ移行させる。A→B→Cの3段階で、体験から本番運用、リアルタイム同期まで段階的に進化できる。データはFSx for ONTAPの正本のまま、S3 Access Pointで読み取り、Bedrock Knowledge Baseがマネージドに取り込む。

**リポジトリ**: github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

## Governance Note

本記事は技術アーキテクチャガイダンスであり、法的・コンプライアンス・規制上の助言ではない。ベンチマーク・料金はtime-sensitive。S3 APのデータソース境界はボリューム/プレフィックス単位であり、利用者個人ごとの可視範囲制御が必要な場合はカスタムRAGを検討すること。
