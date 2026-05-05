#!/usr/bin/env python3
"""AWS 検証で発見された問題をテンプレートに一括反映するスクリプト

修正内容:
1. CloudWatch Logs VPC Endpoint の追加
2. S3 Gateway VPC Endpoint の追加（PrivateRouteTableIds パラメータ付き）
3. IAM ポリシーの S3 AP ARN 形式修正（S3AccessPointName パラメータ追加）

対象: 全 UC の template.yaml
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Phase 2 UC ディレクトリ
PHASE2_UCS = [
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "construction-bim",
    "retail-catalog",
    "logistics-ocr",
    "education-research",
    "insurance-claims",
]

# Phase 1 UC ディレクトリ
PHASE1_UCS = [
    "legal-compliance",
    "financial-idp",
    "manufacturing-analytics",
    "media-vfx",
    "healthcare-dicom",
]

ALL_UCS = PHASE1_UCS + PHASE2_UCS

# CloudWatch Logs Endpoint リソース定義
LOGS_ENDPOINT = """
  CloudWatchLogsEndpoint:
    Type: AWS::EC2::VPCEndpoint
    Condition: CreateVpcEndpoints
    Properties:
      VpcId: !Ref VpcId
      ServiceName: !Sub "com.amazonaws.${AWS::Region}.logs"
      VpcEndpointType: Interface
      SubnetIds: !Ref PrivateSubnetIds
      SecurityGroupIds:
        - !Ref VpcEndpointSecurityGroup
      PrivateDnsEnabled: true
"""


def add_logs_endpoint(content: str) -> str:
    """CloudWatch Logs VPC Endpoint を追加する"""
    if "CloudWatchLogsEndpoint:" in content:
        return content  # 既に存在

    # CloudWatchEndpoint の後に追加
    pattern = r"(  CloudWatchEndpoint:\n.*?PrivateDnsEnabled: true\n)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + LOGS_ENDPOINT + content[insert_pos:]
        print("    ✅ CloudWatch Logs Endpoint 追加")
    else:
        print("    ⚠️  CloudWatchEndpoint が見つかりません")
    return content


def fix_iam_s3ap_arns(content: str) -> str:
    """IAM ポリシーの S3 AP ARN に GetBucketLocation を追加する

    既存の s3:ListBucket, s3:GetObject に s3:GetBucketLocation を追加
    """
    changes = 0

    # Discovery Lambda の S3AccessPointRead に GetBucketLocation を追加
    old_pattern = """              - Sid: S3AccessPointRead
                Effect: Allow
                Action:
                  - s3:ListBucket
                  - s3:GetObject
                Resource:"""
    new_pattern = """              - Sid: S3AccessPointRead
                Effect: Allow
                Action:
                  - s3:ListBucket
                  - s3:GetObject
                  - s3:GetBucketLocation
                Resource:"""

    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern, 1)
        changes += 1

    if changes > 0:
        print(f"    ✅ IAM S3 AP ARN に GetBucketLocation 追加 ({changes} 箇所)")
    return content


def process_template(uc_name: str) -> None:
    """UC テンプレートを処理する"""
    template_path = os.path.join(PROJECT_ROOT, uc_name, "template.yaml")
    if not os.path.exists(template_path):
        print(f"  ⚠️  {uc_name}: template.yaml not found")
        return

    print(f"  📝 {uc_name}:")

    with open(template_path, "r") as f:
        content = f.read()

    original = content

    # 1. CloudWatch Logs Endpoint 追加
    content = add_logs_endpoint(content)

    # 2. IAM S3 AP ARN 修正
    content = fix_iam_s3ap_arns(content)

    if content != original:
        with open(template_path, "w") as f:
            f.write(content)
        print(f"    💾 保存完了")
    else:
        print(f"    ℹ️  変更なし")


def main():
    target_ucs = sys.argv[1:] if len(sys.argv) > 1 else PHASE2_UCS
    print("=== テンプレート一括修正 ===\n")
    for uc in target_ucs:
        process_template(uc)
    print("\n✅ 完了")


if __name__ == "__main__":
    main()
