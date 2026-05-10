#!/usr/bin/env python3
"""Update 7 non-Japanese README files to reflect UC1-5 OutputDestination unification.

Changes the bullet point and table rows for UC1-5 in the "Per-UC Output
Destination Constraints" section to indicate they now support both
OutputDestination (new) and S3AccessPointOutputAlias (legacy).
"""

from __future__ import annotations

import sys
from pathlib import Path


# For each language, the OLD and NEW versions of UC1-5 rows
UPDATES = {
    "en": {
        # Bullet list update
        "bullet_old": '- **🟢 UC1-5**: existing `S3AccessPointOutputAlias` parameter supports FSxN S3AP output (designed this way from day 1)\n- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` switch (STANDARD_S3 ⇄ FSXN_S3AP), implemented 2026-05-10. UC11/14 verified on AWS, UC9/10/12 unit-tested only',
        "bullet_new": '- **🟢 UC1-5** (Pattern A, updated 2026-05-11): `S3AccessPointOutputAlias` (legacy, optional) + newly-added `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` are supported. Default `OutputDestination=FSXN_S3AP` preserves existing behavior\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, implemented 2026-05-10): `OutputDestination` switch (STANDARD_S3 ⇄ FSXN_S3AP). Default `OutputDestination=STANDARD_S3`. UC11/14 verified on AWS, UC9/10/12 unit-tested only',
        # Table rows
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` parameter | Contract metadata / audit logs |",
             "| UC1 legal-compliance | S3AP | S3AP (existing) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Contract metadata / audit logs |"),
            ("| UC2 financial-idp | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Invoice OCR results |",
             "| UC2 financial-idp | S3AP | S3AP (existing) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Invoice OCR results |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Inspection results / anomaly detection |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (existing) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Inspection results / anomaly detection |"),
            ("| UC4 media-vfx | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Render metadata |",
             "| UC4 media-vfx | S3AP | S3AP (existing) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Render metadata |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | DICOM metadata / de-identification |",
             "| UC5 healthcare-dicom | S3AP | S3AP (existing) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM metadata / de-identification |"),
        ],
    },
    "ko": {
        "bullet_old": '- **🟢 UC1-5**: 기존 `S3AccessPointOutputAlias` 파라미터로 FSxN S3AP 출력 지원 (처음부터 이렇게 설계됨)\n- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 전환 메커니즘 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 구현. UC11/14는 AWS 실증, UC9/10/12는 단위 테스트만 완료',
        "bullet_new": '- **🟢 UC1-5** (Pattern A, 2026-05-11 업데이트): `S3AccessPointOutputAlias` (legacy, optional) + 신규 추가된 `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` 지원. 기본값 `OutputDestination=FSXN_S3AP`로 기존 동작 유지\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, 2026-05-10 구현): `OutputDestination` 전환 메커니즘 (STANDARD_S3 ⇄ FSXN_S3AP). 기본값 `OutputDestination=STANDARD_S3`. UC11/14는 AWS 실증, UC9/10/12는 단위 테스트만 완료',
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` 파라미터 | 계약 메타데이터 / 감사 로그 |",
             "| UC1 legal-compliance | S3AP | S3AP (기존) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 계약 메타데이터 / 감사 로그 |"),
            ("| UC2 financial-idp | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 청구서 OCR 결과 |",
             "| UC2 financial-idp | S3AP | S3AP (기존) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 청구서 OCR 결과 |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 검사 결과 / 이상 감지 |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (기존) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 검사 결과 / 이상 감지 |"),
            ("| UC4 media-vfx | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 렌더링 메타데이터 |",
             "| UC4 media-vfx | S3AP | S3AP (기존) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 렌더링 메타데이터 |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | DICOM 메타데이터 / 익명화 결과 |",
             "| UC5 healthcare-dicom | S3AP | S3AP (기존) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM 메타데이터 / 익명화 결과 |"),
        ],
    },
    "zh-CN": {
        "bullet_old": '- **🟢 UC1-5**: 现有的 `S3AccessPointOutputAlias` 参数支持 FSxN S3AP 输出 (从一开始就这样设计)\n- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 切换机制 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 实现。UC11/14 已在 AWS 上验证, UC9/10/12 仅完成单元测试',
        "bullet_new": '- **🟢 UC1-5** (Pattern A, 2026-05-11 更新): `S3AccessPointOutputAlias` (legacy, optional) + 新增的 `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` 支持。默认 `OutputDestination=FSXN_S3AP` 保持现有行为\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, 2026-05-10 实现): `OutputDestination` 切换机制 (STANDARD_S3 ⇄ FSXN_S3AP)。默认 `OutputDestination=STANDARD_S3`。UC11/14 已在 AWS 上验证, UC9/10/12 仅完成单元测试',
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` 参数 | 合同元数据 / 审计日志 |",
             "| UC1 legal-compliance | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 合同元数据 / 审计日志 |"),
            ("| UC2 financial-idp | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 发票 OCR 结果 |",
             "| UC2 financial-idp | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 发票 OCR 结果 |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 检查结果 / 异常检测 |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 检查结果 / 异常检测 |"),
            ("| UC4 media-vfx | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 渲染元数据 |",
             "| UC4 media-vfx | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 渲染元数据 |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | DICOM 元数据 / 匿名化结果 |",
             "| UC5 healthcare-dicom | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM 元数据 / 匿名化结果 |"),
        ],
    },
    "zh-TW": {
        "bullet_old": '- **🟢 UC1-5**: 現有的 `S3AccessPointOutputAlias` 參數支援 FSxN S3AP 輸出 (從一開始就這樣設計)\n- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 切換機制 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 實作。UC11/14 已在 AWS 上驗證, UC9/10/12 僅完成單元測試',
        "bullet_new": '- **🟢 UC1-5** (Pattern A, 2026-05-11 更新): `S3AccessPointOutputAlias` (legacy, optional) + 新增的 `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` 支援。預設 `OutputDestination=FSXN_S3AP` 維持現有行為\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, 2026-05-10 實作): `OutputDestination` 切換機制 (STANDARD_S3 ⇄ FSXN_S3AP)。預設 `OutputDestination=STANDARD_S3`。UC11/14 已在 AWS 上驗證, UC9/10/12 僅完成單元測試',
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` 參數 | 合約中繼資料 / 稽核日誌 |",
             "| UC1 legal-compliance | S3AP | S3AP (現有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 合約中繼資料 / 稽核日誌 |"),
            ("| UC2 financial-idp | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 發票 OCR 結果 |",
             "| UC2 financial-idp | S3AP | S3AP (現有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 發票 OCR 結果 |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 檢查結果 / 異常偵測 |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (現有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 檢查結果 / 異常偵測 |"),
            ("| UC4 media-vfx | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 渲染中繼資料 |",
             "| UC4 media-vfx | S3AP | S3AP (現有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 渲染中繼資料 |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | DICOM 中繼資料 / 匿名化結果 |",
             "| UC5 healthcare-dicom | S3AP | S3AP (現有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM 中繼資料 / 匿名化結果 |"),
        ],
    },
    "fr": {
        "bullet_old": "- **🟢 UC1-5** : le paramètre existant `S3AccessPointOutputAlias` prend en charge la sortie FSxN S3AP (conçu ainsi dès le début)\n- **🟢🆕 UC9/10/11/12/14** : mécanisme de commutation `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP), implémenté le 2026-05-10. UC11/14 vérifiés sur AWS, UC9/10/12 uniquement en tests unitaires",
        "bullet_new": "- **🟢 UC1-5** (Pattern A, mise à jour 2026-05-11) : `S3AccessPointOutputAlias` (legacy, optionnel) + nouveaux paramètres `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` pris en charge. Par défaut `OutputDestination=FSXN_S3AP` préserve le comportement existant\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, implémenté le 2026-05-10) : mécanisme de commutation `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP). Par défaut `OutputDestination=STANDARD_S3`. UC11/14 vérifiés sur AWS, UC9/10/12 uniquement en tests unitaires",
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (existant) | paramètre `S3AccessPointOutputAlias` | Métadonnées de contrat / journaux d'audit |",
             "| UC1 legal-compliance | S3AP | S3AP (existant) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Métadonnées de contrat / journaux d'audit |"),
            ("| UC2 financial-idp | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Résultats OCR de factures |",
             "| UC2 financial-idp | S3AP | S3AP (existant) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Résultats OCR de factures |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Résultats d'inspection / détection d'anomalies |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (existant) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Résultats d'inspection / détection d'anomalies |"),
            ("| UC4 media-vfx | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Métadonnées de rendu |",
             "| UC4 media-vfx | S3AP | S3AP (existant) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Métadonnées de rendu |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Métadonnées DICOM / anonymisation |",
             "| UC5 healthcare-dicom | S3AP | S3AP (existant) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Métadonnées DICOM / anonymisation |"),
        ],
    },
    "de": {
        "bullet_old": "- **🟢 UC1-5**: Bestehender `S3AccessPointOutputAlias`-Parameter unterstützt FSxN S3AP-Ausgabe (von Anfang an so konzipiert)\n- **🟢🆕 UC9/10/11/12/14**: `OutputDestination`-Schaltmechanismus (STANDARD_S3 ⇄ FSXN_S3AP), implementiert am 2026-05-10. UC11/14 auf AWS verifiziert, UC9/10/12 nur Unit-Tests",
        "bullet_new": "- **🟢 UC1-5** (Pattern A, aktualisiert 2026-05-11): `S3AccessPointOutputAlias` (legacy, optional) + neu hinzugefügte `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` unterstützt. Standard `OutputDestination=FSXN_S3AP` bewahrt bestehendes Verhalten\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, implementiert am 2026-05-10): `OutputDestination`-Schaltmechanismus (STANDARD_S3 ⇄ FSXN_S3AP). Standard `OutputDestination=STANDARD_S3`. UC11/14 auf AWS verifiziert, UC9/10/12 nur Unit-Tests",
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias`-Parameter | Vertragsmetadaten / Audit-Logs |",
             "| UC1 legal-compliance | S3AP | S3AP (bestehend) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Vertragsmetadaten / Audit-Logs |"),
            ("| UC2 financial-idp | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Rechnungs-OCR-Ergebnisse |",
             "| UC2 financial-idp | S3AP | S3AP (bestehend) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Rechnungs-OCR-Ergebnisse |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Inspektionsergebnisse / Anomalieerkennung |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (bestehend) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Inspektionsergebnisse / Anomalieerkennung |"),
            ("| UC4 media-vfx | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Rendering-Metadaten |",
             "| UC4 media-vfx | S3AP | S3AP (bestehend) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Rendering-Metadaten |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | DICOM-Metadaten / Anonymisierung |",
             "| UC5 healthcare-dicom | S3AP | S3AP (bestehend) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM-Metadaten / Anonymisierung |"),
        ],
    },
    "es": {
        "bullet_old": "- **🟢 UC1-5**: el parámetro existente `S3AccessPointOutputAlias` admite salida FSxN S3AP (diseñado así desde el principio)\n- **🟢🆕 UC9/10/11/12/14**: mecanismo de conmutación `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP), implementado el 2026-05-10. UC11/14 verificados en AWS, UC9/10/12 solo pruebas unitarias",
        "bullet_new": "- **🟢 UC1-5** (Pattern A, actualizado 2026-05-11): `S3AccessPointOutputAlias` (legacy, opcional) + nuevos parámetros `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` admitidos. Por defecto `OutputDestination=FSXN_S3AP` preserva el comportamiento existente\n- **🟢🆕 UC9/10/11/12/14** (Pattern B, implementado el 2026-05-10): mecanismo de conmutación `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP). Por defecto `OutputDestination=STANDARD_S3`. UC11/14 verificados en AWS, UC9/10/12 solo pruebas unitarias",
        "table_updates": [
            ("| UC1 legal-compliance | S3AP | S3AP (existente) | parámetro `S3AccessPointOutputAlias` | Metadatos de contratos / registros de auditoría |",
             "| UC1 legal-compliance | S3AP | S3AP (existente) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Metadatos de contratos / registros de auditoría |"),
            ("| UC2 financial-idp | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Resultados OCR de facturas |",
             "| UC2 financial-idp | S3AP | S3AP (existente) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Resultados OCR de facturas |"),
            ("| UC3 manufacturing-analytics | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Resultados de inspección / detección de anomalías |",
             "| UC3 manufacturing-analytics | S3AP | S3AP (existente) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Resultados de inspección / detección de anomalías |"),
            ("| UC4 media-vfx | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Metadatos de renderizado |",
             "| UC4 media-vfx | S3AP | S3AP (existente) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Metadatos de renderizado |"),
            ("| UC5 healthcare-dicom | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Metadatos DICOM / anonimización |",
             "| UC5 healthcare-dicom | S3AP | S3AP (existente) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | Metadatos DICOM / anonimización |"),
        ],
    },
}


def patch(path: Path, lang_code: str) -> int:
    text = path.read_text()
    u = UPDATES[lang_code]

    count = 0

    # Apply bullet replacement
    if u["bullet_old"] in text:
        text = text.replace(u["bullet_old"], u["bullet_new"], 1)
        count += 1
    elif u["bullet_new"] in text:
        pass  # already patched
    else:
        print(f"BULLET NOT FOUND in {path}")

    # Apply table row replacements
    for old_row, new_row in u["table_updates"]:
        if old_row in text:
            text = text.replace(old_row, new_row, 1)
            count += 1
        elif new_row in text:
            pass  # already patched

    if count == 0:
        print(f"ALREADY PATCHED: {path}")
        return 0

    path.write_text(text)
    print(f"PATCHED {count} sections in {path}")
    return count


def main() -> int:
    files = [
        ("README.en.md", "en"),
        ("README.ko.md", "ko"),
        ("README.zh-CN.md", "zh-CN"),
        ("README.zh-TW.md", "zh-TW"),
        ("README.fr.md", "fr"),
        ("README.de.md", "de"),
        ("README.es.md", "es"),
    ]
    total = 0
    for filename, lang in files:
        path = Path(filename)
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        total += patch(path, lang)
    print(f"\nTotal sections updated: {total}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
