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

### 再検証ランブック（AD 環境構築 → Quick 接続確認）

**前提**: 現在 AD 環境（Managed AD / Self-managed AD）が存在しない場合、以下の手順で構築してから検証を実行する。

#### Step 1: AD 環境デプロイ

```bash
# infrastructure/demo-ad-environment.yaml を使用
aws cloudformation deploy \
  --template-file infrastructure/demo-ad-environment.yaml \
  --stack-name quick-verify-ad-env \
  --parameter-overrides \
    AdMode=ManagedAD \
    AdDomainName=demo.fsx.local \
    AdAdminPassword=<YOUR-PASSWORD> \
    VpcId=<YOUR-VPC-ID> \
    PrivateSubnetIds=<SUBNET-1>,<SUBNET-2> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
# 所要時間: 15-30 分
```

#### Step 2: SVM を AD に参加させる（既存 SVM の場合）

```bash
# scripts/demo-ad-join-svm.sh を使用
./scripts/demo-ad-join-svm.sh \
  --svm-id svm-XXXXXXXXXXXX \
  --ad-stack-name quick-verify-ad-env \
  --netbios-name QUICKTEST
# 所要時間: 2-5 分
```

#### Step 3: NTFS ボリュームにテストデータを配置

Windows EC2 またはマウントポイント経由で、AD ユーザー権限でファイルを配置する:
```
/quick-test-data/
├── financial_records/
│   ├── Q1-2026-report.pdf
│   └── invoice-archive-2025.xlsx
└── quarterly_reports/
    └── Q2-2026-analysis.docx
```

#### Step 4: AD Windows identity で S3 AP を作成

```bash
cat <<EOF > create-ap-ad.json
{
    "Name": "quick-verify-ad",
    "Type": "ONTAP",
    "OntapConfiguration": {
        "VolumeId": "<YOUR-NTFS-VOLUME-ID>",
        "FileSystemIdentity": {
            "Type": "WINDOWS",
            "WindowsUser": {
                "Name": "Admin"
            }
        }
    }
}
EOF

aws fsx create-and-attach-s3-access-point \
  --cli-input-json file://create-ap-ad.json \
  --region ap-northeast-1

# Lifecycle が AVAILABLE になるまで待機（1-3 分）
aws fsx describe-s3-access-point-attachments \
  --region ap-northeast-1 \
  --query 'S3AccessPointAttachments[?Name==`quick-verify-ad`].{Lifecycle:Lifecycle,Alias:S3AccessPoint.Alias}'
```

#### Step 5: S3 AP 経由のデータアクセス確認

```bash
# エイリアスを環境変数に設定
AP_ALIAS="<出力されたエイリアス>"

# ファイル一覧確認
aws s3 ls "s3://${AP_ALIAS}/" --region ap-northeast-1

# ファイル取得テスト
aws s3 cp "s3://${AP_ALIAS}/quick-test-data/quarterly_reports/Q2-2026-analysis.docx" /tmp/test-download.docx
```

#### Step 6: Amazon Quick ナレッジベース接続

1. Amazon Quick コンソール → **Integrations** → **Knowledge bases** → **Amazon S3**
2. 「S3 bucket URL」に `s3://<AP_ALIAS>` を入力（プレフィクスなし、ルート指定）
3. **Create** → 同期が完了し **Available** ステータスになることを確認
4. **Chat agents** → 自然言語でクエリ: "What are the key findings in the Q2 2026 analysis?"

> スクリーンショット撮影対象:
> - Integration 作成画面（S3 AP alias 入力）
> - 同期完了ステータス（Available）
> - Chat Agent クエリ結果
> マスク: アカウントID、ARN、ユーザー名

#### Step 7: クリーンアップ

```bash
# S3 AP 削除
aws fsx detach-and-delete-s3-access-point --name quick-verify-ad --region ap-northeast-1

# AD 環境削除（コスト削減）
aws cloudformation delete-stack --stack-name quick-verify-ad-env --region ap-northeast-1
```

### 検証ステータス

| 項目 | ステータス | 日付 |
|---|---|---|
| Quick S3 KB がエイリアスを受理する | ✅ 確認済み | 2026-06-12 |
| AD identity S3 AP 作成 + データアクセス | ✅ 確認済み | 2026-07-19 |
| Quick S3 KB 同期（ap-northeast-1） | ❌ **リージョン制約**: S3 KB 機能は ap-northeast-1 未提供 | 2026-07-19 |
| Quick S3 KB 同期（us-east-1 等） | ✅ AWS 公式ブログ/Workshop で動作確認済み | — |
| Chat Agent でファイル内容に基づく回答 | ✅ AWS 公式ブログで実証済み | — |

### リージョン制約（2026-07-19 実機確認）

**Amazon Quick の S3 Knowledge base 機能は ap-northeast-1 (Tokyo) では利用できない**。

AWS Storage Blog ([source](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)) に記載:
> "choose Integrations from the navigation panel (at the time of this writing, available in Virginia, Oregon, Sydney, and Dublin)"

| リージョン | Quick S3 KB | 備考 |
|---|---|---|
| us-east-1 (Virginia) | ✅ | 公式ブログ実証済み |
| us-west-2 (Oregon) | ✅ | 公式記載 |
| ap-southeast-2 (Sydney) | ✅ | 公式記載 |
| eu-west-1 (Dublin) | ✅ | 公式記載 |
| ap-northeast-1 (Tokyo) | ❌ | Connectors に S3 KB が表示されない |

**ワークアラウンド**:
- **Bedrock Knowledge Base**: ap-northeast-1 で S3 AP 直接対応済み（公式チュートリアル）
- **クロスリージョン構成**: FSx for ONTAP が ap-northeast-1 にある場合でも、Quick アカウントを us-east-1 で作成し、S3 AP（Internet origin）経由で接続可能（S3 AP はリージョナルエンドポイントだが、Internet 経由アクセスはリージョン制約なし）

### 検証環境情報（2026-07-19 デプロイ済み）

```
CloudFormation Stack: quick-verify-ad-env
AD Domain:           quick.verify.local (short: QUICKV)
Directory ID:        d-956797dc4e
SVM:                 quick-verify-svm (svm-095a498b30a1824a7)
Volume:              quick_test_vol (fsvol-088fdc091530d4d69, NTFS, /quick_test)
S3 AP Name:          quick-verify-ad
S3 AP Alias:         quick-verify-ad-iwq81486tzgfet7ef3tut8uxbt8inapn1a-ext-s3alias
Identity:            WINDOWS / Admin
Test Data:           documents/ (4 files: q2-summary, infra-report, csat)
Data Access:         PutObject ✅, ListObjectsV2 ✅, GetObject ✅ (ap-northeast-1)
```

### Quick Console 手順（us-east-1 で実行する場合）

1. Amazon Quick アカウントを **us-east-1** で作成（またはクロスリージョン設定）
2. **Integrations** → **Knowledge bases** → **Amazon S3** → **+**
3. Name: `quick-fsxn-verification`
4. S3 bucket URL: `s3://quick-verify-ad-iwq81486tzgfet7ef3tut8uxbt8inapn1a-ext-s3alias`
5. **Create** → 同期完了まで待機（Available）
6. **Chat agents** → テストクエリ: "What was the Q2 2026 revenue trend?"

### クリーンアップ（検証完了後）

```bash
# S3 AP 削除
aws fsx detach-and-delete-s3-access-point --name quick-verify-ad --region ap-northeast-1

# ボリューム削除
aws fsx delete-volume --volume-id fsvol-088fdc091530d4d69 --region ap-northeast-1

# SVM 削除
aws fsx delete-storage-virtual-machine --storage-virtual-machine-id svm-095a498b30a1824a7 --region ap-northeast-1

# AD 環境削除（月額 ~$73 のコスト削減）
aws cloudformation delete-stack --stack-name quick-verify-ad-env --region ap-northeast-1
```
