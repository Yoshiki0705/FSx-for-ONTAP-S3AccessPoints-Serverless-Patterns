#!/bin/bash
# =============================================================================
# S3 Access Point for FSx for NetApp ONTAP — セットアップスクリプト
#
# FSx for ONTAP 上のボリュームに対して S3 Access Point を作成し、
# Amazon Quick からの検索・分析を可能にする
# =============================================================================
set -euo pipefail

# --- 設定 ---
REGION="${AWS_REGION:-ap-northeast-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# FSx ONTAP 情報（CloudFormation 出力から取得するか手動設定）
FSX_FILE_SYSTEM_ID="${FSX_FILE_SYSTEM_ID:-}"
SVM_NAME="${SVM_NAME:-svm_demo}"
VOLUME_NAME="${VOLUME_NAME:-vol_demo}"
S3_AP_NAME="${S3_AP_NAME:-snapmirror-demo-s3ap}"

echo "============================================"
echo "  S3 Access Point Setup for FSx ONTAP"
echo "============================================"
echo ""
echo "  Region:     ${REGION}"
echo "  Account:    ${ACCOUNT_ID}"
echo "  FSx ID:     ${FSX_FILE_SYSTEM_ID}"
echo "  SVM:        ${SVM_NAME}"
echo "  Volume:     ${VOLUME_NAME}"
echo "  S3 AP Name: ${S3_AP_NAME}"
echo ""

# --- 前提チェック ---
if [ -z "${FSX_FILE_SYSTEM_ID}" ]; then
    echo "❌ FSX_FILE_SYSTEM_ID が未設定です"
    echo ""
    echo "   CloudFormation 出力から取得:"
    echo "   export FSX_FILE_SYSTEM_ID=\$(aws cloudformation describe-stacks \\"
    echo "     --stack-name snapmirror-demo \\"
    echo "     --query 'Stacks[0].Outputs[?OutputKey==\`FsxFileSystemId\`].OutputValue' \\"
    echo "     --output text)"
    exit 1
fi

# --- Step 1: S3 Access Point 作成（ONTAP CLI 経由） ---
echo "📝 Step 1: S3 Access Point の作成"
echo ""
echo "  ⚠️  S3 Access Point は FSx コンソールまたは ONTAP CLI で作成します。"
echo "  以下のコマンドを FSx ONTAP の CLI で実行してください:"
echo ""
echo "  # FSx ONTAP CLI に SSH 接続"
echo "  ssh fsxadmin@<FSx_Management_IP>"
echo ""
echo "  # S3 サーバーを有効化"
echo "  vserver object-store-server create -vserver ${SVM_NAME} -object-store-server ${SVM_NAME}-s3"
echo ""
echo "  # バケット（Access Point）を作成"
echo "  vserver object-store-server bucket create \\"
echo "    -vserver ${SVM_NAME} \\"
echo "    -bucket ${S3_AP_NAME} \\"
echo "    -size 100GB \\"
echo "    -type nas"
echo ""
echo "  ───────────────────────────────────────────"
echo "  ※ 上記は ONTAP 9.12+ の S3 on NAS 機能です"
echo "  ※ AWS コンソールの FSx > S3 Access Points からも作成可能です"
echo ""

# --- Step 2: S3 AP エイリアスの取得 ---
echo "📝 Step 2: S3 Access Point エイリアスの確認"
echo ""
echo "  AWS コンソールの FSx > File systems > ${FSX_FILE_SYSTEM_ID} > S3 access points"
echo "  から S3 AP エイリアス (xxx-ext-s3alias) を取得してください。"
echo ""
echo "  または AWS CLI:"
echo "  aws fsx describe-file-systems --file-system-ids ${FSX_FILE_SYSTEM_ID} \\"
echo "    --query 'FileSystems[0].OntapConfiguration' --output json"
echo ""

# --- Step 3: IAM ポリシーの作成 ---
echo "📝 Step 3: IAM ポリシーの作成"

POLICY_DOC=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowS3APListBucket",
            "Effect": "Allow",
            "Action": "s3:ListBucket",
            "Resource": "arn:aws:s3:${REGION}:${ACCOUNT_ID}:accesspoint/${S3_AP_NAME}"
        },
        {
            "Sid": "AllowS3APGetObject",
            "Effect": "Allow",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:${REGION}:${ACCOUNT_ID}:accesspoint/${S3_AP_NAME}/object/*"
        },
        {
            "Sid": "AllowGetBucketLocation",
            "Effect": "Allow",
            "Action": "s3:GetBucketLocation",
            "Resource": "arn:aws:s3:${REGION}:${ACCOUNT_ID}:accesspoint/${S3_AP_NAME}"
        }
    ]
}
EOF
)

echo "  以下の IAM ポリシーを Amazon Quick のサービスロールに付与してください:"
echo ""
echo "${POLICY_DOC}" | python3 -m json.tool
echo ""

# ポリシーをファイルに保存
POLICY_FILE="/tmp/s3ap-policy-${S3_AP_NAME}.json"
echo "${POLICY_DOC}" > "${POLICY_FILE}"
echo "  💾 ポリシーファイル保存先: ${POLICY_FILE}"
echo ""

# --- Step 4: 動作確認 ---
echo "📝 Step 4: 動作確認"
echo ""
echo "  S3 AP エイリアスを使用して動作確認:"
echo ""
echo "  # ファイル一覧取得"
echo "  aws s3api list-objects-v2 \\"
echo "    --bucket '<S3_AP_ALIAS>-ext-s3alias' \\"
echo "    --max-keys 10 \\"
echo "    --region ${REGION}"
echo ""
echo "  # ファイルダウンロード"
echo "  aws s3api get-object \\"
echo "    --bucket '<S3_AP_ALIAS>-ext-s3alias' \\"
echo "    --key 'path/to/file.txt' \\"
echo "    --region ${REGION} \\"
echo "    /tmp/downloaded-file.txt"
echo ""

# --- Step 5: Amazon Quick 接続 ---
echo "📝 Step 5: Amazon Quick でデータソース接続"
echo ""
echo "  1. Amazon Quick コンソールにログイン"
echo "  2. Quick Index > Data sources > Add data source"
echo "  3. Amazon S3 を選択"
echo "  4. S3 AP エイリアスをバケット名として指定"
echo "  5. IAM ロールに Step 3 のポリシーが付与されていることを確認"
echo "  6. 同期スケジュールを設定（デモ用: On-demand推奨）"
echo ""
echo "============================================"
echo "  セットアップ手順の出力完了"
echo "============================================"
