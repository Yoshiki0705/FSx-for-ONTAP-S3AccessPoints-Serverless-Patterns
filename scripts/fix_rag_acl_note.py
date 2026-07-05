#!/usr/bin/env python3
"""Correct the rag-enterprise-files ACL note (review finding).

Original note implied the function reaches ONTAP "from within the VPC", but the
template ships no VpcConfig, and the handler defaults to simulation mode
(`if SIMULATION_MODE or not ONTAP_MANAGEMENT_IP: simulate`). The corrected note
states this accurately.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "solutions" / "flexcache" / "rag-enterprise-files"

OLD = {
    "README.md": "> **ファイルレベル ACL 抽出を使う場合**: 実際の ONTAP 連携で ACL を抽出するには、`OntapManagementIp` と `OntapSecretName` も指定してください（VPC 内から ONTAP REST API へ到達できる必要があります）。",
    "README.en.md": "> **For file-level ACL extraction**: to extract ACLs against a real ONTAP system, also pass `OntapManagementIp` and `OntapSecretName` (the function must reach the ONTAP REST API from within the VPC).",
    "README.ko.md": "> **파일 수준 ACL 추출 시**: 실제 ONTAP 연동으로 ACL을 추출하려면 `OntapManagementIp`와 `OntapSecretName`도 지정하세요 (VPC 내부에서 ONTAP REST API에 도달할 수 있어야 합니다).",
    "README.zh-CN.md": "> **使用文件级 ACL 提取时**: 若要针对真实 ONTAP 提取 ACL，请同时传入 `OntapManagementIp` 与 `OntapSecretName`（函数需能从 VPC 内访问 ONTAP REST API）。",
    "README.zh-TW.md": "> **使用檔案級 ACL 擷取時**: 若要針對真實 ONTAP 擷取 ACL，請同時傳入 `OntapManagementIp` 與 `OntapSecretName`（函式需能從 VPC 內存取 ONTAP REST API）。",
    "README.fr.md": "> **Pour l'extraction d'ACL au niveau fichier** : pour extraire les ACL depuis un système ONTAP réel, passez également `OntapManagementIp` et `OntapSecretName` (la fonction doit joindre l'API REST ONTAP depuis le VPC).",
    "README.de.md": "> **Für die ACL-Extraktion auf Dateiebene**: Um ACLs von einem echten ONTAP-System zu extrahieren, übergeben Sie zusätzlich `OntapManagementIp` und `OntapSecretName` (die Funktion muss die ONTAP-REST-API aus dem VPC erreichen).",
    "README.es.md": "> **Para la extracción de ACL a nivel de archivo**: para extraer ACL de un sistema ONTAP real, pase también `OntapManagementIp` y `OntapSecretName` (la función debe poder alcanzar la API REST de ONTAP desde la VPC).",
}
NEW = {
    "README.md": "> **ファイルレベル ACL 抽出について**: 既定では ACL 抽出はシミュレーションモードで動作します（ONTAP 不要）。実際の ACL を取得するには `OntapManagementIp` / `OntapSecretName` を指定します。ただし本テンプレートは `VpcConfig` を含まないため、プライベートな ONTAP 管理 LIF へ到達するには追加のネットワーク構成が必要です。",
    "README.en.md": "> **About file-level ACL extraction**: by default, ACL extraction runs in simulation mode (no ONTAP required). To extract real ACLs, set `OntapManagementIp` / `OntapSecretName`. Note that this template does not include a `VpcConfig`, so reaching a private ONTAP management LIF requires additional network configuration.",
    "README.ko.md": "> **파일 수준 ACL 추출 안내**: 기본적으로 ACL 추출은 시뮬레이션 모드로 동작합니다(ONTAP 불필요). 실제 ACL을 추출하려면 `OntapManagementIp` / `OntapSecretName`을 지정하세요. 단, 본 템플릿은 `VpcConfig`를 포함하지 않으므로 프라이빗 ONTAP 관리 LIF에 도달하려면 추가 네트워크 구성이 필요합니다.",
    "README.zh-CN.md": "> **关于文件级 ACL 提取**: 默认情况下 ACL 提取以模拟模式运行（无需 ONTAP）。若要提取真实 ACL，请设置 `OntapManagementIp` / `OntapSecretName`。请注意本模板不包含 `VpcConfig`，因此要访问私有 ONTAP 管理 LIF 需要额外的网络配置。",
    "README.zh-TW.md": "> **關於檔案級 ACL 擷取**: 預設情況下 ACL 擷取以模擬模式執行（無需 ONTAP）。若要擷取真實 ACL，請設定 `OntapManagementIp` / `OntapSecretName`。請注意本範本不包含 `VpcConfig`，因此要存取私有 ONTAP 管理 LIF 需要額外的網路設定。",
    "README.fr.md": "> **À propos de l'extraction d'ACL au niveau fichier** : par défaut, l'extraction d'ACL fonctionne en mode simulation (aucun ONTAP requis). Pour extraire des ACL réelles, définissez `OntapManagementIp` / `OntapSecretName`. Notez que ce modèle n'inclut pas de `VpcConfig` ; joindre un LIF de gestion ONTAP privé nécessite donc une configuration réseau supplémentaire.",
    "README.de.md": "> **Zur ACL-Extraktion auf Dateiebene**: Standardmäßig läuft die ACL-Extraktion im Simulationsmodus (kein ONTAP erforderlich). Um echte ACLs zu extrahieren, setzen Sie `OntapManagementIp` / `OntapSecretName`. Beachten Sie, dass diese Vorlage kein `VpcConfig` enthält; das Erreichen eines privaten ONTAP-Management-LIF erfordert daher eine zusätzliche Netzwerkkonfiguration.",
    "README.es.md": "> **Acerca de la extracción de ACL a nivel de archivo**: de forma predeterminada, la extracción de ACL se ejecuta en modo de simulación (sin ONTAP). Para extraer ACL reales, defina `OntapManagementIp` / `OntapSecretName`. Tenga en cuenta que esta plantilla no incluye `VpcConfig`, por lo que alcanzar un LIF de gestión de ONTAP privado requiere configuración de red adicional.",
}


def main() -> int:
    changed = 0
    for fname, old in OLD.items():
        p = D / fname
        text = p.read_text()
        if old in text:
            p.write_text(text.replace(old, NEW[fname]))
            changed += 1
            print(f"corrected {p.relative_to(ROOT)}")
        else:
            print(f"OLD not found (skip) {p.relative_to(ROOT)}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
