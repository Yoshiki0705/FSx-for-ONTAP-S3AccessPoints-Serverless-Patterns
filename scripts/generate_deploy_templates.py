#!/usr/bin/env python3
"""Generate template-deploy.yaml files for Phase 2 UCs.

Transformations:
1. Remove `Transform: AWS::Serverless-2016-10-31` line
2. Add DeployBucket parameter after Parameters: line
3. Replace Lambda Handler paths and add Code block with S3Bucket/S3Key
"""

import re
import os

PHASE2_UCS = [
    "semiconductor-eda",
    "genomics-pipeline",
    "energy-seismic",
    "autonomous-driving",
    "construction-bim",
    "retail-catalog",
    "logistics-ocr",
    "education-research",
    "insurance-claims",
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEPLOY_BUCKET_PARAM = """  DeployBucket:
    Type: String
    Description: S3 bucket containing Lambda deployment packages
"""


def transform_template(uc_name: str) -> str:
    """Read template.yaml and apply deploy transformations."""
    template_path = os.path.join(BASE_DIR, uc_name, "template.yaml")
    with open(template_path, "r") as f:
        content = f.read()

    # 1. Remove Transform line
    content = re.sub(r'^Transform: AWS::Serverless-2016-10-31\n', '', content, flags=re.MULTILINE)

    # 2. Add DeployBucket parameter after Parameters: line
    # Find the first "Parameters:" line and add DeployBucket right after
    content = re.sub(
        r'^(Parameters:\n)',
        r'\1' + DEPLOY_BUCKET_PARAM,
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # 3. Replace Handler paths: UC_NAME/functions/FUNC_NAME/handler.handler -> handler.handler + Code block
    # Pattern: "      Handler: UC_NAME/functions/FUNC_NAME/handler.handler"
    # The handler line indentation is typically 6 spaces (under Properties of Lambda)
    pattern = re.compile(
        r'^(\s+)Handler: ' + re.escape(uc_name) + r'/functions/([^/]+)/handler\.handler$',
        re.MULTILINE,
    )

    def replace_handler(match):
        indent = match.group(1)
        func_name = match.group(2)
        s3_key = f"lambda/{uc_name}-{func_name}.zip"
        return (
            f"{indent}Handler: handler.handler\n"
            f"{indent}Code:\n"
            f"{indent}  S3Bucket: !Ref DeployBucket\n"
            f"{indent}  S3Key: {s3_key}"
        )

    content = pattern.sub(replace_handler, content)

    return content


def main():
    for uc_name in PHASE2_UCS:
        print(f"Processing {uc_name}...")
        deploy_content = transform_template(uc_name)
        output_path = os.path.join(BASE_DIR, uc_name, "template-deploy.yaml")
        with open(output_path, "w") as f:
            f.write(deploy_content)
        print(f"  -> Written {output_path}")
    print("\nDone! All 9 Phase 2 UC template-deploy.yaml files generated.")


if __name__ == "__main__":
    main()
