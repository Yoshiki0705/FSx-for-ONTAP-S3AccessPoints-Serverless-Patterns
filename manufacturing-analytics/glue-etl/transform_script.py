"""
AWS Glue ETL ジョブ — CSV → Parquet 変換スクリプト

FSx for NetApp ONTAP S3 Access Points 経由で CSV センサーログを読み取り、
Parquet 形式に変換して S3 AP に書き戻す PySpark スクリプト。

AWS 公式チュートリアル「Build ETL pipelines using AWS Glue」準拠:
https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html

使用方法:
  AWS Glue ジョブのスクリプトとして指定する。
  ジョブパラメータで以下を設定:
    --S3_ACCESS_POINT_INPUT: 入力用 S3 AP Alias（例: vol-sensor-xxxxx-ext-s3alias）
    --S3_ACCESS_POINT_OUTPUT: 出力用 S3 AP Alias（例: vol-output-xxxxx-ext-s3alias）
    --INPUT_PREFIX: 入力 CSV のプレフィックス（例: sensor-logs/）
    --OUTPUT_PREFIX: 出力 Parquet のプレフィックス（例: parquet/）
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# =====================================================================
# ジョブパラメータの取得
# =====================================================================
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "S3_ACCESS_POINT_INPUT",
        "S3_ACCESS_POINT_OUTPUT",
        "INPUT_PREFIX",
        "OUTPUT_PREFIX",
    ],
)

s3_ap_input = args["S3_ACCESS_POINT_INPUT"]
s3_ap_output = args["S3_ACCESS_POINT_OUTPUT"]
input_prefix = args["INPUT_PREFIX"]
output_prefix = args["OUTPUT_PREFIX"]

# =====================================================================
# Glue Context / Spark Session 初期化
# =====================================================================
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

logger = glue_context.get_logger()
logger.info(f"Starting Glue ETL job: {args['JOB_NAME']}")
logger.info(f"Input S3 AP: {s3_ap_input}, Prefix: {input_prefix}")
logger.info(f"Output S3 AP: {s3_ap_output}, Prefix: {output_prefix}")

# =====================================================================
# S3 AP パス構築
# FSx ONTAP S3 AP は s3://<alias>/<prefix> 形式でアクセス可能
# IMPORTANT: Glue は internet network origin の S3 AP のみアクセス可能
# =====================================================================
input_path = f"s3://{s3_ap_input}/{input_prefix}"
output_path = f"s3://{s3_ap_output}/{output_prefix}"

logger.info(f"Input path: {input_path}")
logger.info(f"Output path: {output_path}")

# =====================================================================
# センサーログ CSV スキーマ定義
# =====================================================================
sensor_schema = StructType(
    [
        StructField("sensor_id", StringType(), nullable=False),
        StructField("timestamp", StringType(), nullable=False),
        StructField("value", DoubleType(), nullable=True),
        StructField("metric_name", StringType(), nullable=True),
        StructField("unit", StringType(), nullable=True),
    ]
)

# =====================================================================
# Step 1: CSV データの読み取り
# =====================================================================
logger.info("Step 1: Reading CSV sensor logs from S3 Access Point...")

try:
    df_raw = (
        spark.read.format("csv")
        .option("header", "true")
        .option("inferSchema", "false")
        .schema(sensor_schema)
        .load(input_path + "*.csv")
    )

    record_count = df_raw.count()
    logger.info(f"Read {record_count} records from CSV files")
except Exception as e:
    logger.error(f"Failed to read CSV files: {e}")
    job.commit()
    sys.exit(1)

if record_count == 0:
    logger.info("No records found. Exiting.")
    job.commit()
    sys.exit(0)

# =====================================================================
# Step 2: データ変換
# - タイムスタンプ文字列を Timestamp 型に変換
# - NULL 値のフィルタリング
# - パーティションカラム（year, month, day）の追加
# =====================================================================
logger.info("Step 2: Transforming data...")

df_transformed = (
    df_raw
    # NULL の value を除外
    .filter(F.col("value").isNotNull())
    # タイムスタンプを Timestamp 型に変換
    .withColumn("event_timestamp", F.to_timestamp(F.col("timestamp")))
    # パーティションカラムの追加
    .withColumn("year", F.year(F.col("event_timestamp")))
    .withColumn("month", F.month(F.col("event_timestamp")))
    .withColumn("day", F.dayofmonth(F.col("event_timestamp")))
    # 元の timestamp 文字列カラムを削除
    .drop("timestamp")
)

transformed_count = df_transformed.count()
logger.info(f"Transformed {transformed_count} records (filtered {record_count - transformed_count} NULL values)")

# =====================================================================
# Step 3: Parquet 形式で書き出し
# - Snappy 圧縮
# - year/month/day パーティション
# - 上書きモード
# =====================================================================
logger.info("Step 3: Writing Parquet to S3 Access Point...")

try:
    (
        df_transformed.write.format("parquet")
        .mode("overwrite")
        .option("compression", "snappy")
        .partitionBy("year", "month", "day")
        .save(output_path)
    )
    logger.info(f"Successfully wrote Parquet to {output_path}")
except Exception as e:
    logger.error(f"Failed to write Parquet: {e}")
    job.commit()
    sys.exit(1)

# =====================================================================
# ジョブ完了
# =====================================================================
logger.info(
    f"Glue ETL job completed. "
    f"Input records: {record_count}, "
    f"Output records: {transformed_count}"
)
job.commit()
