#!/usr/bin/env python3
"""Add a concise 'Output Destination' note to UC demo-guide files in
all 7 non-Japanese languages.

Each UC uses one of two output patterns:
- Pattern A (UC1-5): Native FSxN S3AP output via S3AccessPointOutputAlias
- Pattern B (UC9/10/11/12/14): Selectable via OutputDestination parameter

This script inserts a concise language-localized summary after the
existing executive-summary-style content and before the next major section.
Kept short to match the existing demo-guide translations' compact style.
"""

from __future__ import annotations

import sys
from pathlib import Path

# UC → pattern mapping
UC_PATTERNS = {
    "legal-compliance": "A",
    "financial-idp": "A",
    "manufacturing-analytics": "A",
    "media-vfx": "A",
    "healthcare-dicom": "A",
    "autonomous-driving": "B",
    "construction-bim": "B",
    "logistics-ocr": "B",
    "retail-catalog": "B",
    "insurance-claims": "B",
}

# Pattern A = native S3AP output (UC1-5)
# Pattern B = selectable via OutputDestination (UC9/10/11/12/14)

TRANSLATIONS = {
    "en": {
        "A": """## Output Destination: FSxN S3 Access Point (Pattern A)

This UC falls under **Pattern A: Native S3AP Output**
(see `docs/output-destination-patterns.md`).

**Design**: All AI/ML artifacts are written back to the **same FSx ONTAP
volume** as the source data via the FSxN S3 Access Point — no separate
standard S3 bucket is created ("no data movement" pattern).

**CloudFormation parameters**:
- `S3AccessPointAlias`: Input S3 AP Alias
- `S3AccessPointOutputAlias`: Output S3 AP Alias (can be same as input)

See [README.en.md — AWS Specification Constraints](../../README.en.md#aws-specification-constraints-and-workarounds)
for AWS-side limitations and workarounds.

---
""",
        "B": """## Output Destination: Selectable via OutputDestination (Pattern B)

This UC supports the `OutputDestination` parameter (2026-05-10 update,
see `docs/output-destination-patterns.md`).

**Two modes**:

- **STANDARD_S3** (default): AI artifacts go to a new S3 bucket
- **FSXN_S3AP** ("no data movement"): AI artifacts go back to the same
  FSx ONTAP volume via S3 Access Point — visible to SMB/NFS users in
  the existing directory structure

```bash
# FSXN_S3AP mode
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

See [README.en.md — AWS Specification Constraints](../../README.en.md#aws-specification-constraints-and-workarounds)
for AWS-side limitations and workarounds.

---
""",
    },
    "ko": {
        "A": """## 출력 대상: FSxN S3 Access Point (Pattern A)

이 UC는 **Pattern A: Native S3AP Output**에 해당합니다
(`docs/output-destination-patterns.md` 참조).

**설계**: 모든 AI/ML 아티팩트는 FSxN S3 Access Point를 통해 소스 데이터와 **동일한
FSx ONTAP 볼륨**에 다시 씁니다. 별도의 표준 S3 버킷은 생성되지 않습니다
("no data movement" 패턴).

**CloudFormation 파라미터**:
- `S3AccessPointAlias`: 입력용 S3 AP Alias
- `S3AccessPointOutputAlias`: 출력용 S3 AP Alias (입력과 동일 가능)

AWS 사양 제약과 해결 방법은
[README.ko.md — AWS 사양상의 제약](../../README.ko.md#aws-사양상의-제약-및-해결-방법) 참조.

---
""",
        "B": """## 출력 대상: OutputDestination으로 선택 가능 (Pattern B)

이 UC는 `OutputDestination` 파라미터를 지원합니다 (2026-05-10 업데이트,
`docs/output-destination-patterns.md` 참조).

**두 가지 모드**:

- **STANDARD_S3** (기본값): AI 아티팩트가 새 S3 버킷으로 이동
- **FSXN_S3AP** ("no data movement"): AI 아티팩트가 S3 Access Point를 통해
  동일한 FSx ONTAP 볼륨으로 돌아가며, SMB/NFS 사용자가 기존 디렉토리 구조 내에서
  볼 수 있음

```bash
# FSXN_S3AP 모드
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 사양 제약과 해결 방법은
[README.ko.md — AWS 사양상의 제약](../../README.ko.md#aws-사양상의-제약-및-해결-방법) 참조.

---
""",
    },
    "zh-CN": {
        "A": """## 输出目标: FSxN S3 Access Point (Pattern A)

该 UC 属于 **Pattern A: Native S3AP Output**
(参见 `docs/output-destination-patterns.md`)。

**设计**: 所有 AI/ML 工件通过 FSxN S3 Access Point 写回到与源数据**同一的 FSx ONTAP 卷**。
不创建单独的标准 S3 存储桶 ("no data movement" 模式)。

**CloudFormation 参数**:
- `S3AccessPointAlias`: 输入用 S3 AP Alias
- `S3AccessPointOutputAlias`: 输出用 S3 AP Alias (可以与输入相同)

AWS 规格约束和解决方案请参阅
[README.zh-CN.md — AWS 规格约束](../../README.zh-CN.md#aws-规格约束及解决方案)。

---
""",
        "B": """## 输出目标: 通过 OutputDestination 选择 (Pattern B)

该 UC 支持 `OutputDestination` 参数 (2026-05-10 更新,
参见 `docs/output-destination-patterns.md`)。

**两种模式**:

- **STANDARD_S3** (默认): AI 工件进入新的 S3 存储桶
- **FSXN_S3AP** ("no data movement"): AI 工件通过 S3 Access Point 返回同一的
  FSx ONTAP 卷, SMB/NFS 用户可在现有目录结构中查看

```bash
# FSXN_S3AP 模式
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 规格约束和解决方案请参阅
[README.zh-CN.md — AWS 规格约束](../../README.zh-CN.md#aws-规格约束及解决方案)。

---
""",
    },
    "zh-TW": {
        "A": """## 輸出目標: FSxN S3 Access Point (Pattern A)

此 UC 屬於 **Pattern A: Native S3AP Output**
(請參閱 `docs/output-destination-patterns.md`)。

**設計**: 所有 AI/ML 產物透過 FSxN S3 Access Point 寫回與來源資料**相同的 FSx ONTAP 磁碟區**。
不建立獨立的標準 S3 儲存貯體 ("no data movement" 模式)。

**CloudFormation 參數**:
- `S3AccessPointAlias`: 輸入用 S3 AP Alias
- `S3AccessPointOutputAlias`: 輸出用 S3 AP Alias (可以與輸入相同)

AWS 規格約束與解決方案請參閱
[README.zh-TW.md — AWS 規格約束](../../README.zh-TW.md#aws-規格約束及解決方案)。

---
""",
        "B": """## 輸出目標: 透過 OutputDestination 選擇 (Pattern B)

此 UC 支援 `OutputDestination` 參數 (2026-05-10 更新,
請參閱 `docs/output-destination-patterns.md`)。

**兩種模式**:

- **STANDARD_S3** (預設): AI 產物進入新的 S3 儲存貯體
- **FSXN_S3AP** ("no data movement"): AI 產物透過 S3 Access Point 返回相同的
  FSx ONTAP 磁碟區, SMB/NFS 使用者可在現有目錄結構中檢視

```bash
# FSXN_S3AP 模式
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 規格約束與解決方案請參閱
[README.zh-TW.md — AWS 規格約束](../../README.zh-TW.md#aws-規格約束及解決方案)。

---
""",
    },
    "fr": {
        "A": """## Destination de sortie : FSxN S3 Access Point (Pattern A)

Ce UC relève du **Pattern A : Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : tous les artefacts IA/ML sont écrits via le FSxN S3 Access Point
sur le **même volume FSx ONTAP** que les données source. Aucun bucket S3 standard
séparé n'est créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias d'entrée
- `S3AccessPointOutputAlias` : S3 AP Alias de sortie (peut être identique à l'entrée)

Pour les contraintes et solutions de contournement AWS, voir
[README.fr.md — Contraintes de spécification AWS](../../README.fr.md#contraintes-de-spécification-aws-et-solutions-de-contournement).

---
""",
        "B": """## Destination de sortie : sélectionnable via OutputDestination (Pattern B)

Ce UC prend en charge le paramètre `OutputDestination` (mise à jour 2026-05-10,
voir `docs/output-destination-patterns.md`).

**Deux modes** :

- **STANDARD_S3** (par défaut) : les artefacts IA vont vers un nouveau bucket S3
- **FSXN_S3AP** ("no data movement") : les artefacts IA retournent sur le même
  volume FSx ONTAP via S3 Access Point, visibles pour les utilisateurs SMB/NFS
  dans la structure de répertoires existante

```bash
# Mode FSXN_S3AP
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

Pour les contraintes et solutions de contournement AWS, voir
[README.fr.md — Contraintes de spécification AWS](../../README.fr.md#contraintes-de-spécification-aws-et-solutions-de-contournement).

---
""",
    },
    "de": {
        "A": """## Ausgabeziel: FSxN S3 Access Point (Pattern A)

Dieser UC gehört zum **Pattern A: Native S3AP Output**
(siehe `docs/output-destination-patterns.md`).

**Design**: Alle AI/ML-Artefakte werden über den FSxN S3 Access Point auf
**dasselbe FSx ONTAP Volume** wie die Quelldaten zurückgeschrieben. Kein separater
Standard-S3-Bucket wird erstellt ("no data movement"-Pattern).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: Eingabe-S3-AP-Alias
- `S3AccessPointOutputAlias`: Ausgabe-S3-AP-Alias (kann identisch mit Eingabe sein)

AWS-Spezifikationsbeschränkungen und Workarounds siehe
[README.de.md — AWS-Spezifikationsbeschränkungen](../../README.de.md#aws-spezifikationsbeschränkungen-und-workarounds).

---
""",
        "B": """## Ausgabeziel: auswählbar über OutputDestination (Pattern B)

Dieser UC unterstützt den `OutputDestination`-Parameter (Update vom 2026-05-10,
siehe `docs/output-destination-patterns.md`).

**Zwei Modi**:

- **STANDARD_S3** (Standard): AI-Artefakte gehen in einen neuen S3-Bucket
- **FSXN_S3AP** ("no data movement"): AI-Artefakte gehen über den S3 Access Point
  zurück auf dasselbe FSx ONTAP Volume, sichtbar für SMB/NFS-Benutzer in der
  bestehenden Verzeichnisstruktur

```bash
# FSXN_S3AP-Modus
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS-Spezifikationsbeschränkungen und Workarounds siehe
[README.de.md — AWS-Spezifikationsbeschränkungen](../../README.de.md#aws-spezifikationsbeschränkungen-und-workarounds).

---
""",
    },
    "es": {
        "A": """## Destino de salida: FSxN S3 Access Point (Pattern A)

Este UC se clasifica como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: todos los artefactos de IA/ML se escriben a través del FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los datos fuente. No se crea un bucket S3
estándar separado (patrón "no data movement").

**Parámetros CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias de salida (puede ser igual a la entrada)

Para restricciones de especificación de AWS y soluciones alternativas, consulte
[README.es.md — Restricciones de especificación de AWS](../../README.es.md#restricciones-de-especificación-de-aws-y-soluciones-alternativas).

---
""",
        "B": """## Destino de salida: seleccionable mediante OutputDestination (Pattern B)

Este UC admite el parámetro `OutputDestination` (actualización 2026-05-10,
consulte `docs/output-destination-patterns.md`).

**Dos modos**:

- **STANDARD_S3** (predeterminado): los artefactos de IA van a un nuevo bucket S3
- **FSXN_S3AP** ("no data movement"): los artefactos de IA regresan al mismo
  volumen FSx ONTAP mediante S3 Access Point, visibles para usuarios SMB/NFS en
  la estructura de directorios existente

```bash
# Modo FSXN_S3AP
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

Para restricciones de especificación de AWS y soluciones alternativas, consulte
[README.es.md — Restricciones de especificación de AWS](../../README.es.md#restricciones-de-especificación-de-aws-y-soluciones-alternativas).

---
""",
    },
}

# Marker to insert before — use a common "Executive Summary" reference or similar
# Most demo-guide translations have a structure like:
#   # Title
#   🌐 Language switcher
#   ## Executive Summary
#   ...
#   ---
#   ## Workflow (or similar next major section)
#
# We insert the new section right BEFORE '## Workflow' or '## Storyboard'

LANG_INSERT_MARKERS = {
    "en": ["## Storyboard", "## Workflow", "## Demo Scenario", "## Target Audience"],
    "ko": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
    "zh-CN": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
    "zh-TW": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
    "fr": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
    "de": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
    "es": ["## Workflow", "## Storyboard", "## Demo Scenario", "## Target Audience"],
}


def patch_file(path: Path, lang_code: str, pattern_type: str) -> bool:
    text = path.read_text()
    section = TRANSLATIONS[lang_code][pattern_type]

    # Check if already patched (look for key marker phrase unique to the section)
    unique_markers = {
        "A": [
            "Pattern A",
            "S3AccessPointOutputAlias",
        ],
        "B": [
            "Pattern B",
            "OutputDestination",
        ],
    }
    if all(m in text for m in unique_markers[pattern_type]):
        print(f"ALREADY PATCHED: {path}")
        return False

    # Find insertion point
    markers = LANG_INSERT_MARKERS[lang_code]
    inserted = False
    for marker in markers:
        if marker in text:
            new_text = text.replace(marker, section + marker, 1)
            path.write_text(new_text)
            print(f"PATCHED: {path} (before '{marker}')")
            inserted = True
            break
    if not inserted:
        print(f"NO MARKER FOUND in {path}, skipping")
        return False
    return True


def main() -> int:
    total = 0
    for uc_dir, pattern in UC_PATTERNS.items():
        for lang in ("en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"):
            path = Path(f"{uc_dir}/docs/demo-guide.{lang}.md")
            if not path.exists():
                print(f"MISSING: {path}")
                continue
            if patch_file(path, lang, pattern):
                total += 1
    print(f"\nTotal modified: {total}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
