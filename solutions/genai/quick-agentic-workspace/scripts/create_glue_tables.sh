#!/usr/bin/env bash
# UC30: Quick Sight / Athena 用 Glue テーブル作成スクリプト
#
# analytics/<role>/ の CSV を指す外部テーブルを作成する。
# 使い方:
#   ./create_glue_tables.sh <S3AP_ALIAS> [WORKGROUP] [DATABASE]
#
# 前提:
#   - aws CLI v2 / 認証情報
#   - Lake Formation 利用環境では、実行プリンシパルに DB/テーブルの権限が必要
#
# 注意: LOCATION は S3 AP エイリアスを s3://<alias>/... 形式で指定する。
set -euo pipefail

ALIAS="${1:?S3AP alias required}"
WG="${2:-quick-workspace-wg}"
DB="${3:-quick_workspace_db}"
REGION="${AWS_REGION:-ap-northeast-1}"

run_ddl() {
  local sql="$1"
  local qid
  qid=$(aws athena start-query-execution \
    --query-string "$sql" \
    --work-group "$WG" \
    --query-execution-context Database="$DB" \
    --region "$REGION" \
    --query QueryExecutionId --output text)
  echo "  query: $qid"
  for _ in $(seq 1 20); do
    local state
    state=$(aws athena get-query-execution --query-execution-id "$qid" --region "$REGION" \
      --query 'QueryExecution.Status.State' --output text)
    [ "$state" = "SUCCEEDED" ] && { echo "  -> SUCCEEDED"; return 0; }
    [ "$state" = "FAILED" ] || [ "$state" = "CANCELLED" ] && {
      aws athena get-query-execution --query-execution-id "$qid" --region "$REGION" \
        --query 'QueryExecution.Status.StateChangeReason' --output text
      return 1
    }
    sleep 3
  done
}

echo "Creating sales_pipeline ..."
run_ddl "CREATE EXTERNAL TABLE IF NOT EXISTS ${DB}.sales_pipeline (
  deal_id string, stage string, amount_jpy bigint, owner string
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
LOCATION 's3://${ALIAS}/quick-workspace/analytics/sales/'
TBLPROPERTIES ('skip.header.line.count'='1')"

echo "Creating it_incidents ..."
run_ddl "CREATE EXTERNAL TABLE IF NOT EXISTS ${DB}.it_incidents (
  incident_id string, severity string, mttr_minutes int, opened_at string
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
LOCATION 's3://${ALIAS}/quick-workspace/analytics/information-technology/'
TBLPROPERTIES ('skip.header.line.count'='1')"

echo "Done. (他ロールの analytics CSV も同様に追加可能)"

# --- パフォーマンス/コスト最適化（推奨） ---
# 大規模データでは CSV を Parquet に変換し、scanned 量を削減する（Athena は scanned 課金）。
# 例（CTAS で Parquet 化）:
#   CREATE TABLE ${DB}.sales_pipeline_parquet
#   WITH (format='PARQUET', external_location='s3://<results-bucket>/curated/sales_pipeline/')
#   AS SELECT * FROM ${DB}.sales_pipeline;
# さらにロール/日付でパーティション化すると selective scan が可能:
#   WITH (format='PARQUET', partitioned_by=ARRAY['role'], ...)
