#!/usr/bin/env python3
"""
template.yaml → template-deploy.yaml 変換スクリプト

SAM Transform を削除し、Lambda の Handler パスを修正し、
Code: S3Bucket/S3Key を追加する。
"""
import os
import re
import sys
import yaml


def convert_template(uc_name: str) -> None:
    """UC の template.yaml を template-deploy.yaml に変換する。"""
    # スクリプトの場所からプロジェクトルートを特定
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    input_path = os.path.join(project_root, uc_name, "template.yaml")
    output_path = os.path.join(project_root, uc_name, "template-deploy.yaml")

    with open(input_path, "r") as f:
        content = f.read()

    # 1. SAM Transform 行を削除
    content = re.sub(r'^Transform:.*\n', '', content, flags=re.MULTILINE)

    # 2. DeployBucket パラメータを追加（Parameters セクションの先頭に）
    deploy_bucket_param = """  DeployBucket:
    Type: String
    Description: S3 bucket containing Lambda deployment packages

"""
    content = content.replace(
        "Parameters:\n",
        f"Parameters:\n{deploy_bucket_param}",
        1
    )

    # 3. Lambda Handler パスを修正 + Code ブロック追加
    # パターン: Handler: <uc-name>/functions/<func>/handler.handler → Handler: handler.handler
    # + Code: S3Bucket/S3Key を追加
    
    # Lambda 関数名とZIPファイル名のマッピングを検出
    handler_pattern = re.compile(
        r'(      Handler: )' + re.escape(uc_name) + r'/functions/(\w+)/handler\.handler'
    )
    
    def replace_handler(match):
        func_name = match.group(2)
        return f'{match.group(1)}handler.handler\n      Code:\n        S3Bucket: !Ref DeployBucket\n        S3Key: lambda/{uc_name}-{func_name}.zip'
    
    content = handler_pattern.sub(replace_handler, content)

    with open(output_path, "w") as f:
        f.write(content)

    print(f"✅ Created {uc_name}/template-deploy.yaml")


if __name__ == "__main__":
    ucs = sys.argv[1:] if len(sys.argv) > 1 else [
        "financial-idp",
        "manufacturing-analytics",
        "media-vfx",
        "healthcare-dicom",
    ]
    for uc in ucs:
        convert_template(uc)
