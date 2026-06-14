#!/bin/bash
# =============================================================================
# FlexClone Volume Creation and Multi-Protocol Mount Script
# =============================================================================
#
# FSx for ONTAP FlexClone ボリュームを作成し、NFSv3/NFSv4.1/SMB でマウントする。
#
# ユースケース:
#   - EDA/半導体設計: 大規模シミュレーションデータのスナップショットから
#     テスト環境を瞬時に作成（数TB のデータを秒単位でクローン）
#   - DevOps/CI/CD: 本番データベースのクローンを開発・テスト環境に提供
#     （Oracle, SAP HANA, PostgreSQL のリフレッシュサイクル高速化）
#   - VDI/仮想デスクトップ: ゴールデンイメージからの即時プロビジョニング
#   - 医療/ゲノミクス: 研究データセットの分岐コピーを各研究者に提供
#   - 金融/コンプライアンス: 監査用のポイントインタイムコピー作成
#
# FlexClone の特徴:
#   - 瞬時作成（データコピー不要、メタデータのみ）
#   - スペース効率（書き込み時のみ追加容量消費）
#   - 読み書き可能（本番データに影響なし）
#   - Snapshot ベース（任意の時点からクローン可能）
#
# 参考:
#   - AWS Blog: https://aws.amazon.com/blogs/storage/accelerate-development-refresh-cycles-and-optimize-cost-with-amazon-fsx-for-netapp-ontap-cloning
#   - NetApp Docs: https://docs.netapp.com/us-en/ontap/volumes/create-flexclone-task.html
#   - ONTAP REST API: POST /api/storage/volumes (with clone.parent_volume)
#
# 必須環境変数:
#   ONTAP_MGMT_IP       - ONTAP SVM 管理 IP アドレス
#   ONTAP_USER          - ONTAP 管理ユーザー (default: fsxadmin)
#   ONTAP_PASSWORD      - ONTAP 管理パスワード (or use SECRET_NAME for Secrets Manager)
#   SVM_NAME            - Storage Virtual Machine 名
#   PARENT_VOLUME       - クローン元の親ボリューム名
#   CLONE_NAME          - 作成するクローンボリューム名
#
# オプション環境変数:
#   SECRET_NAME         - Secrets Manager シークレット名 (ONTAP_PASSWORD の代替)
#   SNAPSHOT_NAME       - 特定の Snapshot からクローン (省略時は最新状態)
#   JUNCTION_PATH       - クローンのジャンクションパス (default: /{CLONE_NAME})
#   MOUNT_POINT_BASE    - マウントポイントのベースディレクトリ (default: /mnt/fsxn)
#   NFS_SERVER          - NFS マウント用サーバーアドレス (default: ONTAP_MGMT_IP)
#   SMB_SERVER          - SMB マウント用サーバーアドレス
#   SMB_USER            - SMB 認証ユーザー
#   SMB_PASSWORD        - SMB 認証パスワード
#   SECURITY_STYLE      - ボリュームセキュリティスタイル: unix|ntfs|mixed (default: unix)
#
# 使用方法:
#   # 基本的な FlexClone 作成 + NFS マウント
#   export ONTAP_MGMT_IP=10.0.128.50
#   export SECRET_NAME=fsx-ontap-fsxadmin-credentials
#   export SVM_NAME=FSxN_OnPre
#   export PARENT_VOLUME=vol1
#   export CLONE_NAME=vol1_clone_test
#   ./scripts/create_flexclone_and_mount.sh
#
#   # Snapshot 指定でクローン作成
#   export SNAPSHOT_NAME=daily_backup_20260518
#   ./scripts/create_flexclone_and_mount.sh
#
# =============================================================================

set -euo pipefail

# --- Configuration ---
ONTAP_MGMT_IP="${ONTAP_MGMT_IP:?'Set ONTAP_MGMT_IP env var'}"
ONTAP_USER="${ONTAP_USER:-fsxadmin}"
SVM_NAME="${SVM_NAME:?'Set SVM_NAME env var'}"
PARENT_VOLUME="${PARENT_VOLUME:?'Set PARENT_VOLUME env var'}"
CLONE_NAME="${CLONE_NAME:?'Set CLONE_NAME env var'}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-}"
JUNCTION_PATH="${JUNCTION_PATH:-/${CLONE_NAME}}"
MOUNT_POINT_BASE="${MOUNT_POINT_BASE:-/mnt/fsxn}"
NFS_SERVER="${NFS_SERVER:-${ONTAP_MGMT_IP}}"
SMB_SERVER="${SMB_SERVER:-}"
SMB_USER="${SMB_USER:-}"
SMB_PASSWORD="${SMB_PASSWORD:-}"
SECURITY_STYLE="${SECURITY_STYLE:-unix}"
SECRET_NAME="${SECRET_NAME:-}"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"

# --- Resolve ONTAP password ---
if [ -n "$SECRET_NAME" ]; then
    echo "▶ Retrieving ONTAP credentials from Secrets Manager: $SECRET_NAME"
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id "$SECRET_NAME" \
        --region "$REGION" \
        --query SecretString --output text)
    ONTAP_PASSWORD=$(echo "$SECRET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('password', d.get('ontap_password', '')))")
    ONTAP_USER=$(echo "$SECRET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('username', d.get('ontap_user', 'fsxadmin')))")
    echo "  ✅ Credentials retrieved (user: $ONTAP_USER)"
elif [ -z "${ONTAP_PASSWORD:-}" ]; then
    echo "ERROR: Set either SECRET_NAME or ONTAP_PASSWORD env var"
    exit 1
fi

# --- Helper: ONTAP REST API call ---
ontap_api() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local url="https://${ONTAP_MGMT_IP}/api${endpoint}"
    local args=(
        -s -k
        -u "${ONTAP_USER}:${ONTAP_PASSWORD}"
        -H "Content-Type: application/json"
        -H "Accept: application/json"
        -X "$method"
    )
    if [ -n "$data" ]; then
        args+=(-d "$data")
    fi

    curl "${args[@]}" "$url"
}

echo "============================================================"
echo "FlexClone Volume Creation and Multi-Protocol Mount"
echo "============================================================"
echo "ONTAP Management IP: $ONTAP_MGMT_IP"
echo "SVM: $SVM_NAME"
echo "Parent Volume: $PARENT_VOLUME"
echo "Clone Name: $CLONE_NAME"
echo "Junction Path: $JUNCTION_PATH"
echo "Snapshot: ${SNAPSHOT_NAME:-<latest state>}"
echo "Security Style: $SECURITY_STYLE"
echo "============================================================"
echo ""

# --- Step 1: Get SVM UUID ---
echo "▶ Step 1: Resolving SVM UUID for '$SVM_NAME'..."
SVM_RESPONSE=$(ontap_api GET "/svm/svms?name=${SVM_NAME}&fields=uuid")
SVM_UUID=$(echo "$SVM_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['records'][0]['uuid'])" 2>/dev/null)
if [ -z "$SVM_UUID" ]; then
    echo "  ❌ ERROR: SVM '$SVM_NAME' not found"
    exit 1
fi
echo "  ✅ SVM UUID: $SVM_UUID"

# --- Step 2: Get Parent Volume UUID ---
echo "▶ Step 2: Resolving parent volume UUID for '$PARENT_VOLUME'..."
VOL_RESPONSE=$(ontap_api GET "/storage/volumes?name=${PARENT_VOLUME}&svm.uuid=${SVM_UUID}&fields=uuid,nas.path")
PARENT_UUID=$(echo "$VOL_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['records'][0]['uuid'])" 2>/dev/null)
if [ -z "$PARENT_UUID" ]; then
    echo "  ❌ ERROR: Parent volume '$PARENT_VOLUME' not found in SVM '$SVM_NAME'"
    exit 1
fi
echo "  ✅ Parent Volume UUID: $PARENT_UUID"

# --- Step 3: Create Snapshot (if not specified) ---
if [ -z "$SNAPSHOT_NAME" ]; then
    SNAPSHOT_NAME="${CLONE_NAME}_base_$(date +%Y%m%d_%H%M%S)"
    echo "▶ Step 3: Creating base snapshot '$SNAPSHOT_NAME'..."
    SNAP_BODY=$(cat <<EOF
{
    "name": "${SNAPSHOT_NAME}",
    "comment": "Base snapshot for FlexClone ${CLONE_NAME}"
}
EOF
)
    SNAP_RESPONSE=$(ontap_api POST "/storage/volumes/${PARENT_UUID}/snapshots" "$SNAP_BODY")
    echo "  ✅ Snapshot created: $SNAPSHOT_NAME"
else
    echo "▶ Step 3: Using existing snapshot '$SNAPSHOT_NAME'"
fi

# --- Step 4: Create FlexClone Volume ---
echo "▶ Step 4: Creating FlexClone volume '$CLONE_NAME'..."
CLONE_BODY=$(cat <<EOF
{
    "name": "${CLONE_NAME}",
    "svm": {"uuid": "${SVM_UUID}"},
    "clone": {
        "parent_volume": {"uuid": "${PARENT_UUID}"},
        "parent_snapshot": {"name": "${SNAPSHOT_NAME}"},
        "is_flexclone": true
    },
    "nas": {
        "path": "${JUNCTION_PATH}",
        "security_style": "${SECURITY_STYLE}"
    }
}
EOF
)
CLONE_RESPONSE=$(ontap_api POST "/storage/volumes" "$CLONE_BODY")

# Check for errors
CLONE_ERROR=$(echo "$CLONE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('error',{}).get('message',''))" 2>/dev/null || echo "")
if [ -n "$CLONE_ERROR" ]; then
    echo "  ❌ ERROR: FlexClone creation failed: $CLONE_ERROR"
    exit 1
fi

CLONE_UUID=$(echo "$CLONE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('uuid', r.get('records',[{}])[0].get('uuid','')))" 2>/dev/null || echo "")
echo "  ✅ FlexClone created: $CLONE_NAME (UUID: ${CLONE_UUID:-pending})"
echo "     - Parent: $PARENT_VOLUME"
echo "     - Snapshot: $SNAPSHOT_NAME"
echo "     - Junction: $JUNCTION_PATH"
echo "     - Space-efficient: yes (copy-on-write)"
echo ""

# --- Step 5: Wait for volume to be online ---
echo "▶ Step 5: Waiting for FlexClone to come online..."
for i in $(seq 1 30); do
    VOL_STATE=$(ontap_api GET "/storage/volumes?name=${CLONE_NAME}&svm.uuid=${SVM_UUID}&fields=state" | \
        python3 -c "import sys,json; r=json.load(sys.stdin); print(r['records'][0]['state'])" 2>/dev/null || echo "unknown")
    if [ "$VOL_STATE" = "online" ]; then
        echo "  ✅ Volume is online"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ⚠️  Timeout waiting for volume to come online (state: $VOL_STATE)"
        break
    fi
    sleep 2
done
echo ""

# --- Step 6: Mount via NFSv3 ---
echo "▶ Step 6: Mounting via NFSv3..."
MOUNT_NFSv3="${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv3"
sudo mkdir -p "$MOUNT_NFSv3"
if sudo mount -t nfs -o vers=3,hard,timeo=600,retrans=2 \
    "${NFS_SERVER}:${JUNCTION_PATH}" "$MOUNT_NFSv3" 2>/dev/null; then
    echo "  ✅ NFSv3 mounted: $MOUNT_NFSv3"
    echo "     mount -t nfs -o vers=3 ${NFS_SERVER}:${JUNCTION_PATH} $MOUNT_NFSv3"
    df -h "$MOUNT_NFSv3" 2>/dev/null | tail -1 | awk '{print "     Size:", $2, "Used:", $3, "Avail:", $4}'
else
    echo "  ⚠️  NFSv3 mount failed (NFS client may not be installed or network unreachable)"
    echo "     Manual command: sudo mount -t nfs -o vers=3 ${NFS_SERVER}:${JUNCTION_PATH} $MOUNT_NFSv3"
fi
echo ""

# --- Step 7: Mount via NFSv4.1 ---
echo "▶ Step 7: Mounting via NFSv4.1..."
MOUNT_NFSv4="${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv4"
sudo mkdir -p "$MOUNT_NFSv4"
if sudo mount -t nfs -o vers=4.1,hard,timeo=600,retrans=2 \
    "${NFS_SERVER}:${JUNCTION_PATH}" "$MOUNT_NFSv4" 2>/dev/null; then
    echo "  ✅ NFSv4.1 mounted: $MOUNT_NFSv4"
    echo "     mount -t nfs -o vers=4.1 ${NFS_SERVER}:${JUNCTION_PATH} $MOUNT_NFSv4"
    df -h "$MOUNT_NFSv4" 2>/dev/null | tail -1 | awk '{print "     Size:", $2, "Used:", $3, "Avail:", $4}'
else
    echo "  ⚠️  NFSv4.1 mount failed (NFSv4 may not be enabled on SVM or network unreachable)"
    echo "     Manual command: sudo mount -t nfs -o vers=4.1 ${NFS_SERVER}:${JUNCTION_PATH} $MOUNT_NFSv4"
fi
echo ""

# --- Step 8: Mount via SMB/CIFS ---
echo "▶ Step 8: Mounting via SMB/CIFS..."
if [ -n "$SMB_SERVER" ] && [ -n "$SMB_USER" ]; then
    MOUNT_SMB="${MOUNT_POINT_BASE}/${CLONE_NAME}/smb"
    SMB_SHARE="${CLONE_NAME}"
    sudo mkdir -p "$MOUNT_SMB"
    if sudo mount -t cifs "//${SMB_SERVER}/${SMB_SHARE}" "$MOUNT_SMB" \
        -o "username=${SMB_USER},password=${SMB_PASSWORD},vers=3.0" 2>/dev/null; then
        echo "  ✅ SMB mounted: $MOUNT_SMB"
        echo "     mount -t cifs //${SMB_SERVER}/${SMB_SHARE} $MOUNT_SMB"
        df -h "$MOUNT_SMB" 2>/dev/null | tail -1 | awk '{print "     Size:", $2, "Used:", $3, "Avail:", $4}'
    else
        echo "  ⚠️  SMB mount failed (CIFS share may need to be created or cifs-utils not installed)"
        echo "     Manual command: sudo mount -t cifs //${SMB_SERVER}/${SMB_SHARE} $MOUNT_SMB -o username=${SMB_USER}"
        echo ""
        echo "     Note: SMB/CIFS share must be created separately on the SVM:"
        echo "     cifs share create -vserver ${SVM_NAME} -share-name ${SMB_SHARE} -path ${JUNCTION_PATH}"
    fi
else
    echo "  ⏭️  Skipped (SMB_SERVER and SMB_USER not set)"
    echo "     To mount via SMB, set: SMB_SERVER, SMB_USER, SMB_PASSWORD"
    echo "     Also ensure CIFS share exists: cifs share create -vserver ${SVM_NAME} -share-name ${CLONE_NAME} -path ${JUNCTION_PATH}"
fi
echo ""

# --- Summary ---
echo "============================================================"
echo "FlexClone Summary"
echo "============================================================"
echo ""
echo "Clone Volume:    $CLONE_NAME"
echo "Parent Volume:   $PARENT_VOLUME"
echo "Base Snapshot:   $SNAPSHOT_NAME"
echo "Junction Path:   $JUNCTION_PATH"
echo "Security Style:  $SECURITY_STYLE"
echo ""
echo "Mount Points:"
echo "  NFSv3:  ${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv3"
echo "  NFSv4:  ${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv4"
[ -n "$SMB_SERVER" ] && echo "  SMB:    ${MOUNT_POINT_BASE}/${CLONE_NAME}/smb"
echo ""
echo "Industry Use Cases for FlexClone:"
echo "  • EDA/Semiconductor: Clone design libraries for parallel simulation runs"
echo "  • DevOps/Database: Instant dev/test refresh from production snapshots"
echo "  • Healthcare/Genomics: Branch research datasets per study"
echo "  • Financial Services: Point-in-time audit copies"
echo "  • Manufacturing/CAE: Clone CAD/simulation data for engineering teams"
echo ""
echo "Cleanup Commands:"
echo "  # Unmount"
echo "  sudo umount ${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv3"
echo "  sudo umount ${MOUNT_POINT_BASE}/${CLONE_NAME}/nfsv4"
[ -n "$SMB_SERVER" ] && echo "  sudo umount ${MOUNT_POINT_BASE}/${CLONE_NAME}/smb"
echo ""
echo "  # Delete FlexClone (ONTAP CLI)"
echo "  volume unmount -vserver ${SVM_NAME} -volume ${CLONE_NAME}"
echo "  volume offline -vserver ${SVM_NAME} -volume ${CLONE_NAME}"
echo "  volume delete -vserver ${SVM_NAME} -volume ${CLONE_NAME}"
echo ""
echo "  # Or split clone into independent volume (no longer space-efficient)"
echo "  volume clone split start -vserver ${SVM_NAME} -flexclone ${CLONE_NAME}"
echo "============================================================"
