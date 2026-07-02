# UC17: Smart City — Geodatenanalyse und Stadtplanung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)
📚 **Dokumentation**: [Architektur](docs/architecture.md) | [Demo-Skript](docs/demo-guide.md) | [Fehlerbehebung](../docs/phase7-troubleshooting.md)

## Überblick

Automatisierte Analysepipeline für Geodaten (GIS) auf Basis von
FSx for ONTAP S3 Access Points. Sie integriert Satellitenbilder, LiDAR und
IoT-Sensordaten für Stadtplanung, Infrastrukturüberwachung und Katastrophenreaktion.

## Anwendungsfall

Kommunen und Stadtplanungsbehörden integrieren Geodaten aus mehreren Quellen,
um die Zustandsüberwachung städtischer Infrastruktur, die Änderungserkennung
und die Bewertung von Katastrophenrisiken zu automatisieren.

### Verarbeitungsablauf

```
FSx for ONTAP (GIS-Datenspeicher — abteilungsbezogene Zugriffskontrolle)
  → S3 Access Point
    → Step-Functions-Workflow
      → Discovery: Erkennung neuer Daten (GeoTIFF, Shapefile, GeoJSON, LAS)
      → Preprocessing: Koordinatensystem-Umwandlung / Normalisierung (EPSG-Vereinheitlichung, EPSG:4326)
      → LandUseClassification: Landnutzungsklassifizierung (ML-Inferenz)
      → ChangeDetection: Zeitreihen-Änderungserkennung (Neubauten, Rückgang von Grünflächen)
      → InfraAssessment: Bewertung der Infrastrukturabnutzung (Straßen, Brücken, LAS-Punktwolken)
      → RiskMapping: Erstellung von Katastrophen-Risikokarten (Hochwasser, Erdbeben, Erdrutsch)
      → ReportGeneration: Erstellung von Stadtplanungsberichten (Bedrock Nova Lite)
```

### Zieldaten

| Datenformat | Beschreibung | Typische Größe |
|-----------|------|-----------|
| GeoTIFF | Luftbilder / Satellitenbilder | 100 MB – 10 GB |
| Shapefile (.shp) | Vektordaten (Straßen, Gebäude, Parzellen) | 1 – 500 MB |
| GeoJSON | Leichtgewichtige Vektordaten | 1 KB – 100 MB |
| LAS / LAZ | LiDAR-Punktwolken (Gelände / Gebäude 3D) | 100 MB – 5 GB |
| GeoPackage (.gpkg) | GIS-Datenbank nach OGC-Standard | 10 MB – 2 GB |

### AWS-Dienste

| Dienst | Verwendung |
|---------|------|
| FSx for ONTAP | Persistenter Speicher für GIS-Daten (abteilungsbezogene NTFS-ACL) |
| S3 Access Points | Datenzugriff von serverlosen Komponenten |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Vorverarbeitung, Koordinatenumwandlung, Metadatenextraktion |
| SageMaker (Batch Transform) | Landnutzungsklassifizierung, ML-Inferenz zur Änderungserkennung (optional) |
| Amazon Rekognition | Objekterkennung aus Luftbildern (Gebäude, Fahrzeuge) |
| Amazon Bedrock Nova Lite | Erstellung von Stadtplanungsberichten in japanischer Sprache |
| DynamoDB | Zeitreihen-Landnutzungshistorie, Änderungserkennung |
| SNS | Warnmeldungen bei Anomalieerkennung |
| CloudWatch | Beobachtbarkeit |

### Eignung für den öffentlichen Sektor

- **Unterstützung der INSPIRE-Richtlinie** (EU-Geodateninfrastruktur)
- **Konformität mit OGC-Standards**: WMS, WFS, WCS, GeoPackage
- **Open Data**: Verarbeitungsergebnisse können auf bürgernahen Portalen veröffentlicht werden
- **Katastrophenreaktion**: Echtzeit-Kartierung der Schadenslage
- **Datensouveränität**: kommunale Daten bleiben innerhalb der Region

### Nutzungsszenarien

| Szenario | Eingabedaten | Ausgabe |
|---------|-----------|------|
| Überwachung der Stadtbegrünung | Satellitenbilder (Zeitreihe) | Bericht über die Veränderung der Grünflächen |
| Erkennung illegaler Müllablagerung | Drohnenbilder | Warnung + Standortinformation |
| Bewertung der Straßenabnutzung | Bilder von Fahrzeugkameras | Karte mit Reparaturprioritäten |
| Hochwasserrisikobewertung | LiDAR + Niederschlagsdaten | Überschwemmungsprognosekarte |
| Unterstützung der Baugenehmigung | Luftbilder + Bauantrag | Bericht zur Abweichungserkennung |

## Verifizierte Ansichten (Screenshots)

### 1. GIS-Datenspeicherung (über S3 Access Point)

Der Bestätigungsbildschirm zur Datenablage aus Sicht eines kommunalen GIS-Sachbearbeiters.
GeoTIFF / Shapefile / LAS werden unter dem Präfix `gis/YYYY/MM/` abgelegt.

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     Inhalt: Auflistung des gis/-Präfixes im S3 AP, gemischte Dateiformate
     Maske: Konto-ID, S3-AP-ARN, aus echten Koordinaten abgeleitete Dateinamen -->
![UC17: Bestätigung der GIS-Datenspeicherung](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Von Bedrock generierter Stadtplanungsbericht (Markdown-Ansicht)

**Kernfunktion von UC17**: Durch die Integration von Landnutzungsverteilung,
Änderungserkennung und Risikobewertung erstellt Bedrock Nova Lite automatisch
einen japanischsprachigen Bericht für kommunale Mitarbeitende.

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     Inhalt: reports/*.md in der S3-Konsole gerendert
     Tatsächlicher Beispielinhalt:
       ### Beobachtungsbericht für kommunale Mitarbeitende
       #### Beachtenswerte Punkte für die Stadtplanung
       Laut den GIS-Daten ist die Landnutzungsverteilung in der Stadt stabil...
       #### Vorrangig zu erwägende Maßnahmen
       1. Hochwasserschutz verstärken ... 2. Erdbebenschutz verstärken ... 3. Schutz vor Hangrutschungen verstärken ...
     Maske: Konto-ID, Kommunenname (nur der Beispielname wird angezeigt) -->
![UC17: von Bedrock generierter Bericht](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. JSON der Katastrophen-Risikokarte

Drei Arten von Risikobewertungen — Hochwasser, Erdbeben und Erdrutsch — werden
in vier Stufen eingeteilt: CRITICAL / HIGH / MEDIUM / LOW.

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     Inhalt: formatierte Ansicht von risk-maps/*.json (level von flood, earthquake, landslide hervorgehoben)
     Maske: Konto-ID -->
![UC17: Katastrophen-Risikokarte](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. Landnutzungsverteilung (JSON)

Die aus den Rekognition-/SageMaker-Inferenzergebnissen abgeleitete Verteilung der Landnutzungsklassen.
Anteile von residential / commercial / forest / water / road usw.

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     Inhalt: Inhalt von landuse/*.json (residential: 0.5, forest: 0.3 usw.)
     Maske: Konto-ID -->
![UC17: Landnutzungsverteilung](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. Visualisierung der Zeitreihen-Änderungen (DynamoDB Explorer)

Tabelle `fsxn-uc17-demo-landuse-history`. Für jede area_id werden vergangene
Landnutzungsverteilungen mit aktuellen Werten verglichen, um change_magnitude zu berechnen.

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     Inhalt: Zeitreihenelemente der landuse-history-Tabelle im DynamoDB Explorer
     Maske: Konto-ID, area_id -->
![UC17: Tabelle der Zeitreihen-Änderungen](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
Durch die Automatisierung der Geodatenanalyse (CRS-Normalisierung, Landnutzungsklassifizierung, Katastrophen-Risikokartierung) unterstützt sie die Entscheidungsfindung in der Stadtplanung.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Verarbeitete Datensätze / Lauf | > 100 files |
| Erfolgsrate der CRS-Normalisierung | > 95% |
| Genauigkeit der Landnutzungsklassifizierung | > 80% |
| Erstellungszeit der Risikokarte | < 10 Min |
| Kosten / Lauf | < $10 |
| Zielquote für Human Review | < 20 % (Bereiche mit unsicherer Klassifizierung) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Bedrock-Analyseberichte, Rekognition-Erkennungsergebnisse, S3-Ausgabe-GeoJSON, CloudWatch Metrics.

## Bereitstellung

### Vorabprüfung

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-Shot-Bereitstellung

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### Manuelle Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Wichtig**: Aktivieren Sie in der Bedrock-Konsole den Modellzugriff für `amazon.nova-lite-v1:0`.

## Verzeichnisstruktur

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS-Normalisierung (EPSG:4326)
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ-Punktwolkenanalyse
│   ├── risk_mapping/handler.py           # Hochwasser-/Erdbeben-/Erdrutschrisiko
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## Links zur AWS-Dokumentation

| Dienst | Dokumentation |
|---------|------------|
| FSx for ONTAP | [Benutzerhandbuch](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Entwicklerhandbuch](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [Entwicklerhandbuch](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [Entwicklerhandbuch](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [Benutzerhandbuch](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Ausrichtung am Well-Architected Framework

| Säule | Ausrichtung |
|----|------|
| Operative Exzellenz | X-Ray, EMF, Verfolgung von Landnutzungsänderungen, Resilienztests |
| Sicherheit | IAM mit geringsten Rechten, KMS, abteilungsbezogene NTFS-ACL, INSPIRE-Konformität |
| Zuverlässigkeit | Step Functions Retry/Catch, CRS-Normalisierung, Resilienztests |
| Leistungseffizienz | GeoTIFF-Kachelung, SageMaker Batch Transform |
| Kostenoptimierung | Serverless, SageMaker Spot, DynamoDB-Zeitreihen |
| Nachhaltigkeit | Inkrementelle Änderungserkennung, Konformität mit OGC-Standards |





---

## Kostenschätzung (monatlicher Näherungswert)

> **Hinweis**: Das Folgende ist eine Schätzung für die Region ap-northeast-1; die tatsächlichen Kosten hängen von der Nutzung ab. Prüfen Sie die aktuellsten Preise mit dem [AWS Pricing Calculator](https://calculator.aws/).

### Serverlose Komponenten (nutzungsbasiert)

| Dienst | Stückpreis | Angenommene Nutzung | Monatlicher Näherungswert |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 Funktionen × 20 datasets/Tag | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/Tag | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/Tag | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/Lauf | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/Abfrage | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/Tag | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/Monat | ~$0.76 |

### Fixkosten (FSx for ONTAP — bestehende Umgebung vorausgesetzt)

| Komponente | Monatlich |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (gemeinsam genutzte bestehende Umgebung) |
| S3 Access Point | Keine zusätzlichen Gebühren (nur S3-API-Gebühren) |

### Gesamtschätzung

| Konfiguration | Monatlicher Näherungswert |
|------|---------|
| Minimalkonfiguration (einmal täglich) | ~$5-15 |
| Standardkonfiguration (stündlich) | ~$15-50 |
| Großkonfiguration (hohe Frequenz + Alarme) | ~$50-150 |

> **Governance Caveat**: Kostenschätzungen sind Näherungswerte und keine garantierten Werte. Die tatsächliche Abrechnung hängt von Nutzungsmustern, Datenvolumen und Region ab.

---

## Lokale Tests

### Prüfung der Voraussetzungen

```bash
# Voraussetzungen prüfen
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (für sam local)
aws sts get-caller-identity  # AWS-Anmeldeinformationen
```

### sam local invoke

```bash
# Build
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

# Discovery-Lambda lokal ausführen
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Mit Überschreibung von Umgebungsvariablen
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit-Tests

```bash
python3 -m pytest tests/ -v
```

Weitere Einzelheiten finden Sie im [Schnellstart für lokale Tests](../docs/local-testing-quick-start.md).

---

## Ausgabebeispiel (Output Sample)

Beispielausgabe der Geodatenanalyse-Pipeline:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **Hinweis**: Das Obige ist eine Beispielausgabe; die tatsächlichen Werte hängen von Umgebung und Eingabedaten ab. Benchmark-Zahlen sind ein Dimensionierungsreferenzwert, keine Service-Grenze.

---

## Governance Note

> Dieses Pattern bietet technische Architekturhinweise. Es stellt keine Rechts-, Compliance- oder Regulierungsberatung dar. Organisationen sollten qualifizierte Fachleute konsultieren.

---

## S3AP Compatibility

Informationen zu Kompatibilitätseinschränkungen, Fehlerbehebung und Auslösemustern für S3 Access Points for FSx for ONTAP finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
