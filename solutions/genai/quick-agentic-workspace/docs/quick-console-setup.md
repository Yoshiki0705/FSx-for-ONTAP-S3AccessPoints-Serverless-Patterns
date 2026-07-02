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

## 実機検証で判明した制約（2026-06-12）

Amazon Quick を有効化し、Quick Knowledge の **Amazon S3 コネクタ** で FSx for ONTAP S3 Access Point への接続を試行した結果:

### 判明事項

1. **Quick の S3 ナレッジベースは S3 AP エイリアスを「有効なバケット URL」として受理する**
   （`s3://<alias>-ext-s3alias` は形式検証を通過。`s3://<alias>/<prefix>/` のようにパス付きは「valid S3 bucket URL ではない」と拒否＝バケットルート指定が前提）。
2. しかし接続検証で **「You do not have permissions to access the S3 bucket.」** となり接続失敗。
3. この失敗は「特定の IAM 権限が不足している」問題ではなく、**構造的な認可パス不一致**である。以下の3要因が重なる:
   - **ARN フォーマット不一致**: FSx for ONTAP S3 AP は `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式。Quick コネクタの内部 IAM 評価がエイリアスをバケット名（`arn:aws:s3:::{alias}`）として扱っている可能性が高く、IAM policy evaluation が一致しない。
   - **AP リソースポリシーが principal を拒否**: Quick のデータアクセスロール（`aws-quicksight-service-role-v0` 等）を S3 AP リソースポリシーに追加しようとすると `MalformedPolicy: Invalid principal in policy` エラー。FSx for ONTAP S3 AP のポリシーには受理可能な principal に制約がある。
   - **Layer 2（ファイルシステム ID 認証）**: IAM 層が仮に解決しても、S3 AP に紐付いた ONTAP ファイルシステム ID（UNIX UID または Windows AD ユーザー）がファイル/ディレクトリへの読み取り権限を持っていなければアクセスは拒否される。

> 画面証跡: `docs/screenshots/masked/quick-s3-kb-connect.png`（エイリアス受理＋権限メッセージ）

### Remediation / 推奨

- **本命の RAG 経路は Bedrock Knowledge Base（UC29）を使う**。FSx for ONTAP S3 AP → Bedrock KB は実機で取り込み COMPLETE 済み。
  Quick からは Bedrock KB を参照する構成（または Quick の RAG を別途）に寄せる。
- Quick Index で純粋な S3 を使いたい場合は、**通常の S3 バケットにステージング**（FSx for ONTAP から S3 へ同期）して接続するのが確実。
- FSx for ONTAP S3 AP を Quick から直接使う場合は、AWS の
  「[Restrict access to sensitive documents in Amazon Quick knowledge bases for Amazon S3](https://aws.amazon.com/blogs/machine-learning/restrict-access-to-sensitive-documents-in-your-amazon-quick-knowledge-bases-for-amazon-s3/)」
  と FSx for ONTAP S3 AP のデュアルレイヤー認証要件（IAM + AP リソースポリシー + FSx identity）を満たすロール/ポリシー設計が必要。
  正確な Quick データアクセスロールを CloudTrail の AccessDenied から特定し、AP 側で許可する。
- **公式の AD 連携経路**: [Configuring S3 Access Points for FSx for NetApp ONTAP with Active Directory（AI-powered analytics）](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)。
  S3 AP を **Windows identity（AD）** で構成し、アクセスするロール/ユーザーをファイルシステム側で解決できるようにすることで、IAM とファイルシステム権限の2層を両立する。本検証 AP は UNIX root identity のため、Quick ロールの AP principal 追加が `MalformedPolicy` となった。

> **自身で試す場合のヒント**: CloudTrail で `AccessDenied` イベントを捕捉し、Quick が使用する正確な呼び出し元 principal ARN を特定すること。`MalformedPolicy` 制約を解決できれば（AD ベース ID で S3 AP を構成する等）、直接パスが開ける可能性はある。2026年6月時点では **Bedrock Knowledge Base → FSx for ONTAP S3 AP** が検証済みの RAG 取り込み経路。
- **Quick Sight（BI）** は Athena 経由（本UCの Athena Query Lambda / Glue テーブル）で接続可能。
  QuickSight ロールに Athena/Glue/Lake Formation/結果バケットの権限付与（Manage → Security & permissions ＋ LF grant）が前提。

> 本検証では、ライブ課金環境かつ共有 S3 AP のため、これ以上の試行錯誤的なポリシー変更は行わず、
> 上記を確定事項として記録した（投機的に付与した IAM はクリーンアップ済み）。
