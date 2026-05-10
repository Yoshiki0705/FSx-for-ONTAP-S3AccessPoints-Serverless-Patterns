#!/usr/bin/env python3
"""Add Phase 7 screenshot placeholders to each UC's 7-language READMEs.

UC15 / UC16 / UC17 の各 README（en, ko, zh-CN, zh-TW, fr, de, es）の
## Overview セクション直後に、UI/UX 寄りスクリーンショット配置プレースホルダーを挿入する。

Step Functions のような技術者向けビューは対象外。Public Sector の一般職員が
日常的に見る画面（S3 ファイル一覧、SNS メール、墨消し後の本文、Bedrock レポート等）
を想定したキャプション。
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _screenshot_block(
    ss_path: str,
    caption: str,
    internal_note: str = "",
) -> str:
    """共通の HTML コメント + image タグを生成する。"""
    comment = f"<!-- SCREENSHOT: {Path(ss_path).name}"
    if internal_note:
        comment += f"\n     {internal_note}"
    comment += " -->"
    return f"{comment}\n![{caption}]({ss_path})"


UC_SECTIONS: dict[str, dict[str, list[tuple[str, str, str]]]] = {
    # format: uc_dir -> locale -> list of (heading, caption, image_file)
    "defense-satellite": {
        # locale: [(section_heading, image_caption, image_filename)]
        "en": [
            ("### Verified UI/UX Screenshots", "", ""),
            ("#### 1. Satellite Imagery Placement (via S3 AP on FSx ONTAP)",
             "UC15: Satellite imagery placement",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. Analytics Output (S3 Output Bucket)",
             "UC15: S3 output bucket",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. Change-Detection Alert (SNS Email)",
             "UC15: SNS alert email",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. Detection Results (JSON)",
             "UC15: Detection results JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "ko": [
            ("### 검증된 UI/UX 스크린샷", "", ""),
            ("#### 1. 위성 이미지 배치 (FSx ONTAP 의 S3 AP 경유)",
             "UC15: 위성 이미지 배치",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. 분석 결과 (S3 출력 버킷)",
             "UC15: S3 출력 버킷",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. 변화 감지 경보 (SNS 이메일)",
             "UC15: SNS 경보 이메일",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. 탐지 결과 (JSON)",
             "UC15: 탐지 결과 JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "zh-CN": [
            ("### 已验证的 UI/UX 截图", "", ""),
            ("#### 1. 卫星图像放置（通过 FSx ONTAP 的 S3 AP）",
             "UC15: 卫星图像放置",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. 分析输出（S3 输出桶）",
             "UC15: S3 输出桶",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. 变化检测告警（SNS 电子邮件）",
             "UC15: SNS 告警邮件",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. 检测结果（JSON）",
             "UC15: 检测结果 JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "zh-TW": [
            ("### 已驗證的 UI/UX 螢幕截圖", "", ""),
            ("#### 1. 衛星影像放置（透過 FSx ONTAP 的 S3 AP）",
             "UC15: 衛星影像放置",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. 分析輸出（S3 輸出儲存貯體）",
             "UC15: S3 輸出儲存貯體",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. 變化偵測警報（SNS 電子郵件）",
             "UC15: SNS 警報郵件",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. 偵測結果（JSON）",
             "UC15: 偵測結果 JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "fr": [
            ("### Captures d'écran UI/UX vérifiées", "", ""),
            ("#### 1. Placement d'imagerie satellite (via S3 AP sur FSx ONTAP)",
             "UC15: Placement d'imagerie satellite",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. Résultats d'analyse (Bucket S3 de sortie)",
             "UC15: Bucket S3 de sortie",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. Alerte de détection de changement (Email SNS)",
             "UC15: Email d'alerte SNS",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. Résultats de détection (JSON)",
             "UC15: Résultats JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "de": [
            ("### Verifizierte UI/UX-Screenshots", "", ""),
            ("#### 1. Satellitenbild-Platzierung (über S3 AP auf FSx ONTAP)",
             "UC15: Satellitenbild-Platzierung",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. Analyseergebnisse (S3 Output-Bucket)",
             "UC15: S3 Output-Bucket",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. Veränderungs-Alarm (SNS-E-Mail)",
             "UC15: SNS-Alarm-E-Mail",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. Erkennungsergebnisse (JSON)",
             "UC15: Erkennungsergebnisse JSON",
             "phase7-uc15-detections-json.png"),
        ],
        "es": [
            ("### Capturas de pantalla UI/UX verificadas", "", ""),
            ("#### 1. Colocación de imágenes satelitales (vía S3 AP en FSx ONTAP)",
             "UC15: Colocación de imágenes satelitales",
             "phase7-uc15-s3-satellite-uploaded.png"),
            ("#### 2. Salida de análisis (Bucket S3)",
             "UC15: Bucket S3 de salida",
             "phase7-uc15-s3-output-bucket.png"),
            ("#### 3. Alerta de detección de cambios (Email SNS)",
             "UC15: Email de alerta SNS",
             "phase7-uc15-sns-alert-email.png"),
            ("#### 4. Resultados de detección (JSON)",
             "UC15: Resultados JSON",
             "phase7-uc15-detections-json.png"),
        ],
    },
    "government-archives": {
        "en": [
            ("### Verified UI/UX Screenshots", "", ""),
            ("#### 1. Public Records Placement (via S3 AP)",
             "UC16: Records placement",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. Redacted Document Preview",
             "UC16: Redacted document preview",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. Redaction Metadata (Sidecar JSON)",
             "UC16: Redaction metadata",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. FOIA Deadline Reminder (SNS Email)",
             "UC16: FOIA reminder email",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. NARA GRS Retention Schedule (DynamoDB)",
             "UC16: Retention table",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "ko": [
            ("### 검증된 UI/UX 스크린샷", "", ""),
            ("#### 1. 공문서 배치 (S3 AP 경유)",
             "UC16: 공문서 배치",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. 편집된 문서 미리보기",
             "UC16: 편집된 문서 미리보기",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. 편집 메타데이터 (Sidecar JSON)",
             "UC16: 편집 메타데이터",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. FOIA 기한 리마인더 (SNS 이메일)",
             "UC16: FOIA 리마인더 이메일",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. NARA GRS 보존 일정 (DynamoDB)",
             "UC16: 보존 테이블",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "zh-CN": [
            ("### 已验证的 UI/UX 截图", "", ""),
            ("#### 1. 公文档案放置（通过 S3 AP）",
             "UC16: 公文档案放置",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. 已编辑文档预览",
             "UC16: 已编辑文档预览",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. 编辑元数据（Sidecar JSON）",
             "UC16: 编辑元数据",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. FOIA 期限提醒（SNS 电子邮件）",
             "UC16: FOIA 提醒邮件",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. NARA GRS 保存计划（DynamoDB）",
             "UC16: 保存表",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "zh-TW": [
            ("### 已驗證的 UI/UX 螢幕截圖", "", ""),
            ("#### 1. 公文檔案放置（透過 S3 AP）",
             "UC16: 公文檔案放置",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. 已編輯文件預覽",
             "UC16: 已編輯文件預覽",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. 編輯中繼資料（Sidecar JSON）",
             "UC16: 編輯中繼資料",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. FOIA 期限提醒（SNS 電子郵件）",
             "UC16: FOIA 提醒郵件",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. NARA GRS 保存排程（DynamoDB）",
             "UC16: 保存表",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "fr": [
            ("### Captures d'écran UI/UX vérifiées", "", ""),
            ("#### 1. Placement des archives publiques (via S3 AP)",
             "UC16: Placement des archives",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. Aperçu du document rédigé",
             "UC16: Document rédigé",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. Métadonnées de rédaction (Sidecar JSON)",
             "UC16: Métadonnées de rédaction",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. Rappel d'échéance FOIA (Email SNS)",
             "UC16: Email de rappel FOIA",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. Calendrier de conservation NARA GRS (DynamoDB)",
             "UC16: Table de conservation",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "de": [
            ("### Verifizierte UI/UX-Screenshots", "", ""),
            ("#### 1. Aktenablage (über S3 AP)",
             "UC16: Aktenablage",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. Geschwärztes Dokument Vorschau",
             "UC16: Geschwärztes Dokument",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. Schwärzungs-Metadaten (Sidecar JSON)",
             "UC16: Schwärzungs-Metadaten",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. FOIA-Fristerinnerung (SNS-E-Mail)",
             "UC16: FOIA-Erinnerungs-E-Mail",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. NARA GRS-Aufbewahrungsplan (DynamoDB)",
             "UC16: Aufbewahrungstabelle",
             "phase7-uc16-dynamodb-retention.png"),
        ],
        "es": [
            ("### Capturas de pantalla UI/UX verificadas", "", ""),
            ("#### 1. Colocación de archivos públicos (vía S3 AP)",
             "UC16: Colocación de archivos",
             "phase7-uc16-s3-archives-uploaded.png"),
            ("#### 2. Vista previa del documento redactado",
             "UC16: Documento redactado",
             "phase7-uc16-redacted-text-preview.png"),
            ("#### 3. Metadatos de redacción (Sidecar JSON)",
             "UC16: Metadatos de redacción",
             "phase7-uc16-redaction-metadata-json.png"),
            ("#### 4. Recordatorio de plazo FOIA (Email SNS)",
             "UC16: Email recordatorio FOIA",
             "phase7-uc16-foia-reminder-email.png"),
            ("#### 5. Programa de retención NARA GRS (DynamoDB)",
             "UC16: Tabla de retención",
             "phase7-uc16-dynamodb-retention.png"),
        ],
    },
    "smart-city-geospatial": {
        "en": [
            ("### Verified UI/UX Screenshots", "", ""),
            ("#### 1. GIS Data Placement (via S3 AP)",
             "UC17: GIS data placement",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Bedrock-Generated Urban Planning Report",
             "UC17: Bedrock report",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. Disaster Risk Map (JSON)",
             "UC17: Risk map",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. Land-Use Distribution",
             "UC17: Land-use distribution",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. Time-Series Change (DynamoDB)",
             "UC17: Land-use history",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "ko": [
            ("### 검증된 UI/UX 스크린샷", "", ""),
            ("#### 1. GIS 데이터 배치 (S3 AP 경유)",
             "UC17: GIS 데이터 배치",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Bedrock 이 생성한 도시 계획 보고서",
             "UC17: Bedrock 보고서",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. 재난 위험 지도 (JSON)",
             "UC17: 위험 지도",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. 토지 이용 분포",
             "UC17: 토지 이용 분포",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. 시계열 변화 (DynamoDB)",
             "UC17: 토지 이용 이력",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "zh-CN": [
            ("### 已验证的 UI/UX 截图", "", ""),
            ("#### 1. GIS 数据放置（通过 S3 AP）",
             "UC17: GIS 数据放置",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Bedrock 生成的城市规划报告",
             "UC17: Bedrock 报告",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. 灾害风险地图（JSON）",
             "UC17: 风险地图",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. 土地利用分布",
             "UC17: 土地利用分布",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. 时间序列变化（DynamoDB）",
             "UC17: 土地利用历史",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "zh-TW": [
            ("### 已驗證的 UI/UX 螢幕截圖", "", ""),
            ("#### 1. GIS 資料放置（透過 S3 AP）",
             "UC17: GIS 資料放置",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Bedrock 產生的都市計劃報告",
             "UC17: Bedrock 報告",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. 災害風險地圖（JSON）",
             "UC17: 風險地圖",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. 土地利用分佈",
             "UC17: 土地利用分佈",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. 時間序列變化（DynamoDB）",
             "UC17: 土地利用歷史",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "fr": [
            ("### Captures d'écran UI/UX vérifiées", "", ""),
            ("#### 1. Placement de données GIS (via S3 AP)",
             "UC17: Placement GIS",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Rapport d'urbanisme généré par Bedrock",
             "UC17: Rapport Bedrock",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. Carte de risques de catastrophes (JSON)",
             "UC17: Carte de risques",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. Distribution d'usage du sol",
             "UC17: Usage du sol",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. Évolution temporelle (DynamoDB)",
             "UC17: Historique d'usage",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "de": [
            ("### Verifizierte UI/UX-Screenshots", "", ""),
            ("#### 1. GIS-Datenplatzierung (über S3 AP)",
             "UC17: GIS-Datenplatzierung",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Bedrock-generierter Stadtplanungsbericht",
             "UC17: Bedrock-Bericht",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. Katastrophen-Risikokarte (JSON)",
             "UC17: Risikokarte",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. Landnutzungsverteilung",
             "UC17: Landnutzungsverteilung",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. Zeitreihe (DynamoDB)",
             "UC17: Nutzungshistorie",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
        "es": [
            ("### Capturas de pantalla UI/UX verificadas", "", ""),
            ("#### 1. Colocación de datos GIS (vía S3 AP)",
             "UC17: Colocación de GIS",
             "phase7-uc17-s3-gis-uploaded.png"),
            ("#### 2. Informe de planificación urbana generado por Bedrock",
             "UC17: Informe Bedrock",
             "phase7-uc17-bedrock-report.png"),
            ("#### 3. Mapa de riesgos de desastres (JSON)",
             "UC17: Mapa de riesgos",
             "phase7-uc17-risk-map-json.png"),
            ("#### 4. Distribución de uso del suelo",
             "UC17: Distribución de uso",
             "phase7-uc17-landuse-distribution.png"),
            ("#### 5. Cambio temporal (DynamoDB)",
             "UC17: Historial de uso",
             "phase7-uc17-dynamodb-landuse-history.png"),
        ],
    },
}

PREAMBLES = {
    "en": (
        "> This section shows **UI/UX screens that general agency staff actually use** "
        "during day-to-day operations. Technical views like Step Functions graphs are "
        "documented separately in `docs/verification-results-phase7.md`."
    ),
    "ko": (
        "> 본 섹션은 **일반 직원이 일상 업무에서 실제로 사용하는 UI/UX 화면**을 게시합니다. "
        "Step Functions 그래프와 같은 기술자 화면은 `docs/verification-results-phase7.md` 를 참조하세요."
    ),
    "zh-CN": (
        "> 本节展示**一般人员在日常工作中实际使用的 UI/UX 界面**。"
        "Step Functions 图形等技术视图另见 `docs/verification-results-phase7.md`。"
    ),
    "zh-TW": (
        "> 本節展示**一般職員在日常工作中實際使用的 UI/UX 介面**。"
        "Step Functions 圖形等技術視圖另見 `docs/verification-results-phase7.md`。"
    ),
    "fr": (
        "> Cette section présente **les écrans UI/UX utilisés au quotidien par les agents**. "
        "Les vues techniques comme les graphes Step Functions sont documentées séparément dans "
        "`docs/verification-results-phase7.md`."
    ),
    "de": (
        "> Dieser Abschnitt zeigt **UI/UX-Bildschirme, die allgemeine Mitarbeitende im Alltag verwenden**. "
        "Technische Ansichten wie Step-Functions-Graphen werden in `docs/verification-results-phase7.md` dokumentiert."
    ),
    "es": (
        "> Esta sección muestra **pantallas UI/UX que el personal general utiliza en el día a día**. "
        "Las vistas técnicas como gráficos de Step Functions están documentadas en "
        "`docs/verification-results-phase7.md`."
    ),
}


def build_section(uc: str, locale: str, entries: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append(entries[0][0])  # h3 heading
    lines.append("")
    lines.append(PREAMBLES[locale])
    lines.append("")

    for heading, caption, filename in entries[1:]:
        lines.append(heading)
        lines.append("")
        rel_path = f"../docs/screenshots/masked/phase7/{filename}"
        lines.append(f"<!-- SCREENSHOT: {filename} -->")
        lines.append(f"![{caption}]({rel_path})")
        lines.append("")

    return "\n".join(lines)


def apply_to_readme(uc: str, locale: str, entries: list[tuple[str, str, str]]) -> None:
    readme = PROJECT_ROOT / uc / f"README.{locale}.md"
    if not readme.exists():
        print(f"SKIP (missing): {readme}")
        return

    content = readme.read_text()
    if "### Verified UI/UX Screenshots" in content or \
       "### 검증된 UI/UX 스크린샷" in content or \
       "### 已验证的 UI/UX 截图" in content or \
       "### 已驗證的 UI/UX 螢幕截圖" in content or \
       "### Captures d'écran UI/UX vérifiées" in content or \
       "### Verifizierte UI/UX-Screenshots" in content or \
       "### Capturas de pantalla UI/UX verificadas" in content:
        print(f"SKIP (already updated): {readme.name}")
        return

    # Insert before the first "## Deploy" / "## デプロイ" / "## 部署" etc.
    markers = [
        "## Deploy",
        "## デプロイ",
        "## 배포",
        "## 部署",
        "## 部署",
        "## Déploiement",
        "## Bereitstellung",
        "## Despliegue",
    ]
    insert_idx = -1
    for m in markers:
        idx = content.find(m)
        if idx != -1:
            insert_idx = idx
            break

    if insert_idx == -1:
        # Fallback: insert before the directory structure / 最末尾
        marker_alt = "## Directory layout"
        insert_idx = content.find(marker_alt)
        if insert_idx == -1:
            insert_idx = len(content)

    section = build_section(uc, locale, entries) + "\n"
    content = content[:insert_idx] + section + content[insert_idx:]
    readme.write_text(content)
    print(f"UPDATED: {readme.name}")


def main() -> None:
    for uc, locales in UC_SECTIONS.items():
        for locale, entries in locales.items():
            apply_to_readme(uc, locale, entries)


if __name__ == "__main__":
    main()
