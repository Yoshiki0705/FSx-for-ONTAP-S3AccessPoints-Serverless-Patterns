#!/usr/bin/env python3
"""Add 'Pattern B: OutputDestination selectable' section to UC9/UC10/UC12 demo-guide.md files.

Inserts the section right after '*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*'
and before '## 検証済みの UI/UX スクリーンショット' or similar downstream section.
"""

from __future__ import annotations

import sys
from pathlib import Path

UC_CONFIG = {
    "autonomous-driving": {
        "uc_id": "UC9 autonomous-driving",
        "purpose": "ADAS / 自動運転データ（フレーム抽出、点群QC、アノテーション、推論）",
    },
    "construction-bim": {
        "uc_id": "UC10 construction-bim",
        "purpose": "建設 BIM / 図面 OCR / 安全コンプライアンスチェック",
    },
    "logistics-ocr": {
        "uc_id": "UC12 logistics-ocr",
        "purpose": "配送伝票 OCR / 在庫分析 / 物流レポート",
    },
}


def build_section(uc_dir: str, cfg: dict) -> str:
    uc_id = cfg["uc_id"]
    purpose = cfg["purpose"]
    return f"""*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

{uc_id} は 2026-05-10 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: {purpose}

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${{AWS::StackName}}-output-${{AWS::AccountId}}`）を作成し、
AI 成果物をそこに書き込みます。

```bash
aws cloudformation deploy \\
  --template-file {uc_dir}/template-deploy.yaml \\
  --stack-name fsxn-{uc_dir}-demo \\
  --parameter-overrides \\
    OutputDestination=STANDARD_S3 \\
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" パターン）
AI 成果物を FSxN S3 Access Point 経由でオリジナルデータと**同一の FSx ONTAP ボリューム**に
書き戻します。SMB/NFS ユーザーが業務で使用するディレクトリ構造内で AI 成果物を
直接閲覧できます。標準 S3 バケットは作成されません。

```bash
aws cloudformation deploy \\
  --template-file {uc_dir}/template-deploy.yaml \\
  --stack-name fsxn-{uc_dir}-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    S3AccessPointName=eda-demo-s3ap \\
    ... (他の必須パラメータ)
```

**注意事項**:

- `S3AccessPointName` の指定を強く推奨（Alias 形式と ARN 形式の両方で IAM 許可する）
- 5GB 超のオブジェクトは FSxN S3AP では不可（AWS 仕様）、マルチパートアップロード必須
- AWS 仕様上の制約は
  [プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
  および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照

---

## 検証済みの UI/UX スクリーンショット"""


def patch(path: Path, uc_dir: str, cfg: dict) -> bool:
    text = path.read_text()
    old = "*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*\n\n---\n\n## 検証済みの UI/UX スクリーンショット"
    if old not in text:
        print(f"SKIP (marker not found): {path}")
        return False
    new = build_section(uc_dir, cfg)
    text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"PATCHED: {path}")
    return True


def main() -> int:
    for uc_dir, cfg in UC_CONFIG.items():
        path = Path(f"{uc_dir}/docs/demo-guide.md")
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            continue
        patch(path, uc_dir, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
