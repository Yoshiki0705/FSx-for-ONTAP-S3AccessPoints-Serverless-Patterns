#!/usr/bin/env python3
"""Add 'Pattern A: Native S3AP Output' section to UC1-UC5 demo-guide.md files.

Inserts the section right after the line that ends with
'本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*'
and before '## 検証済みの UI/UX スクリーンショット'.
"""

from __future__ import annotations

import sys
from pathlib import Path

UC_CONFIG = {
    "legal-compliance": {
        "uc_id": "UC1 legal-compliance",
        "output_desc": "契約メタデータ、監査ログ、サマリーレポート",
        "source_desc": "オリジナル契約データ",
        "example_path": "/vol/contracts/\n  ├── 2026/Q2/contract_ABC.pdf         # オリジナル契約書\n  └── summaries/2026/05/                # AI 生成サマリー（同じボリューム内）\n      └── contract_ABC.json",
    },
    "financial-idp": {
        "uc_id": "UC2 financial-idp",
        "output_desc": "請求書 OCR 結果、構造化メタデータ、BedRock サマリー",
        "source_desc": "オリジナル請求書 PDF",
        "example_path": "/vol/invoices/\n  ├── 2026/05/invoice_001.pdf          # オリジナル請求書\n  └── summaries/2026/05/                # AI 生成サマリー（同じボリューム内）\n      └── invoice_001.json",
    },
    "manufacturing-analytics": {
        "uc_id": "UC3 manufacturing-analytics",
        "output_desc": "センサーデータ解析結果、異常検知レポート、画像検査結果",
        "source_desc": "オリジナルセンサー CSV と検査画像",
        "example_path": "/vol/sensors/\n  ├── 2026/05/line_A/sensor_001.csv    # オリジナルセンサーデータ\n  └── analysis/2026/05/                 # AI 異常検知結果（同じボリューム内）\n      └── line_A_report.json",
    },
    "media-vfx": {
        "uc_id": "UC4 media-vfx",
        "output_desc": "レンダリングメタデータ、フレーム品質評価",
        "source_desc": "オリジナルレンダリングアセット",
        "example_path": "/vol/renders/\n  ├── shot_001/frame_0001.exr         # オリジナルレンダーフレーム\n  └── qc/shot_001/                     # フレーム品質評価（同じボリューム内）\n      └── frame_0001_qc.json",
    },
    "healthcare-dicom": {
        "uc_id": "UC5 healthcare-dicom",
        "output_desc": "DICOM メタデータ、匿名化結果、PII 検出ログ",
        "source_desc": "オリジナル DICOM 医用画像",
        "example_path": "/vol/dicom/\n  ├── patient_001/study_A/image.dcm    # オリジナル DICOM\n  └── metadata/patient_001/             # AI 匿名化結果（同じボリューム内）\n      └── study_A_anonymized.json",
    },
}


def build_section(uc_dir: str, cfg: dict) -> str:
    uc_id = cfg["uc_id"]
    output_desc = cfg["output_desc"]
    source_desc = cfg["source_desc"]
    example_path = cfg["example_path"]
    return f"""*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: FSxN S3 Access Point (Pattern A)

{uc_id} は **Pattern A: Native S3AP Output** に分類されます
（`docs/output-destination-patterns.md` 参照）。

**設計**: {output_desc}は全て FSxN S3 Access Point 経由で
{source_desc}と**同一の FSx ONTAP ボリューム**に書き戻されます。標準 S3 バケットは
作成されません（"no data movement" パターン）。

**CloudFormation パラメータ**:
- `S3AccessPointAlias`: 入力データ読み取り用 S3 AP Alias
- `S3AccessPointOutputAlias`: 出力書き込み用 S3 AP Alias（入力と同じでも可）

**デプロイ例**:
```bash
aws cloudformation deploy \\
  --template-file {uc_dir}/template-deploy.yaml \\
  --stack-name fsxn-{uc_dir}-demo \\
  --parameter-overrides \\
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \\
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \\
    ... (他の必須パラメータ)
```

**SMB/NFS ユーザーからの見え方**:
```
{example_path}
```

AWS 仕様上の制約については
[プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照。

---

## 検証済みの UI/UX スクリーンショット"""


def patch(path: Path, uc_dir: str, cfg: dict) -> bool:
    text = path.read_text()
    old = "*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*\n\n---\n\n## 検証済みの UI/UX スクリーンショット"
    if old not in text:
        print(f"SKIP (marker not found or already patched): {path}")
        return False
    new = build_section(uc_dir, cfg)
    text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"PATCHED: {path}")
    return True


def main() -> int:
    for uc_dir, cfg in UC_CONFIG.items():
        if uc_dir == "legal-compliance":
            # already patched manually
            continue
        path = Path(f"{uc_dir}/docs/demo-guide.md")
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            continue
        patch(path, uc_dir, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
