"""EMR Serverless Spark ジョブ: CSV → Parquet 変換

FSx ONTAP S3 Access Point 経由で CSV センサーログを読み取り、
Parquet 形式に変換して書き戻す。

参考:
- EMR Serverless Getting Started: https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/getting-started.html
- FSx ONTAP S3 AP + Glue ETL: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html

Usage:
    spark-submit spark_csv_to_parquet.py <s3_ap_alias> <input_prefix> <output_prefix>
"""
import sys
from pyspark.sql import SparkSession

def main():
    s3_ap = sys.argv[1] if len(sys.argv) > 1 else ""
    input_prefix = sys.argv[2] if len(sys.argv) > 2 else "sensor-logs/"
    output_prefix = sys.argv[3] if len(sys.argv) > 3 else "parquet-output/"

    input_path = f"s3://{s3_ap}/{input_prefix}"
    output_path = f"s3://{s3_ap}/{output_prefix}"

    spark = SparkSession.builder.appName("FSxN-S3AP-CSV-to-Parquet").getOrCreate()

    print(f"Reading CSV from: {input_path}")
    df = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)

    print(f"Schema:")
    df.printSchema()
    print(f"Row count: {df.count()}")

    print(f"Writing Parquet to: {output_path}")
    df.write.mode("overwrite").parquet(output_path)

    print("CSV to Parquet conversion complete")
    spark.stop()

if __name__ == "__main__":
    main()
