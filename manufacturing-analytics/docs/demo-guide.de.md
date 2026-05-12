# IoT-Sensor-Anomalieerkennung und Qualitätsprüfung — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt einen Workflow zur automatischen Erkennung von Anomalien aus IoT-Sensordaten von Fertigungslinien und zur Erstellung von Qualitätsprüfberichten.

**Kernbotschaft der Demo**: Automatische Erkennung von Anomaliemustern in Sensordaten zur Früherkennung von Qualitätsproblemen und vorausschauenden Wartung.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Fertigungsabteilungsleiter / Qualitätskontrollingenieur |
| **Tägliche Aufgaben** | Überwachung der Produktionslinie, Qualitätsprüfung, Anlagenwartungsplanung |
| **Herausforderung** | Übersehen von Sensoranomalien, fehlerhafte Produkte gelangen in nachgelagerte Prozesse |
| **Erwartete Ergebnisse** | Früherkennung von Anomalien und Visualisierung von Qualitätstrends |

### Persona: Herr Suzuki (Qualitätskontrollingenieur)

- Überwacht 100+ Sensoren in 5 Fertigungslinien
- Schwellenwertbasierte Alarme erzeugen viele Fehlalarme, echte Anomalien werden oft übersehen
- „Ich möchte nur statistisch signifikante Anomalien erkennen"

---

## Demo Scenario: Batch-Analyse zur Sensoranomalieerkennung

### Gesamtübersicht des Workflows

```
Sensordaten         Datenerfassung    Anomalieerkennung    Qualitätsbericht
(CSV/Parquet)  →   Vorverarbeitung  →  Statistische    →   AI-Generierung
                   Normalisierung      Analyse
                                      (Ausreißererkennung)
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Zusammenfassung der Erzählung**:
> Täglich werden große Datenmengen von 100+ Sensoren in Fertigungslinien generiert. Einfache Schwellenwertalarme erzeugen viele Fehlalarme und bergen das Risiko, echte Anomalien zu übersehen.

**Key Visual**: Zeitreihengrafik der Sensordaten, Situation mit übermäßigen Alarmen

### Section 2: Data Ingestion (0:45–1:30)

**Zusammenfassung der Erzählung**:
> Wenn Sensordaten auf dem Dateiserver gespeichert werden, wird automatisch die Analysepipeline gestartet.

**Key Visual**: Dateiablage → Workflow-Start

### Section 3: Anomaly Detection (1:30–2:30)

**Zusammenfassung der Erzählung**:
> Berechnung von Anomalie-Scores für jeden Sensor mit statistischen Methoden (gleitender Durchschnitt, Standardabweichung, IQR). Korrelationsanalyse mehrerer Sensoren wird ebenfalls durchgeführt.

**Key Visual**: Ausführung des Anomalieerkennungsalgorithmus, Heatmap der Anomalie-Scores

### Section 4: Quality Inspection (2:30–3:45)

**Zusammenfassung der Erzählung**:
> Analyse der erkannten Anomalien aus Qualitätsprüfungsperspektive. Identifizierung, in welcher Linie und in welchem Prozess Probleme auftreten.

**Key Visual**: Athena-Abfrageergebnisse — Anomalieverteilung nach Linie und Prozess

### Section 5: Report & Action (3:45–5:00)

**Zusammenfassung der Erzählung**:
> AI generiert einen Qualitätsprüfbericht. Präsentation von Kandidaten für Grundursachen von Anomalien und empfohlenen Maßnahmen.

**Key Visual**: AI-generierter Qualitätsbericht (Anomalie-Zusammenfassung + empfohlene Maßnahmen)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Sensordatei-Liste | Section 1 |
| 2 | Workflow-Startbildschirm | Section 2 |
| 3 | Fortschritt der Anomalieerkennung | Section 3 |
| 4 | Abfrageergebnisse der Anomalieverteilung | Section 4 |
| 5 | AI-Qualitätsprüfbericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Schwellenwertalarme übersehen echte Anomalien" |
| Ingestion | 0:45–1:30 | „Analyse beginnt automatisch bei Datenspeicherung" |
| Detection | 1:30–2:30 | „Nur statistisch signifikante Anomalien mit statistischen Methoden erkennen" |
| Inspection | 2:30–3:45 | „Problemstellen auf Linien- und Prozessebene identifizieren" |
| Report | 3:45–5:00 | „AI präsentiert Kandidaten für Grundursachen und Gegenmaßnahmen" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Normale Sensordaten (5 Linien × 7 Tage) | Baseline |
| 2 | Temperaturanomaliedaten (2 Fälle) | Anomalieerkennungs-Demo |
| 3 | Vibrationsanomaliedaten (3 Fälle) | Korrelationsanalyse-Demo |
| 4 | Qualitätsverschlechterungsmuster (1 Fall) | Berichtsgenerierungs-Demo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Generierung von Beispiel-Sensordaten | 3 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahme | 2 Stunden |
| Erstellung des Erzählungsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Echtzeit-Streaming-Analyse
- Automatische Generierung von vorausschauenden Wartungsplänen
- Integration mit Digital Twin

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Data Preprocessor) | Sensordaten-Normalisierung und Vorverarbeitung |
| Lambda (Anomaly Detector) | Statistische Anomalieerkennung |
| Lambda (Report Generator) | Qualitätsberichtsgenerierung durch Bedrock |
| Amazon Athena | Aggregation und Analyse von Anomaliedaten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Unzureichende Datenmenge | Verwendung vorab generierter Daten |
| Unzureichende Erkennungsgenauigkeit | Anzeige von Ergebnissen mit angepassten Parametern |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über OutputDestination: FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics ist als **Pattern A: Native S3AP Output** klassifiziert
(siehe `docs/output-destination-patterns.md`).

**Design**: Sensordatenanalyseergebnisse, Anomalieerkennungsberichte und Bildprüfungsergebnisse werden alle über FSxN S3 Access Point
in **dasselbe FSx ONTAP Volume** wie die ursprünglichen Sensor-CSV- und Prüfungsbilder zurückgeschrieben. Standard-S3-Buckets werden
nicht erstellt („no data movement"-Muster).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: S3 AP Alias zum Lesen von Eingabedaten
- `S3AccessPointOutputAlias`: S3 AP Alias zum Schreiben von Ausgaben (kann mit Eingabe identisch sein)

**Deployment-Beispiel**:
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (andere erforderliche Parameter)
```

**Sichtbarkeit für SMB/NFS-Benutzer**:
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # Ursprüngliche Sensordaten
  └── analysis/2026/05/                 # AI-Anomalieerkennungsergebnisse (im selben Volume)
      └── line_A_report.json
```

Für AWS-Spezifikationsbeschränkungen siehe
[Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
und [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verifizierte UI/UX-Screenshots

Gemäß der gleichen Richtlinie wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14 werden **UI/UX-Bildschirme, die Endbenutzer tatsächlich
in ihrer täglichen Arbeit sehen**, als Ziel betrachtet. Technische Ansichten (Step Functions-Grafik, CloudFormation-
Stack-Ereignisse usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC3 Step Functions-Grafik, erfolgreiche Lambda-Ausführung bestätigt)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC3 Step Functions Graph view (SUCCEEDED)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus jedes Lambda / Parallel / Map-Status
farblich visualisiert.

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-succeeded.png)

![UC3 Step Functions Graph (erweiterte Ansicht)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-expanded.png)

![UC3 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (metrics/, anomalies/, reports/)
- Athena-Abfrageergebnisse (IoT-Sensoranomalieerkennung)
- Rekognition-Qualitätsprüfungs-Bildlabels
- Fertigungsqualitäts-Zusammenfassungsbericht

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - Voraussetzungen mit `bash scripts/verify_phase7_prerequisites.sh` prüfen (gemeinsame VPC/S3 AP vorhanden)
   - Lambda-Paket mit `UC=manufacturing-analytics bash scripts/package_generic_uc.sh`
   - Deployment mit `bash scripts/deploy_generic_ucs.sh UC3`

2. **Beispieldatenablage**:
   - Beispieldateien über S3 AP Alias in `sensors/`-Präfix hochladen
   - Step Functions `fsxn-manufacturing-analytics-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Ausgabe-Bucket `fsxn-manufacturing-analytics-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierungsverarbeitung**:
   - Automatische Maskierung mit `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo`
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - Löschen mit `bash scripts/cleanup_generic_ucs.sh UC3`
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
