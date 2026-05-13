"""StackSets 互換性バリデータのプロパティテスト + ユニットテスト.

Property 5: StackSets 互換性バリデータの検出精度
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from check_stacksets_compatibility import (
    ValidationResult,
    check_export_collision,
    check_hardcoded_account_ids,
    check_resource_name_uniqueness,
    check_vpc_parameterization,
    validate_template,
)


class TestHardcodedAccountIdProperty:
    """Property 5: ハードコード Account ID 検出精度."""

    @settings(max_examples=100)
    @given(
        account_id=st.from_regex(r"[1-9]\d{11}", fullmatch=True),
    )
    def test_detects_hardcoded_account_id(self, account_id: str) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 5: バリデータ検出精度.

        ハードコード 12 桁 Account ID を含むテンプレートの検出を検証。
        """
        content = f"""
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: my-bucket-{account_id}
"""
        results = check_hardcoded_account_ids(content, "test.yaml")
        # Should detect the account ID
        account_ids_found = [
            r for r in results if account_id in r.message
        ]
        assert len(account_ids_found) > 0, (
            f"Failed to detect account ID {account_id}"
        )

    def test_ignores_sub_with_account_id(self) -> None:
        """${AWS::AccountId} を含む行は無視する."""
        content = """
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "my-bucket-${AWS::AccountId}"
"""
        results = check_hardcoded_account_ids(content, "test.yaml")
        assert len(results) == 0

    def test_ignores_comments(self) -> None:
        """コメント行は無視する."""
        content = """
# Account ID: 178625946981
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
"""
        results = check_hardcoded_account_ids(content, "test.yaml")
        assert len(results) == 0

    def test_ignores_safe_patterns(self) -> None:
        """既知の安全パターン（000000000000, 123456789012）は無視する."""
        content = """
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: my-bucket-123456789012
"""
        results = check_hardcoded_account_ids(content, "test.yaml")
        assert len(results) == 0


class TestVpcParameterizationProperty:
    """Property 5: VPC/Subnet/SecurityGroup ハードコード検出."""

    def test_detects_hardcoded_vpc_id(self) -> None:
        """ハードコード VPC ID を検出する."""
        content = """
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties:
      VpcConfig:
        VpcId: vpc-0ae01826f906191af
"""
        results = check_vpc_parameterization(content, {}, "test.yaml")
        assert len(results) == 1
        assert "vpc-0ae01826f906191af" in results[0].message

    def test_detects_hardcoded_subnet_id(self) -> None:
        """ハードコード Subnet ID を検出する."""
        content = """
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties:
      VpcConfig:
        SubnetIds:
          - subnet-0abc1234def56789a
"""
        results = check_vpc_parameterization(content, {}, "test.yaml")
        assert len(results) == 1
        assert "subnet-" in results[0].message

    def test_detects_hardcoded_sg_id(self) -> None:
        """ハードコード Security Group ID を検出する."""
        content = """
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties:
      VpcConfig:
        SecurityGroupIds:
          - sg-0abc1234def56789a
"""
        results = check_vpc_parameterization(content, {}, "test.yaml")
        assert len(results) == 1
        assert "sg-" in results[0].message

    def test_no_false_positive_on_ref(self) -> None:
        """!Ref を使用している場合は検出しない."""
        content = """
Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties:
      VpcConfig:
        VpcId: !Ref VpcId
"""
        results = check_vpc_parameterization(content, {}, "test.yaml")
        assert len(results) == 0


class TestResourceNameUniqueness:
    """リソース名一意性チェック."""

    def test_detects_static_function_name(self) -> None:
        """静的 FunctionName を検出する."""
        template = {
            "Resources": {
                "MyLambda": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "FunctionName": "my-static-function",
                    },
                }
            }
        }
        results = check_resource_name_uniqueness(template, "test.yaml")
        assert len(results) == 1
        assert "static" in results[0].message.lower() or "FunctionName" in results[0].message

    def test_no_warning_for_sub_name(self) -> None:
        """!Sub を使用した名前は警告しない."""
        template = {
            "Resources": {
                "MyLambda": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "FunctionName": {
                            "Fn::Sub": "my-function-${AWS::StackName}"
                        },
                    },
                }
            }
        }
        results = check_resource_name_uniqueness(template, "test.yaml")
        assert len(results) == 0


class TestExportCollision:
    """Export 名衝突チェック."""

    def test_detects_static_export(self) -> None:
        """静的 Export 名を検出する."""
        template = {
            "Outputs": {
                "QueueUrl": {
                    "Value": "https://sqs...",
                    "Export": {"Name": "my-queue-url"},
                }
            }
        }
        results = check_export_collision(template, "test.yaml")
        assert len(results) == 1

    def test_no_warning_for_dynamic_export(self) -> None:
        """動的 Export 名は警告しない."""
        template = {
            "Outputs": {
                "QueueUrl": {
                    "Value": "https://sqs...",
                    "Export": {
                        "Name": {"Fn::Sub": "${AWS::StackName}-QueueUrl"}
                    },
                }
            }
        }
        results = check_export_collision(template, "test.yaml")
        assert len(results) == 0


class TestValidateTemplate:
    """validate_template 統合テスト."""

    def test_nonexistent_file(self) -> None:
        """存在しないファイルでエラー."""
        results = validate_template("/nonexistent/path.yaml")
        assert len(results) == 1
        assert results[0].rule == "file-not-found"

    def test_valid_template(self) -> None:
        """正常テンプレートで false positive なし."""
        content = """
AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub "my-function-${AWS::StackName}"
      Runtime: python3.12
      Handler: handler.handler
      Code:
        ZipFile: |
          def handler(event, context):
              return {"statusCode": 200}
Outputs:
  LambdaArn:
    Value: !GetAtt MyLambda.Arn
    Export:
      Name: !Sub "${AWS::StackName}-LambdaArn"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            f.flush()
            results = validate_template(f.name)

        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0
