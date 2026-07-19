# UC30: Amazon Quick コンソール設定手順

Amazon Quick Suite 本体のデータソース接続はコンソールで構成する（本テンプレート対象外）。
本書は再現性のための手順テキスト。スクリーンショットは撮影時にこの手順に沿ってマスク取得する。

> Amazon Quick の UI・名称・手順は変更されます（time-sensitive）。最新は [Amazon Quick ユーザーガイド](https://docs.aws.amazon.com/quick/latest/userguide/) を参照。

## 0. 前提

- Amazon Quick Suite が有効化済み（管理者）
- SAM スタック（UC30）デプロイ済み、Glue テーブル作成済み、Lake Formation 権限付与済み
- `quick-workspace/{index,analytics,flows}/<role>/` にデータ投入済み

## 1. Quick Index（非構造化検索）データソース接続

1. Quick コンソール → Knowledge / Index → 「データソースを追加」
2. ソースに **Amazon S3（S3 Access Point）** を選択
3. バケット/AP に S3 AP エイリアス、プレフィックスに `quick-workspace/index/` を指定
4. （任意）**文書レベル ACL** を有効化し、フォルダー/ファイルに閲覧可能ユーザー・グループを設定
5. 同期を実行 → インデックス作成完了を確認

> スクショ対象: データソース一覧、同期完了ステータス、ACL 設定画面（マスク: アカウントID/ユーザー名/メール）

## 2. Quick Sight（BI）データセット作成

1. Quick コンソール → Quick Sight → データセット → 新規
2. データソースに **Athena** を選択、WorkGroup=`quick-workspace-wg`
3. データベース `quick_workspace_db` → テーブル `sales_pipeline` / `it_incidents` を選択
4. 可視化を作成（例: ステージ別パイプライン金額、重大度別 平均 MTTR）
5. （任意）**行レベルセキュリティ（RLS）** でロール別の行可視性を設定

> スクショ対象: データセット定義、ダッシュボード、RLS 設定（マスク: アカウントID/ARN）

## 3. Quick Flows（アクション）接続

1. Quick コンソール → Flows → 新規フロー
2. HTTP アクションを追加し、エンドポイントに Action API（`POST /action`）を指定
3. 認証は **IAM（SigV4）**。Quick の接続/コネクタに署名用資格情報を構成
4. ペイロード例（`flows/<role>/*.json`）でテスト実行
   - `create_action_item` / `generate_brief` / `request_approval`（高リスクは承認待ち）

> スクショ対象: フロー定義、実行結果、承認待ち（pending_approval）通知（マスク: 個人名/メール）

## 4. カスタム権限（ガバナンス）

- Quick Suite の権限は **account / role / user の3階層**（user > role > account）
- カスタム権限プロファイルで機能（ダッシュボード編集等）を制限
- ロールフォルダー（`index/<role>/`）と Quick グループを対応づける

> スクショ対象: 権限プロファイル一覧、ロール割り当て（マスク: ユーザー名/グループ名）

## マスキング

スクリーンショットは公開前に環境固有情報（アカウントID、ARN、IP、ユーザー名、メール、内部ホスト名）を
マスクすること（プロジェクトのスクリーンショットマスキング手順に従う）。

---

## 実機検証で判明した制約（2026-06-12）→ 原因特定済み（2026-07-18 修正）

Amazon Quick を有効化し、Quick Knowledge の **Amazon S3 コネクタ** で FSx for ONTAP S3 Access Point への接続を試行した結果:

### 判明事項

1. **Quick の S3 ナレッジベースは S3 AP エイリアスを「有効なバケット URL」として受理する**
   （`s3://<alias>-ext-s3alias` は形式検証を通過。`s3://<alias>/<prefix>/` のようにパス付きは「valid S3 bucket URL ではない」と拒否＝バケットルート指定が前提）。
2. しかし接続検証で **「You do not have permissions to access the S3 bucket.」** となり接続失敗。

### 原因（2026-07-18 修正）

**この失敗は S3 AP の FileSystemIdentity 設定の問題であり、サービスの構造的制約ではない。**

本検証では S3 AP を **UNIX root identity** で構成していた。AWS 公式ブログ（[Enabling AI-powered analytics on enterprise file data](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)）および [AWS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/08-quicksuite/61-setup) では、**AD ユーザーまたはサービスアカウントの Windows identity** で S3 AP を構成し、正常に Quick ナレッジベースの同期・Chat Agent 検索が動作している。

前回の失敗原因:
- UNIX identity の S3 AP では、Quick のデータアクセスロールを AP リソースポリシーに追加しようとすると `MalformedPolicy: Invalid principal in policy` エラーが発生
- AD ベースの Windows identity で S3 AP を構成すれば、デュアルレイヤー認証（IAM + NTFS ACL）が正しく機能し、Quick から接続可能

### 修正アクション

- [ ] AD identity で S3 AP を再構成して検証を再実行
- [ ] スクリーンショットを撮影し `docs/screenshots/masked/` に追加
- [ ] 本ドキュメントの検証ステータスを「✅ 動作確認済み」に更新
