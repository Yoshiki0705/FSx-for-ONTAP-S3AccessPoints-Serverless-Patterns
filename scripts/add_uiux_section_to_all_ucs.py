#!/usr/bin/env python3
"""Append a UI/UX screenshot pointer section to demo-guides for UCs that haven't been
re-verified in this session, referencing existing phase1-6 screenshots when relevant.

For E2E-verified UCs (UC3, UC7, UC8, UC10, UC12, UC13) that we have existing
screenshots for, we add a link to the existing captures.

For UCs requiring Textract/Comprehend Medical (UC2, UC5), we note cross-region status.

UC4 (media-vfx) depends on Deadline Cloud; skip detailed UI/UX for now.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# UCs already verified in this session (skip)
SKIP = {"UC6", "UC11", "UC14", "UC15", "UC16", "UC17"}

# Mapping UC to demo-guide paths
UC_DIRS = {
    "UC1": "legal-compliance",
    "UC2": "financial-idp",
    "UC3": "manufacturing-analytics",
    "UC4": "media-vfx",
    "UC5": "healthcare-dicom",
    "UC7": "genomics-pipeline",
    "UC8": "energy-seismic",
    "UC9": "autonomous-driving",
    "UC10": "construction-bim",
    "UC12": "logistics-ocr",
    "UC13": "education-research",
}

# E2E verified in previous phases (from root README.md)
E2E_VERIFIED = {"UC1", "UC3", "UC7", "UC8", "UC10", "UC11", "UC12", "UC13", "UC14"}

# Relevant existing phase1-6 screenshots for each UC
EXISTING_SCREENSHOTS = {
    "UC1": [
        ("phase1/phase1-cloudformation-uc1-deployed.png",
         "UC1 CloudFormation スタックデプロイ完了（2026-05-02 検証時）"),
        ("phase1/phase1-step-functions-uc1-succeeded.png",
         "UC1 Step Functions SUCCEEDED（E2E 実行成功）"),
    ],
    "UC3": [],
    "UC7": [
        ("phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png",
         "UC7 Comprehend Medical ゲノミクス解析結果（Cross-Region us-east-1）"),
    ],
    "UC8": [],
    "UC10": [],
    "UC12": [],
    "UC13": [],
}


SECTION_TEMPLATE = """
---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

{status_block}

### 既存スクリーンショット（Phase 1-6 から該当分）

{existing_block}

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

{recommended_block}

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC={uc_dir} bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh {uc_short}` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `{sample_prefix}/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-{uc_dir}-demo-workflow` を起動（入力 `{{}}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-{uc_dir}-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py {uc_dir}-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh {uc_short}` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
"""


def build_status_block(uc: str) -> str:
    if uc in E2E_VERIFIED:
        return f"- ✅ **E2E 実行**: Phase 1-6 で確認済み（根 README 参照）\n- 📸 **UI/UX 再撮影**: 未実施（本セッションでは UC6/UC11/UC14 を代表として撮影）\n- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照"
    return f"- ⚠️ **E2E 検証**: 一部機能のみ（本番環境では追加検証推奨）\n- 📸 **UI/UX 再撮影**: 未実施"


def build_existing_block(uc: str) -> str:
    shots = EXISTING_SCREENSHOTS.get(uc, [])
    if not shots:
        return "*(該当なし。再検証時に新規撮影してください)*"
    lines = []
    for path, caption in shots:
        rel = f"../../docs/screenshots/masked/{path}"
        lines.append(f"#### {caption}\n\n![{caption}]({rel})\n")
    return "\n".join(lines)


def build_recommended_block(uc: str) -> str:
    """List recommended UI/UX screens per UC."""
    recommendations = {
        "UC1": [
            "S3 出力バケット（audit-reports/、acl-audits/、athena-results/ プレフィックス）",
            "Athena クエリ結果（ACL 違反検出 SQL）",
            "Bedrock 生成の監査レポート（コンプライアンス違反サマリー）",
            "SNS 通知メール（監査アラート）",
        ],
        "UC2": [
            "S3 出力バケット（textract-results/、comprehend-entities/、reports/）",
            "Textract OCR 結果 JSON（契約書・請求書から抽出されたフィールド）",
            "Comprehend エンティティ検出結果（組織名、日付、金額）",
            "Bedrock 生成の要約レポート",
        ],
        "UC3": [
            "S3 出力バケット（metrics/、anomalies/、reports/）",
            "Athena クエリ結果（IoT センサー異常検出）",
            "Rekognition 品質検査画像ラベル",
            "製造品質サマリーレポート",
        ],
        "UC5": [
            "S3 出力バケット（dicom-metadata/、deid-reports/、diagnoses/）",
            "Comprehend Medical エンティティ検出結果（Cross-Region）",
            "DICOM 匿名化済みメタデータ JSON",
        ],
        "UC7": [
            "S3 出力バケット（fastq-qc/、variant-summary/、entities/）",
            "Athena クエリ結果（バリアント頻度集計）",
            "Comprehend Medical 医学エンティティ（Genes, Diseases, Mutations）",
            "Bedrock 生成の研究レポート",
        ],
        "UC8": [
            "S3 出力バケット（segy-metadata/、anomalies/、reports/）",
            "Athena クエリ結果（SEG-Y メタデータ統計）",
            "Rekognition 坑井ログ画像ラベル",
            "異常検知レポート",
        ],
        "UC9": [
            "S3 出力バケット（keyframes/、annotations/、qc/）",
            "Rekognition キーフレーム物体検出結果",
            "LiDAR 点群品質チェックサマリー",
            "COCO 互換アノテーション JSON",
        ],
        "UC10": [
            "S3 出力バケット（drawings-ocr/、bim-metadata/、safety-reports/）",
            "Textract 図面 OCR 結果（Cross-Region）",
            "BIM バージョン差分レポート",
            "Bedrock 安全コンプライアンスチェック",
        ],
        "UC12": [
            "S3 出力バケット（waybills-ocr/、inventory/、reports/）",
            "Textract 伝票 OCR 結果（Cross-Region）",
            "Rekognition 倉庫画像ラベル",
            "配送集計レポート",
        ],
        "UC13": [
            "S3 出力バケット（papers-ocr/、citations/、reports/）",
            "Textract 論文 OCR 結果（Cross-Region）",
            "Comprehend エンティティ検出（著者、引用、キーワード）",
            "研究ネットワーク分析レポート",
        ],
    }
    items = recommendations.get(uc, ["（再検証時に定義）"])
    return "\n".join(f"- {item}" for item in items)


def apply_to_uc(uc_short: str, uc_dir: str) -> None:
    demo_guide = PROJECT_ROOT / uc_dir / "docs" / "demo-guide.md"
    if not demo_guide.exists():
        print(f"SKIP (missing): {demo_guide}")
        return

    content = demo_guide.read_text()
    if "検証済みの UI/UX スクリーンショット" in content:
        print(f"SKIP (already has UI/UX): {uc_short} / {uc_dir}")
        return

    sample_prefix_map = {
        "legal-compliance": "contracts",
        "financial-idp": "invoices",
        "manufacturing-analytics": "sensors",
        "media-vfx": "renders",
        "healthcare-dicom": "dicom",
        "genomics-pipeline": "fastq",
        "energy-seismic": "seismic",
        "autonomous-driving": "footage",
        "construction-bim": "drawings",
        "logistics-ocr": "waybills",
        "education-research": "papers",
    }

    section = SECTION_TEMPLATE.format(
        uc_short=uc_short,
        uc_dir=uc_dir,
        sample_prefix=sample_prefix_map.get(uc_dir, "data"),
        status_block=build_status_block(uc_short),
        existing_block=build_existing_block(uc_short),
        recommended_block=build_recommended_block(uc_short),
    )

    with demo_guide.open("a") as f:
        f.write(section)
    print(f"UPDATED: {uc_short} / {uc_dir}")


def main() -> None:
    for uc_short, uc_dir in UC_DIRS.items():
        if uc_short in SKIP:
            print(f"SKIP (already done): {uc_short}")
            continue
        apply_to_uc(uc_short, uc_dir)


if __name__ == "__main__":
    main()
