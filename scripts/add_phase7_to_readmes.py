#!/usr/bin/env python3
"""Add Phase 7 (UC15/UC16/UC17) section to all language READMEs."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Locale-specific translations for the Phase 7 section
LOCALES = {
    "en": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) Public Sector Expansion",
        "uc_table_header": "| # | Directory | Industry | Pattern | AI/ML services | ap-northeast-1 status |\n|---|-----------|----------|---------|----------------|----------------------|",
        "uc15_row": "| UC15 | [`defense-satellite/`](defense-satellite/README.en.md) | Defense/Space | Satellite imagery analytics (object detection, change detection, alerts) | Rekognition, SageMaker (optional), Bedrock | ✅ Code + tests complete, AWS verified |",
        "uc16_row": "| UC16 | [`government-archives/`](government-archives/README.en.md) | Government | Public records / FOIA (OCR, classification, redaction, 20-day deadline tracking) | Textract ⚠️, Comprehend, Bedrock, OpenSearch (optional) | ✅ Code + tests complete, AWS verified |",
        "uc17_row": "| UC17 | [`smart-city-geospatial/`](smart-city-geospatial/README.en.md) | Smart City | Geospatial analytics (CRS normalization, land use, risk mapping, planning report) | Rekognition, SageMaker (optional), Bedrock (Nova Lite) | ✅ Code + tests complete, AWS verified |",
        "public_sector_note": "> **Public Sector compliance**: UC15 targets DoD CC SRG / CSfC / FedRAMP High (on GovCloud migration), UC16 targets NARA / FOIA Section 552 / Section 508, UC17 targets INSPIRE Directive / OGC standards.",
        "doc_row_uc14": "| UC14 | Insurance | [📐 Architecture](insurance-claims/docs/architecture.en.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.en.md) |",
        "doc_row_uc15": "| UC15 | Defense/Space (Satellite) | [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | Government (FOIA / Archives) | [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | Smart City | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "ko": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) 공공 부문 확장",
        "uc_table_header": "| # | 디렉토리 | 업계 | 패턴 | AI/ML 서비스 | ap-northeast-1 검증 상태 |\n|---|---------|------|------|-------------|------------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | 국방·우주 | 위성 이미지 분석 (물체 탐지, 변화 탐지, 경고) | Rekognition, SageMaker (선택), Bedrock | ✅ 코드 + 테스트 완료, AWS 검증됨 |",
        "uc16_row": "| UC16 | `government-archives/` | 정부 | 공문서 아카이브·FOIA (OCR, 분류, 삭제, 20일 기한 추적) | Textract ⚠️, Comprehend, Bedrock, OpenSearch (선택) | ✅ 코드 + 테스트 완료, AWS 검증됨 |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | 스마트 시티 | 지리 공간 분석 (CRS 정규화, 토지 이용, 위험 매핑, 계획 보고서) | Rekognition, SageMaker (선택), Bedrock (Nova Lite) | ✅ 코드 + 테스트 완료, AWS 검증됨 |",
        "public_sector_note": "> **공공 부문 적합성**: UC15는 DoD CC SRG / CSfC / FedRAMP High (GovCloud 마이그레이션 시), UC16은 NARA / FOIA 섹션 552 / 섹션 508, UC17은 INSPIRE 지침 / OGC 표준 준수.",
        "doc_row_uc14": "| UC14 | 보험 | [📐 Architecture](insurance-claims/docs/architecture.ko.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.ko.md) |",
        "doc_row_uc15": "| UC15 | 국방·우주 (위성 이미지) | [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | 정부 (FOIA / 아카이브) | [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | 스마트 시티 | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "zh-CN": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) 公共部门扩展",
        "uc_table_header": "| # | 目录 | 行业 | 模式 | AI/ML 服务 | ap-northeast-1 验证状态 |\n|---|------|------|------|-----------|-----------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | 国防/太空 | 卫星图像分析（对象检测、变化检测、警报）| Rekognition, SageMaker（可选）, Bedrock | ✅ 代码+测试完成，AWS 已验证 |",
        "uc16_row": "| UC16 | `government-archives/` | 政府 | 公文档案·FOIA（OCR、分类、编辑、20 天期限跟踪）| Textract ⚠️, Comprehend, Bedrock, OpenSearch（可选）| ✅ 代码+测试完成，AWS 已验证 |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | 智慧城市 | 地理空间分析（CRS 归一化、土地利用、风险映射、规划报告）| Rekognition, SageMaker（可选）, Bedrock (Nova Lite) | ✅ 代码+测试完成，AWS 已验证 |",
        "public_sector_note": "> **公共部门合规性**: UC15 针对 DoD CC SRG / CSfC / FedRAMP High（GovCloud 迁移），UC16 针对 NARA / FOIA Section 552 / Section 508，UC17 针对 INSPIRE 指令 / OGC 标准。",
        "doc_row_uc14": "| UC14 | 保险 | [📐 Architecture](insurance-claims/docs/architecture.zh-CN.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.zh-CN.md) |",
        "doc_row_uc15": "| UC15 | 国防/太空（卫星图像）| [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | 政府（FOIA / 档案）| [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | 智慧城市 | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "zh-TW": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) 公共部門擴展",
        "uc_table_header": "| # | 目錄 | 產業 | 模式 | AI/ML 服務 | ap-northeast-1 驗證狀態 |\n|---|------|------|------|-----------|-----------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | 國防/太空 | 衛星影像分析（物件偵測、變化偵測、警報）| Rekognition, SageMaker（可選）, Bedrock | ✅ 程式碼+測試完成，AWS 已驗證 |",
        "uc16_row": "| UC16 | `government-archives/` | 政府 | 公文檔案·FOIA（OCR、分類、編輯、20 天期限追蹤）| Textract ⚠️, Comprehend, Bedrock, OpenSearch（可選）| ✅ 程式碼+測試完成，AWS 已驗證 |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | 智慧城市 | 地理空間分析（CRS 正規化、土地利用、風險映射、規劃報告）| Rekognition, SageMaker（可選）, Bedrock (Nova Lite) | ✅ 程式碼+測試完成，AWS 已驗證 |",
        "public_sector_note": "> **公共部門合規性**: UC15 針對 DoD CC SRG / CSfC / FedRAMP High（GovCloud 遷移），UC16 針對 NARA / FOIA Section 552 / Section 508，UC17 針對 INSPIRE 指令 / OGC 標準。",
        "doc_row_uc14": "| UC14 | 保險 | [📐 Architecture](insurance-claims/docs/architecture.zh-TW.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.zh-TW.md) |",
        "doc_row_uc15": "| UC15 | 國防/太空（衛星影像）| [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | 政府（FOIA / 檔案）| [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | 智慧城市 | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "fr": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) Expansion Secteur Public",
        "uc_table_header": "| # | Répertoire | Industrie | Modèle | Services AI/ML | État ap-northeast-1 |\n|---|-----------|-----------|--------|----------------|---------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | Défense/Espace | Analyse d'imagerie satellite (détection d'objets, détection de changements, alertes) | Rekognition, SageMaker (optionnel), Bedrock | ✅ Code + tests complets, AWS vérifié |",
        "uc16_row": "| UC16 | `government-archives/` | Gouvernement | Archives publiques / FOIA (OCR, classification, rédaction, suivi délai 20 jours) | Textract ⚠️, Comprehend, Bedrock, OpenSearch (optionnel) | ✅ Code + tests complets, AWS vérifié |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | Ville Intelligente | Analyse géospatiale (normalisation CRS, usage du sol, cartographie des risques, rapport de planification) | Rekognition, SageMaker (optionnel), Bedrock (Nova Lite) | ✅ Code + tests complets, AWS vérifié |",
        "public_sector_note": "> **Conformité Secteur Public** : UC15 cible DoD CC SRG / CSfC / FedRAMP High (migration GovCloud), UC16 cible NARA / FOIA Section 552 / Section 508, UC17 cible Directive INSPIRE / normes OGC.",
        "doc_row_uc14": "| UC14 | Assurance | [📐 Architecture](insurance-claims/docs/architecture.fr.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.fr.md) |",
        "doc_row_uc15": "| UC15 | Défense/Espace (Satellite) | [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | Gouvernement (FOIA / Archives) | [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | Ville Intelligente | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "de": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) Erweiterung für öffentliche Hand",
        "uc_table_header": "| # | Verzeichnis | Branche | Muster | AI/ML-Services | ap-northeast-1 Status |\n|---|-------------|---------|--------|----------------|----------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | Verteidigung/Weltraum | Satellitenbildanalyse (Objekterkennung, Veränderungserkennung, Alarme) | Rekognition, SageMaker (optional), Bedrock | ✅ Code + Tests vollständig, AWS verifiziert |",
        "uc16_row": "| UC16 | `government-archives/` | Regierung | Behördenakten / FOIA (OCR, Klassifikation, Schwärzung, 20-Tage-Frist) | Textract ⚠️, Comprehend, Bedrock, OpenSearch (optional) | ✅ Code + Tests vollständig, AWS verifiziert |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | Smart City | Geospatiale Analyse (CRS-Normalisierung, Landnutzung, Risikokartierung, Planungsbericht) | Rekognition, SageMaker (optional), Bedrock (Nova Lite) | ✅ Code + Tests vollständig, AWS verifiziert |",
        "public_sector_note": "> **Konformität mit öffentlicher Hand**: UC15 adressiert DoD CC SRG / CSfC / FedRAMP High (GovCloud-Migration), UC16 adressiert NARA / FOIA Section 552 / Section 508, UC17 adressiert INSPIRE-Richtlinie / OGC-Standards.",
        "doc_row_uc14": "| UC14 | Versicherung | [📐 Architecture](insurance-claims/docs/architecture.de.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.de.md) |",
        "doc_row_uc15": "| UC15 | Verteidigung/Weltraum (Satellit) | [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | Regierung (FOIA / Archive) | [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | Smart City | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
    "es": {
        "phase2_header": "### Phase 2 (UC6–UC14)",
        "phase7_header": "### Phase 7 (UC15–UC17) Expansión Sector Público",
        "uc_table_header": "| # | Directorio | Industria | Patrón | Servicios AI/ML | Estado ap-northeast-1 |\n|---|-----------|-----------|--------|-----------------|----------------------|",
        "uc15_row": "| UC15 | `defense-satellite/` | Defensa/Espacio | Análisis de imágenes satelitales (detección de objetos, detección de cambios, alertas) | Rekognition, SageMaker (opcional), Bedrock | ✅ Código + pruebas completos, AWS verificado |",
        "uc16_row": "| UC16 | `government-archives/` | Gobierno | Archivos públicos / FOIA (OCR, clasificación, redacción, seguimiento de plazo 20 días) | Textract ⚠️, Comprehend, Bedrock, OpenSearch (opcional) | ✅ Código + pruebas completos, AWS verificado |",
        "uc17_row": "| UC17 | `smart-city-geospatial/` | Ciudad Inteligente | Análisis geoespacial (normalización CRS, uso del suelo, mapeo de riesgos, informe de planificación) | Rekognition, SageMaker (opcional), Bedrock (Nova Lite) | ✅ Código + pruebas completos, AWS verificado |",
        "public_sector_note": "> **Cumplimiento Sector Público**: UC15 apunta a DoD CC SRG / CSfC / FedRAMP High (migración a GovCloud), UC16 apunta a NARA / FOIA Sección 552 / Sección 508, UC17 apunta a Directiva INSPIRE / estándares OGC.",
        "doc_row_uc14": "| UC14 | Seguros | [📐 Architecture](insurance-claims/docs/architecture.es.md) | [🎬 Demo Guide](insurance-claims/docs/demo-guide.es.md) |",
        "doc_row_uc15": "| UC15 | Defensa/Espacio (Satélite) | [📐 Architecture](defense-satellite/docs/uc15-architecture.md) | [🎬 Demo Script](defense-satellite/docs/uc15-demo-script.md) |",
        "doc_row_uc16": "| UC16 | Gobierno (FOIA / Archivos) | [📐 Architecture](government-archives/docs/uc16-architecture.md) | [🎬 Demo Script](government-archives/docs/uc16-demo-script.md) |",
        "doc_row_uc17": "| UC17 | Ciudad Inteligente | [📐 Architecture](smart-city-geospatial/docs/uc17-architecture.md) | [🎬 Demo Script](smart-city-geospatial/docs/uc17-demo-script.md) |",
    },
}


def add_phase7_section(readme_path: Path, trans: dict[str, str]) -> None:
    """Insert Phase 7 table after the Phase 2 region-constraint note,
    and add UC15-17 documentation rows after UC14 row in the documentation table."""
    if not readme_path.exists():
        print(f"MISSING: {readme_path}")
        return

    content = readme_path.read_text()

    # 1) Insert Phase 7 table after the region constraints paragraph (blank line following `> **Region`)
    if "UC15" in content and "defense-satellite" in content:
        # Already has UC15 — skip
        print(f"SKIP (already updated): {readme_path.name}")
        return

    # Find the UC14 row
    if trans["doc_row_uc14"] in content:
        new_section = (
            trans["doc_row_uc14"]
            + "\n"
            + trans["doc_row_uc15"]
            + "\n"
            + trans["doc_row_uc16"]
            + "\n"
            + trans["doc_row_uc17"]
        )
        content = content.replace(trans["doc_row_uc14"], new_section, 1)
    else:
        print(f"WARN: UC14 doc row not found in {readme_path.name}")

    # Find the Phase 2 section - insert Phase 7 table + public sector note after the region constraint note
    # We look for "ap-northeast-1" paragraph (> **Region constraints ...)
    marker = None
    markers = [
        "Rekognition, Comprehend, Bedrock, and Athena",  # en
        "Rekognition, Comprehend, Bedrock, Athena는 ap-northeast-1에서 사용 가능합니다.",  # ko
        "Rekognition, Comprehend, Bedrock, Athena 在 ap-northeast-1 可用。",  # zh-CN/TW
        "Rekognition, Comprehend, Bedrock et Athena sont disponibles dans ap-northeast-1.",  # fr
        "Rekognition, Comprehend, Bedrock und Athena sind in ap-northeast-1 verfügbar.",  # de
        "Rekognition, Comprehend, Bedrock y Athena están disponibles en ap-northeast-1.",  # es
    ]
    for m in markers:
        if m in content:
            marker = m
            break
    if not marker:
        print(f"WARN: region constraint marker not found in {readme_path.name}")
        return

    # Build insertion text
    insert = (
        "\n\n"
        + trans["phase7_header"]
        + "\n\n"
        + trans["uc_table_header"]
        + "\n"
        + trans["uc15_row"]
        + "\n"
        + trans["uc16_row"]
        + "\n"
        + trans["uc17_row"]
        + "\n\n"
        + trans["public_sector_note"]
        + "\n"
    )

    # Find a good insertion point - after the region constraint paragraph which typically ends with ". or 。
    idx = content.find(marker)
    # Search forward for end of paragraph (double newline)
    end_of_para = content.find("\n\n", idx)
    if end_of_para == -1:
        print(f"WARN: end of region paragraph not found in {readme_path.name}")
        return

    content = content[:end_of_para] + insert + content[end_of_para:]
    readme_path.write_text(content)
    print(f"UPDATED: {readme_path.name}")


def main() -> None:
    for locale, trans in LOCALES.items():
        readme = PROJECT_ROOT / f"README.{locale}.md"
        add_phase7_section(readme, trans)


if __name__ == "__main__":
    main()
