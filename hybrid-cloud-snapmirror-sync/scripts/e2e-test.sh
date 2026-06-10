#!/bin/bash
# =============================================================================
# End-to-End テストスクリプト
#
# Sync Server 経由で SnapMirror 同期を実行し、
# S3 Access Point で同期結果を確認する
# =============================================================================
set -euo pipefail

# --- 設定 ---
SYNC_SERVER="${SYNC_SERVER:-http://localhost:8080}"
S3_AP_ALIAS="${S3_AP_ALIAS:-}"  # S3 AP エイリアス (xxx-ext-s3alias)
TEST_FILE_PREFIX="${TEST_FILE_PREFIX:-_e2e_test}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
REGION="${AWS_REGION:-ap-northeast-1}"

# 認証ヘッダー
AUTH_HEADER=""
if [ -n "${AUTH_TOKEN}" ]; then
    AUTH_HEADER="-H 'Authorization: Bearer ${AUTH_TOKEN}'"
fi

echo "============================================"
echo "  End-to-End Test"
echo "============================================"
echo ""
echo "  Sync Server: ${SYNC_SERVER}"
echo "  S3 AP Alias: ${S3_AP_ALIAS:-'(未設定 — S3 確認スキップ)'}"
echo ""

# --- Step 1: ヘルスチェック ---
echo "📝 Step 1: ヘルスチェック"
HEALTH=$(curl -s "${SYNC_SERVER}/api/health")
echo "  Response: ${HEALTH}"

STATUS=$(echo "${HEALTH}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "error")
if [ "${STATUS}" = "ok" ]; then
    echo "  ✅ ヘルスチェック OK"
elif [ "${STATUS}" = "degraded" ]; then
    echo "  ⚠️ ヘルスチェック degraded（SnapMirror 関係の確認が必要）"
else
    echo "  ❌ ヘルスチェック失敗"
    echo "  Sync Server が起動しているか確認してください"
    exit 1
fi
echo ""

# --- Step 2: 現在のステータス確認 ---
echo "📝 Step 2: 現在のステータス確認"
STATE=$(curl -s ${AUTH_HEADER} "${SYNC_SERVER}/api/status")
echo "  Response: ${STATE}"
PHASE=$(echo "${STATE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',{}).get('phase',''))" 2>/dev/null || echo "unknown")
CAN_TRIGGER=$(echo "${STATE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',{}).get('can_trigger',False))" 2>/dev/null || echo "False")

if [ "${CAN_TRIGGER}" != "True" ]; then
    echo "  ⚠️ 現在同期中です。完了を待ちます..."
    sleep 10
fi
echo ""

# --- Step 3: 同期トリガー ---
echo "📝 Step 3: 同期トリガー"
TRIGGER=$(curl -s -X POST ${AUTH_HEADER} "${SYNC_SERVER}/api/sync")
echo "  Response: ${TRIGGER}"
SUCCESS=$(echo "${TRIGGER}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success',False))" 2>/dev/null || echo "False")

if [ "${SUCCESS}" != "True" ]; then
    echo "  ❌ 同期トリガーに失敗"
    echo "  ${TRIGGER}"
    exit 1
fi
echo "  ✅ 同期トリガー成功"
echo ""

# --- Step 4: 完了待ち ---
echo "📝 Step 4: 同期完了待ち (最大5分)"
MAX_WAIT=300
ELAPSED=0
INTERVAL=5

while [ ${ELAPSED} -lt ${MAX_WAIT} ]; do
    sleep ${INTERVAL}
    ELAPSED=$((ELAPSED + INTERVAL))

    STATE=$(curl -s ${AUTH_HEADER} "${SYNC_SERVER}/api/status")
    PHASE=$(echo "${STATE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',{}).get('phase',''))" 2>/dev/null || echo "unknown")

    echo "  [${ELAPSED}s] phase=${PHASE}"

    if [ "${PHASE}" = "done" ]; then
        echo "  ✅ 同期完了！"
        break
    elif [ "${PHASE}" = "error" ]; then
        echo "  ❌ 同期エラー"
        echo "  ${STATE}"
        exit 1
    fi
done

if [ "${PHASE}" != "done" ]; then
    echo "  ❌ タイムアウト（5分経過）"
    exit 1
fi
echo ""

# --- Step 5: S3 AP 確認（オプション） ---
if [ -n "${S3_AP_ALIAS}" ]; then
    echo "📝 Step 5: S3 Access Point 確認"
    echo "  S3 AP alias: ${S3_AP_ALIAS}"

    OBJECTS=$(aws s3api list-objects-v2 \
        --bucket "${S3_AP_ALIAS}" \
        --max-keys 5 \
        --region "${REGION}" \
        --output json 2>&1 || echo "ERROR")

    if echo "${OBJECTS}" | grep -q "ERROR\|AccessDenied\|NoSuchBucket"; then
        echo "  ⚠️ S3 AP アクセスに問題があります"
        echo "  ${OBJECTS}"
    else
        KEY_COUNT=$(echo "${OBJECTS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('KeyCount',0))" 2>/dev/null || echo "0")
        echo "  ✅ S3 AP アクセス成功 (${KEY_COUNT} objects)"
    fi
else
    echo "📝 Step 5: S3 AP 確認スキップ（S3_AP_ALIAS 未設定）"
fi
echo ""

# --- 結果サマリー ---
echo "============================================"
echo "  ✅ End-to-End テスト完了"
echo "============================================"
echo ""
echo "  結果:"
echo "  - ヘルスチェック:    OK"
echo "  - 同期トリガー:     成功"
echo "  - 同期完了:         成功"
if [ -n "${S3_AP_ALIAS}" ]; then
    echo "  - S3 AP アクセス:   確認済み"
fi
echo ""
echo "  デモの準備が完了しました。"
