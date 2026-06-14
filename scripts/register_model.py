#!/usr/bin/env python3
"""SageMaker Model Registry — モデル登録スクリプト

SageMaker Model Package Group に新しいモデルバージョンを登録する。
登録時に以下のメタデータを設定:
- モデルアーティファクト S3 URI
- トレーニングメトリクス（精度、損失等）
- 承認ステータス（PendingManualApproval）

Usage:
    python register_model.py \
        --model-package-group-name "my-stack-point-cloud-segmentation" \
        --model-url "s3://bucket/models/model.tar.gz" \
        --image-uri "763104351884.dkr.ecr.ap-northeast-1.amazonaws.com/pytorch-inference:2.0-cpu-py310" \
        --accuracy 0.95 \
        --loss 0.05 \
        --description "Point cloud segmentation v2 - improved accuracy"

    # 承認ステータスを Approved に変更:
    python register_model.py \
        --approve \
        --model-package-arn "arn:aws:sagemaker:ap-northeast-1:123456789012:model-package/my-group/1"

Environment Variables:
    AWS_REGION: AWS リージョン (default: ap-northeast-1)
    AWS_PROFILE: AWS プロファイル名 (optional)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def register_model(
    sagemaker_client,
    model_package_group_name: str,
    model_url: str,
    image_uri: str,
    accuracy: float | None = None,
    loss: float | None = None,
    description: str = "",
    content_types: list[str] | None = None,
    response_types: list[str] | None = None,
    approval_status: str = "PendingManualApproval",
) -> dict:
    """SageMaker Model Package Group に新しいモデルバージョンを登録する。

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        model_package_group_name: Model Package Group 名
        model_url: モデルアーティファクトの S3 URI
        image_uri: 推論コンテナイメージ URI
        accuracy: モデル精度メトリクス (optional)
        loss: モデル損失メトリクス (optional)
        description: モデルバージョンの説明
        content_types: サポートする Content-Type リスト
        response_types: サポートする Response Content-Type リスト
        approval_status: 承認ステータス (PendingManualApproval / Approved / Rejected)

    Returns:
        dict: CreateModelPackage API レスポンス

    Raises:
        ClientError: SageMaker API エラー
    """
    if content_types is None:
        content_types = ["application/json", "application/octet-stream"]
    if response_types is None:
        response_types = ["application/json"]

    # InferenceSpecification 構築
    inference_specification = {
        "Containers": [
            {
                "Image": image_uri,
                "ModelDataUrl": model_url,
            }
        ],
        "SupportedContentTypes": content_types,
        "SupportedResponseMIMETypes": response_types,
        "SupportedTransformInstanceTypes": ["ml.m5.large", "ml.m5.xlarge"],
        "SupportedRealtimeInferenceInstanceTypes": [
            "ml.m5.large",
            "ml.m5.xlarge",
            "ml.c5.large",
        ],
    }

    # ModelMetrics 構築
    model_metrics = {}
    if accuracy is not None or loss is not None:
        quality_metrics = {}
        if accuracy is not None:
            quality_metrics["Accuracy"] = {"Value": accuracy}
        if loss is not None:
            quality_metrics["Loss"] = {"Value": loss}

        model_metrics["ModelQuality"] = {
            "Statistics": {
                "ContentType": "application/json",
                "S3Uri": f"s3://placeholder/metrics/{model_package_group_name}/quality.json",
            }
        }

    # カスタムメタデータ
    customer_metadata = {
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "use_case": "autonomous-driving",
        "phase": "4",
    }
    if accuracy is not None:
        customer_metadata["accuracy"] = str(accuracy)
    if loss is not None:
        customer_metadata["loss"] = str(loss)

    # CreateModelPackage リクエスト構築
    create_params: dict = {
        "ModelPackageGroupName": model_package_group_name,
        "InferenceSpecification": inference_specification,
        "ModelPackageDescription": description or f"Model registered at {datetime.now(timezone.utc).isoformat()}",
        "ModelApprovalStatus": approval_status,
        "CustomerMetadataProperties": customer_metadata,
    }

    logger.info(
        "Registering model: group=%s, model_url=%s, status=%s",
        model_package_group_name,
        model_url,
        approval_status,
    )

    response = sagemaker_client.create_model_package(**create_params)

    model_package_arn = response["ModelPackageArn"]
    logger.info("Model registered successfully: %s", model_package_arn)

    return response


def approve_model(
    sagemaker_client,
    model_package_arn: str,
    approval_status: str = "Approved",
    approval_description: str = "",
) -> dict:
    """モデルバージョンの承認ステータスを更新する。

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        model_package_arn: Model Package ARN
        approval_status: 新しい承認ステータス (Approved / Rejected)
        approval_description: 承認/却下の理由

    Returns:
        dict: UpdateModelPackage API レスポンス

    Raises:
        ClientError: SageMaker API エラー
    """
    update_params: dict = {
        "ModelPackageArn": model_package_arn,
        "ModelApprovalStatus": approval_status,
    }

    if approval_description:
        update_params["ApprovalDescription"] = approval_description

    logger.info(
        "Updating model approval: arn=%s, status=%s",
        model_package_arn,
        approval_status,
    )

    response = sagemaker_client.update_model_package(**update_params)

    logger.info(
        "Model approval updated: arn=%s, status=%s",
        model_package_arn,
        approval_status,
    )

    return response


def list_model_versions(
    sagemaker_client,
    model_package_group_name: str,
    approval_status: str | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Model Package Group 内のモデルバージョン一覧を取得する。

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        model_package_group_name: Model Package Group 名
        approval_status: フィルタ用承認ステータス (optional)
        max_results: 最大取得件数

    Returns:
        list[dict]: モデルバージョンのリスト
    """
    list_params: dict = {
        "ModelPackageGroupName": model_package_group_name,
        "MaxResults": max_results,
        "SortBy": "CreationTime",
        "SortOrder": "Descending",
    }

    if approval_status:
        list_params["ModelApprovalStatus"] = approval_status

    response = sagemaker_client.list_model_packages(**list_params)
    packages = response.get("ModelPackageSummaryList", [])

    logger.info(
        "Found %d model versions in group '%s'",
        len(packages),
        model_package_group_name,
    )

    return packages


def main() -> int:
    """CLI エントリポイント"""
    parser = argparse.ArgumentParser(
        description="SageMaker Model Registry — モデル登録・承認スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 新しいモデルバージョンを登録:
  python register_model.py \\
    --model-package-group-name "my-stack-point-cloud-segmentation" \\
    --model-url "s3://bucket/models/model.tar.gz" \\
    --image-uri "763104351884.dkr.ecr.ap-northeast-1.amazonaws.com/pytorch-inference:2.0-cpu-py310" \\
    --accuracy 0.95 --loss 0.05

  # モデルバージョンを承認:
  python register_model.py \\
    --approve \\
    --model-package-arn "arn:aws:sagemaker:ap-northeast-1:123456789012:model-package/my-group/1"

  # モデルバージョン一覧を表示:
  python register_model.py \\
    --list \\
    --model-package-group-name "my-stack-point-cloud-segmentation"
        """,
    )

    # 共通引数
    parser.add_argument(
        "--region",
        default="ap-northeast-1",
        help="AWS リージョン (default: ap-northeast-1)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS プロファイル名 (optional)",
    )

    # アクション選択
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--register",
        action="store_true",
        help="新しいモデルバージョンを登録する",
    )
    action_group.add_argument(
        "--approve",
        action="store_true",
        help="モデルバージョンの承認ステータスを更新する",
    )
    action_group.add_argument(
        "--list",
        action="store_true",
        help="モデルバージョン一覧を表示する",
    )

    # 登録用引数
    parser.add_argument(
        "--model-package-group-name",
        help="Model Package Group 名",
    )
    parser.add_argument(
        "--model-url",
        help="モデルアーティファクトの S3 URI",
    )
    parser.add_argument(
        "--image-uri",
        help="推論コンテナイメージ URI",
    )
    parser.add_argument(
        "--accuracy",
        type=float,
        default=None,
        help="モデル精度メトリクス",
    )
    parser.add_argument(
        "--loss",
        type=float,
        default=None,
        help="モデル損失メトリクス",
    )
    parser.add_argument(
        "--description",
        default="",
        help="モデルバージョンの説明",
    )

    # 承認用引数
    parser.add_argument(
        "--model-package-arn",
        help="Model Package ARN (承認時に必要)",
    )
    parser.add_argument(
        "--approval-status",
        default="Approved",
        choices=["Approved", "Rejected", "PendingManualApproval"],
        help="承認ステータス (default: Approved)",
    )
    parser.add_argument(
        "--approval-description",
        default="",
        help="承認/却下の理由",
    )

    # 一覧用引数
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="最大取得件数 (default: 10)",
    )
    parser.add_argument(
        "--filter-status",
        default=None,
        choices=["Approved", "Rejected", "PendingManualApproval"],
        help="承認ステータスでフィルタ",
    )

    args = parser.parse_args()

    # boto3 セッション作成
    session_kwargs: dict = {"region_name": args.region}
    if args.profile:
        session_kwargs["profile_name"] = args.profile

    session = boto3.Session(**session_kwargs)
    sagemaker_client = session.client("sagemaker")

    try:
        if args.register:
            # バリデーション
            if not args.model_package_group_name:
                parser.error("--model-package-group-name is required for --register")
            if not args.model_url:
                parser.error("--model-url is required for --register")
            if not args.image_uri:
                parser.error("--image-uri is required for --register")

            response = register_model(
                sagemaker_client=sagemaker_client,
                model_package_group_name=args.model_package_group_name,
                model_url=args.model_url,
                image_uri=args.image_uri,
                accuracy=args.accuracy,
                loss=args.loss,
                description=args.description,
            )
            print(json.dumps({"ModelPackageArn": response["ModelPackageArn"]}, indent=2))

        elif args.approve:
            # バリデーション
            if not args.model_package_arn:
                parser.error("--model-package-arn is required for --approve")

            response = approve_model(
                sagemaker_client=sagemaker_client,
                model_package_arn=args.model_package_arn,
                approval_status=args.approval_status,
                approval_description=args.approval_description,
            )
            print(json.dumps({"status": "updated", "arn": args.model_package_arn}, indent=2))

        elif args.list:
            # バリデーション
            if not args.model_package_group_name:
                parser.error("--model-package-group-name is required for --list")

            packages = list_model_versions(
                sagemaker_client=sagemaker_client,
                model_package_group_name=args.model_package_group_name,
                approval_status=args.filter_status,
                max_results=args.max_results,
            )

            # 表示
            print(f"\nModel versions in '{args.model_package_group_name}':")
            print("-" * 80)
            for pkg in packages:
                print(
                    f"  ARN: {pkg['ModelPackageArn']}\n"
                    f"  Status: {pkg.get('ModelApprovalStatus', 'N/A')}\n"
                    f"  Created: {pkg.get('CreationTime', 'N/A')}\n"
                    f"  ---"
                )
            if not packages:
                print("  (no model versions found)")

    except ClientError as e:
        logger.error("AWS API error: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
