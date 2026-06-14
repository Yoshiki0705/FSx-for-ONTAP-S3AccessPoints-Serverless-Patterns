#!/bin/bash
# =============================================================================
# FSx for ONTAP SMB/CIFS Share Mount Script
# =============================================================================
#
# FSx for ONTAP ボリュームを SMB/CIFS プロトコルでマウントする。
# Active Directory 参加済み / 非参加の両パターンに対応。
#
# ユースケース:
#   - Windows ファイルサーバー移行: オンプレ CIFS 共有を FSx ONTAP に移行後、
#     Linux/Windows クライアントから SMB アクセス
#   - マルチプロトコルアクセス: 同一ボリュームに NFS (Linux) + SMB (Windows) で
#     同時アクセス（NTFS セキュリティスタイル推奨）
#   - VDI/仮想デスクトップ: Windows デスクトップからのプロファイル・ホームディレクトリ
#   - SAP/ERP: Windows アプリケーションサーバーからの共有ストレージ
#   - DevOps: FlexClone ボリュームを SMB 経由で開発環境に提供
#
# 前提条件:
#   - Linux: cifs-utils パッケージがインストール済み
#     (Amazon Linux 2023: sudo yum install -y cifs-utils)
#     (Ubuntu: sudo apt-get install -y cifs-utils)
#   - Windows: net use コマンドが利用可能（標準搭載）
#   - SVM に CIFS サーバーが設定済み（AD 参加 or ワークグループ）
#   - CIFS 共有が作成済み（未作成の場合は本スクリプトで作成可能）
#   - TCP 445 ポートが開放済み
#
# 参考:
#   - AWS Docs: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/attach-windows-client.html
#   - AWS rePost: https://repost.aws/knowledge-center/ec2-mount-fsx-ontap-cifs
#   - NetApp Docs: https://docs.netapp.com/us-en/ontap/smb-config/index.html
#
# 必須環境変数:
#   SMB_SERVER          - SVM の SMB DNS 名または IP アドレス
#   SMB_SHARE           - CIFS 共有名
#   SMB_USER            - 認証ユーザー名 (AD ユーザー or ローカルユーザー)
#   SMB_PASSWORD        - 認証パスワード
#
# オプション環境変数:
#   SMB_DOMAIN          - Active Directory ドメイン名 (default: "")
#   MOUNT_POINT         - マウントポイント (default: /mnt/fsxn/smb/{SMB_SHARE})
#   SMB_VERSION         - SMB プロトコルバージョン: 2.1|3.0|3.1.1 (default: 3.0)
#   SMB_SEC             - セキュリティモード: ntlmsspi|krb5|krb5i (default: ntlmsspi)
#   CREDENTIALS_FILE    - 認証情報ファイルパス (パスワード直接指定の代替)
#   RSIZE               - 読み取りバッファサイズ (default: 130048)
#   WSIZE               - 書き込みバッファサイズ (default: 130048)
#   CACHE_MODE          - キャッシュモード: none|strict|loose (default: strict)
#   PERSISTENT_MOUNT    - /etc/fstab に追加: true|false (default: false)
#   CREATE_SHARE        - CIFS 共有を作成: true|false (default: false)
#   ONTAP_MGMT_IP       - ONTAP 管理 IP (CREATE_SHARE=true 時に必要)
#   ONTAP_USER          - ONTAP 管理ユーザー (default: fsxadmin)
#   ONTAP_PASSWORD      - ONTAP 管理パスワード
#   SVM_NAME            - SVM 名 (CREATE_SHARE=true 時に必要)
#   VOLUME_JUNCTION     - ボリュームジャンクションパス (CREATE_SHARE=true 時に必要)
#
# 使用方法:
#   # パターン 1: 既存 CIFS 共有をマウント（AD 参加済み Linux）
#   export SMB_SERVER=svm1.corp.example.com
#   export SMB_SHARE=project_data
#   export SMB_USER=admin@CORP.EXAMPLE.COM
#   export SMB_PASSWORD=MyPassword123
#   export SMB_DOMAIN=CORP.EXAMPLE.COM
#   ./scripts/mount_smb_share.sh
#
#   # パターン 2: 認証情報ファイルを使用（セキュリティ強化）
#   echo -e "username=admin\npassword=MyPassword123\ndomain=CORP.EXAMPLE.COM" > ~/.smb_creds
#   chmod 600 ~/.smb_creds
#   export SMB_SERVER=10.0.128.50
#   export SMB_SHARE=project_data
#   export CREDENTIALS_FILE=~/.smb_creds
#   ./scripts/mount_smb_share.sh
#
#   # パターン 3: CIFS 共有作成 + マウント（FlexClone 後の新規共有）
#   export SMB_SERVER=10.0.128.50
#   export SMB_SHARE=clone_vol1_dev
#   export SMB_USER=admin
#   export SMB_PASSWORD=MyPassword123
#   export CREATE_SHARE=true
#   export ONTAP_MGMT_IP=10.0.128.50
#   export ONTAP_USER=fsxadmin
#   export ONTAP_PASSWORD=OntapAdminPass
#   export SVM_NAME=FSxN_OnPre
#   export VOLUME_JUNCTION=/clone_vol1_dev
#   ./scripts/mount_smb_share.sh
#
#   # パターン 4: Windows クライアント（PowerShell）
#   # net use Z: \\svm1.corp.example.com\project_data /user:CORP\admin MyPassword123
#   # または:
#   # New-PSDrive -Name Z -PSProvider FileSystem -Root \\svm1.corp.example.com\project_data -Credential (Get-Credential)
#
# =============================================================================

set -euo pipefail

# --- Configuration ---
SMB_SERVER="${SMB_SERVER:?'Set SMB_SERVER env var (SVM SMB DNS name or IP)'}"
SMB_SHARE="${SMB_SHARE:?'Set SMB_SHARE env var (CIFS share name)'}"
SMB_USER="${SMB_USER:-}"
SMB_PASSWORD="${SMB_PASSWORD:-}"
SMB_DOMAIN="${SMB_DOMAIN:-}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/fsxn/smb/${SMB_SHARE}}"
SMB_VERSION="${SMB_VERSION:-3.0}"
SMB_SEC="${SMB_SEC:-ntlmsspi}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-}"
RSIZE="${RSIZE:-130048}"
WSIZE="${WSIZE:-130048}"
CACHE_MODE="${CACHE_MODE:-strict}"
PERSISTENT_MOUNT="${PERSISTENT_MOUNT:-false}"
CREATE_SHARE="${CREATE_SHARE:-false}"
ONTAP_MGMT_IP="${ONTAP_MGMT_IP:-}"
ONTAP_USER="${ONTAP_USER:-fsxadmin}"
ONTAP_PASSWORD="${ONTAP_PASSWORD:-}"
SVM_NAME="${SVM_NAME:-}"
VOLUME_JUNCTION="${VOLUME_JUNCTION:-}"

echo "============================================================"
echo "FSx for ONTAP SMB/CIFS Mount"
echo "============================================================"
echo "SMB Server: $SMB_SERVER"
echo "Share Name: $SMB_SHARE"
echo "Mount Point: $MOUNT_POINT"
echo "SMB Version: $SMB_VERSION"
echo "Security: $SMB_SEC"
echo "Cache Mode: $CACHE_MODE"
echo "============================================================"
echo ""

# --- Step 0: Create CIFS share if requested ---
if [ "$CREATE_SHARE" = "true" ]; then
    echo "▶ Step 0: Creating CIFS share on ONTAP..."
    if [ -z "$ONTAP_MGMT_IP" ] || [ -z "$SVM_NAME" ] || [ -z "$VOLUME_JUNCTION" ]; then
        echo "  ❌ ERROR: CREATE_SHARE=true requires ONTAP_MGMT_IP, SVM_NAME, VOLUME_JUNCTION"
        exit 1
    fi

    # Create CIFS share via ONTAP REST API
    SHARE_BODY=$(cat <<EOF
{
    "name": "${SMB_SHARE}",
    "path": "${VOLUME_JUNCTION}",
    "svm": {"name": "${SVM_NAME}"},
    "comment": "Created by mount_smb_share.sh",
    "oplocks": true,
    "browsable": true,
    "change_notify": true,
    "show_previous_versions": true
}
EOF
)
    SHARE_RESPONSE=$(curl -s -k \
        -u "${ONTAP_USER}:${ONTAP_PASSWORD}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -X POST \
        -d "$SHARE_BODY" \
        "https://${ONTAP_MGMT_IP}/api/protocols/cifs/shares")

    SHARE_ERROR=$(echo "$SHARE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('error',{}).get('message',''))" 2>/dev/null || echo "")
    if [ -n "$SHARE_ERROR" ] && [[ "$SHARE_ERROR" != *"already exists"* ]]; then
        echo "  ❌ ERROR: CIFS share creation failed: $SHARE_ERROR"
        exit 1
    elif [[ "$SHARE_ERROR" == *"already exists"* ]]; then
        echo "  ℹ️  CIFS share '$SMB_SHARE' already exists (continuing)"
    else
        echo "  ✅ CIFS share created: $SMB_SHARE → $VOLUME_JUNCTION"
    fi
    echo ""
fi

# --- Step 1: Check prerequisites ---
echo "▶ Step 1: Checking prerequisites..."

# Check if cifs-utils is installed
if ! command -v mount.cifs &>/dev/null; then
    echo "  ⚠️  cifs-utils not installed. Installing..."
    if command -v yum &>/dev/null; then
        sudo yum install -y cifs-utils
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y cifs-utils
    else
        echo "  ❌ ERROR: Cannot install cifs-utils. Please install manually."
        exit 1
    fi
fi
echo "  ✅ cifs-utils available"

# Check connectivity
if timeout 5 bash -c "echo >/dev/tcp/${SMB_SERVER}/445" 2>/dev/null; then
    echo "  ✅ TCP 445 connectivity to $SMB_SERVER confirmed"
else
    echo "  ❌ ERROR: Cannot connect to $SMB_SERVER on TCP 445"
    echo "     Check security group rules and network connectivity"
    exit 1
fi
echo ""

# --- Step 2: Prepare credentials ---
echo "▶ Step 2: Preparing credentials..."
if [ -n "$CREDENTIALS_FILE" ]; then
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        echo "  ❌ ERROR: Credentials file not found: $CREDENTIALS_FILE"
        exit 1
    fi
    CRED_OPTION="credentials=${CREDENTIALS_FILE}"
    echo "  ✅ Using credentials file: $CREDENTIALS_FILE"
else
    if [ -z "$SMB_USER" ] || [ -z "$SMB_PASSWORD" ]; then
        echo "  ❌ ERROR: Set SMB_USER + SMB_PASSWORD or CREDENTIALS_FILE"
        exit 1
    fi
    # Create temporary credentials file (more secure than command-line password)
    TEMP_CREDS=$(mktemp /tmp/.smb_creds_XXXXXX)
    echo "username=${SMB_USER}" > "$TEMP_CREDS"
    echo "password=${SMB_PASSWORD}" >> "$TEMP_CREDS"
    [ -n "$SMB_DOMAIN" ] && echo "domain=${SMB_DOMAIN}" >> "$TEMP_CREDS"
    chmod 600 "$TEMP_CREDS"
    CRED_OPTION="credentials=${TEMP_CREDS}"
    echo "  ✅ Temporary credentials file created"
    # Cleanup on exit
    trap "rm -f $TEMP_CREDS" EXIT
fi
echo ""

# --- Step 3: Create mount point ---
echo "▶ Step 3: Creating mount point..."
sudo mkdir -p "$MOUNT_POINT"
echo "  ✅ Mount point: $MOUNT_POINT"
echo ""

# --- Step 4: Mount the CIFS share ---
echo "▶ Step 4: Mounting CIFS share..."
MOUNT_OPTIONS="sec=${SMB_SEC},${CRED_OPTION},vers=${SMB_VERSION},rsize=${RSIZE},wsize=${WSIZE},cache=${CACHE_MODE}"

echo "  Command: sudo mount -t cifs //${SMB_SERVER}/${SMB_SHARE} ${MOUNT_POINT}"
echo "  Options: sec=${SMB_SEC},vers=${SMB_VERSION},rsize=${RSIZE},wsize=${WSIZE},cache=${CACHE_MODE}"

if sudo mount -t cifs "//${SMB_SERVER}/${SMB_SHARE}" "$MOUNT_POINT" -o "$MOUNT_OPTIONS"; then
    echo "  ✅ SMB mount successful!"
    echo ""
    echo "  Mount details:"
    mount | grep "$MOUNT_POINT" | sed 's/^/     /'
    echo ""
    echo "  Filesystem usage:"
    df -h "$MOUNT_POINT" | tail -1 | awk '{printf "     Size: %s  Used: %s  Avail: %s  Use%%: %s\n", $2, $3, $4, $5}'
    echo ""

    # Test write access
    TEST_FILE="${MOUNT_POINT}/.smb_mount_test_$(date +%s)"
    if touch "$TEST_FILE" 2>/dev/null; then
        rm -f "$TEST_FILE"
        echo "  ✅ Write access confirmed"
    else
        echo "  ⚠️  Read-only access (write test failed)"
    fi
else
    echo "  ❌ Mount failed!"
    echo ""
    echo "  Troubleshooting steps:"
    echo "  1. Verify connectivity: telnet $SMB_SERVER 445"
    echo "  2. Verify credentials: smbclient //${SMB_SERVER}/${SMB_SHARE} -U ${SMB_USER:-<user>}"
    echo "  3. Check CIFS share exists: vserver cifs share show -vserver ${SVM_NAME:-<svm>}"
    echo "  4. Check security style: volume show -volume <vol> -fields security-style"
    echo "  5. Check verbose mount: sudo mount -t cifs //${SMB_SERVER}/${SMB_SHARE} ${MOUNT_POINT} --verbose -o ${MOUNT_OPTIONS}"
    echo "  6. Check kernel logs: dmesg | grep -i cifs"
    exit 1
fi
echo ""

# --- Step 5: Persistent mount (optional) ---
if [ "$PERSISTENT_MOUNT" = "true" ]; then
    echo "▶ Step 5: Adding to /etc/fstab for persistent mount..."
    FSTAB_ENTRY="//${SMB_SERVER}/${SMB_SHARE} ${MOUNT_POINT} cifs sec=${SMB_SEC},_netdev,auto,x-systemd.automount,x-systemd.requires=network-online.target,${CRED_OPTION},rsize=${RSIZE},wsize=${WSIZE},cache=${CACHE_MODE},vers=${SMB_VERSION} 0 0"

    if grep -q "${SMB_SERVER}/${SMB_SHARE}" /etc/fstab 2>/dev/null; then
        echo "  ℹ️  Entry already exists in /etc/fstab"
    else
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab > /dev/null
        echo "  ✅ Added to /etc/fstab"
        echo "     Note: Ensure credentials file is persistent (not /tmp)"
    fi
    echo ""
fi

# --- Summary ---
echo "============================================================"
echo "SMB Mount Summary"
echo "============================================================"
echo ""
echo "Server:       $SMB_SERVER"
echo "Share:        $SMB_SHARE"
echo "Mount Point:  $MOUNT_POINT"
echo "Protocol:     SMB $SMB_VERSION"
echo "Security:     $SMB_SEC"
echo "Domain:       ${SMB_DOMAIN:-<none>}"
echo "Persistent:   $PERSISTENT_MOUNT"
echo ""
echo "Windows equivalent commands:"
echo "  # Command Prompt"
echo "  net use Z: \\\\${SMB_SERVER}\\${SMB_SHARE} /user:${SMB_DOMAIN:+${SMB_DOMAIN}\\}${SMB_USER:-<user>}"
echo ""
echo "  # PowerShell"
echo "  New-PSDrive -Name Z -PSProvider FileSystem -Root \\\\${SMB_SERVER}\\${SMB_SHARE} -Persist"
echo ""
echo "  # PowerShell with credentials"
echo '  $cred = Get-Credential'
echo "  New-PSDrive -Name Z -PSProvider FileSystem -Root \\\\${SMB_SERVER}\\${SMB_SHARE} -Credential \$cred -Persist"
echo ""
echo "Unmount command:"
echo "  sudo umount $MOUNT_POINT"
echo ""
echo "ONTAP CIFS share management:"
echo "  # List shares"
echo "  vserver cifs share show -vserver ${SVM_NAME:-<svm>}"
echo "  # Show share properties"
echo "  vserver cifs share properties show -vserver ${SVM_NAME:-<svm>} -share-name ${SMB_SHARE}"
echo "  # Show connected sessions"
echo "  vserver cifs session show -vserver ${SVM_NAME:-<svm>}"
echo "============================================================"
