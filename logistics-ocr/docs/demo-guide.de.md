# Lieferschein OCR & Bestandsanalyse — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt die OCR-Verarbeitung von Lieferscheinen und eine Bestandsanalyse-Pipeline. Papierbasierte Lieferscheine werden digitalisiert und Warenein- und -ausgangsdaten automatisch aggregiert und analysiert.

**Kernbotschaft der Demo**: Automatische Digitalisierung von Lieferscheinen zur Unterstützung der Echtzeit-Bestandsüberwachung und Bedarfsprognose.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Logistikmanager / Lagerverwalter |
| **Tägliche Aufgaben** | Warenein- und -ausgangsverwaltung, Bestandsprüfung, Versandkoordination |
| **Herausforderungen** | Verzögerungen und Fehler durch manuelle Eingabe von Papierbelegen |
| **Erwartete Ergebnisse** | Automatisierung der Belegverarbeitung und Bestandstransparenz |

### Persona: Herr Saito (Logistikmanager)

- Verarbeitet täglich 500+ Lieferscheine
- Bestandsinformationen sind aufgrund manueller Eingabeverzögerungen stets veraltet
- „Ich möchte, dass gescannte Belege direkt im Bestand reflektiert werden"

---

## Demo Scenario: Batch-Verarbeitung von Lieferscheinen

### Gesamtworkflow-Übersicht

```
Lieferscheine        OCR-Verarbeitung   Datenstrukturierung   Bestandsanalyse
(Scan-Bilder)    →   Textextraktion  →  Feld-Mapping      →   Aggregationsberichte
                                                              Bedarfsprognose
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Über 500 Lieferscheine täglich. Manuelle Eingabe verzögert die Aktualisierung der Bestandsinformationen und erhöht das Risiko von Fehlbeständen oder Überbeständen.

**Key Visual**: Große Mengen gescannter Lieferscheinbilder, Visualisierung manueller Eingabeverzögerungen

### Section 2: Scan & Upload (0:45–1:30)

**Narration (Zusammenfassung)**:
> Einfach gescannte Lieferscheinbilder in einen Ordner ablegen – die OCR-Pipeline startet automatisch.

**Key Visual**: Upload von Lieferscheinbildern → Workflow-Start

### Section 3: OCR Processing (1:30–2:30)

**Narration (Zusammenfassung)**:
> OCR extrahiert Text aus Lieferscheinen, KI mappt automatisch Felder wie Artikelname, Menge, Empfänger, Datum usw.

**Key Visual**: OCR-Verarbeitung läuft, Feldextraktionsergebnisse

### Section 4: Inventory Analysis (2:30–3:45)

**Narration (Zusammenfassung)**:
> Extrahierte Daten werden mit der Bestandsdatenbank abgeglichen. Warenein- und -ausgänge werden automatisch aggregiert und der Bestand aktualisiert.

**Key Visual**: Bestandsaggregationsergebnisse, Warenein- und -ausgangstrends nach Artikel

### Section 5: Demand Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> KI generiert einen Bestandsanalysebericht. Zeigt Lagerumschlagsrate, Artikel mit Fehlbestandsrisiko und Bestellempfehlungen.

**Key Visual**: KI-generierter Bestandsbericht (Bestandszusammenfassung + Bestellempfehlungen)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Liste gescannter Lieferscheinbilder | Section 1 |
| 2 | Upload & Pipeline-Start | Section 2 |
| 3 | OCR-Extraktionsergebnisse | Section 3 |
| 4 | Bestandsaggregations-Dashboard | Section 4 |
| 5 | KI-Bestandsanalysebericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Bestandsinformationen sind durch manuelle Eingabeverzögerungen stets veraltet" |
| Upload | 0:45–1:30 | „Automatische Verarbeitung startet allein durch Ablegen der Scans" |
| OCR | 1:30–2:30 | „KI erkennt und strukturiert Lieferscheinfelder automatisch" |
| Analysis | 2:30–3:45 | „Warenein- und -ausgänge werden automatisch aggregiert und Bestand sofort aktualisiert" |
| Report | 3:45–5:00 | „KI zeigt Fehlbestandsrisiken und Bestellempfehlungen" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Wareneingangsbelege (10 Bilder) | OCR-Verarbeitungsdemo |
| 2 | Warenausgangsbelege (10 Bilder) | Bestandsreduktionsdemo |
| 3 | Handschriftliche Belege (3 Bilder) | OCR-Genauigkeitsdemo |
| 4 | Bestandsstammdaten | Abgleichsdemo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispiel-Lieferscheinbildern | 2 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahmen erstellen | 2 Stunden |
| Narrationsskript erstellen | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Echtzeit-Belegverarbeitung (Kameraintegration)
- WMS-Systemintegration
- Integration von Bedarfsprognosemodellen

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (OCR Processor) | Lieferschein-Textextraktion mit Textract |
| Lambda (Field Mapper) | Feld-Mapping mit Bedrock |
| Lambda (Inventory Updater) | Bestandsdatenaktualisierung & Aggregation |
| Lambda (Report Generator) | Bestandsanalysebericht-Generierung |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| OCR-Genauigkeit sinkt | Vorverarbeitete Daten verwenden |
| Bedrock-Verzögerung | Vorab generierte Berichte anzeigen |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über OutputDestination: Auswahl mit OutputDestination möglich (Pattern B)

UC12 logistics-ocr unterstützt seit dem Update vom 2026-05-10 den Parameter `OutputDestination`
(siehe `docs/output-destination-patterns.md`).

**Ziel-Workload**: Lieferschein-OCR / Bestandsanalyse / Logistikberichte

**2 Modi**:

### STANDARD_S3 (Standard, wie bisher)
Erstellt einen neuen S3-Bucket (`${AWS::StackName}-output-${AWS::AccountId}`) und
schreibt KI-Artefakte dorthin.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (andere erforderliche Parameter)
```

### FSXN_S3AP („no data movement"-Muster)
Schreibt KI-Artefakte über FSxN S3 Access Point zurück auf **dasselbe FSx ONTAP-Volume** wie die Originaldaten.
SMB/NFS-Benutzer können KI-Artefakte direkt in der Verzeichnisstruktur ihrer täglichen Arbeit einsehen.
Es wird kein Standard-S3-Bucket erstellt.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (andere erforderliche Parameter)
```

**Hinweise**:

- Angabe von `S3AccessPointName` wird dringend empfohlen (IAM-Berechtigung sowohl für Alias- als auch ARN-Format)
- Objekte über 5 GB sind mit FSxN S3AP nicht möglich (AWS-Spezifikation), Multipart-Upload erforderlich
- AWS-Spezifikationsbeschränkungen siehe
  [Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
  und [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verifizierte UI/UX-Screenshots

Gleiche Richtlinie wie bei Phase 7 UC15/16/17 und UC6/11/14 Demos: Ziel sind **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich sehen**. Technische Ansichten (Step Functions-Graph, CloudFormation-Stack-Events usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC12 Step Functions-Graph, erfolgreiche Lambda-Ausführung bestätigt)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC12 Step Functions Graph view (SUCCEEDED)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus jedes Lambda / Parallel / Map-States farblich visualisiert.

### Vorhandene Screenshots (aus Phase 1-6, relevante Teile)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Output-Bucket (waybills-ocr/, inventory/, reports/)
- Textract Lieferschein-OCR-Ergebnisse (Cross-Region)
- Rekognition Lagerbildlabels
- Versandaggregationsberichte

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Voraussetzungsprüfung (gemeinsame VPC/S3 AP vorhanden)
   - `UC=logistics-ocr bash scripts/package_generic_uc.sh` für Lambda-Paketierung
   - `bash scripts/deploy_generic_ucs.sh UC12` für Deployment

2. **Beispieldatenplatzierung**:
   - Beispieldateien über S3 AP Alias mit Präfix `waybills/` hochladen
   - Step Functions `fsxn-logistics-ocr-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Output-Bucket `fsxn-logistics-ocr-demo-output-<account>`
   - Vorschau von AI/ML-Output-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierung**:
   - `python3 scripts/mask_uc_demos.py logistics-ocr-demo` für automatische Maskierung
   - Zusätzliche Maskierung nach `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC12` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
