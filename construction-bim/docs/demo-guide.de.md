# BIM-Modelländerungserkennung und Sicherheitskonformität — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur Erkennung von BIM-Modelländerungen und zur Überprüfung der Sicherheitskonformität. Entwurfsänderungen werden automatisch erkannt und die Einhaltung von Baustandards wird verifiziert.

**Kernbotschaft der Demo**: Automatische Verfolgung von BIM-Modelländerungen und sofortige Erkennung von Verstößen gegen Sicherheitsstandards. Verkürzung der Design-Review-Zyklen.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | BIM-Manager / Tragwerksplanungsingenieur |
| **Tägliche Aufgaben** | BIM-Modellverwaltung, Review von Entwurfsänderungen, Konformitätsprüfung |
| **Herausforderung** | Schwierig, Entwurfsänderungen mehrerer Teams zu verfolgen und die Einhaltung von Standards zu bestätigen |
| **Erwartete Ergebnisse** | Effizienzsteigerung bei automatischer Änderungserkennung und Sicherheitsstandardprüfung |

### Persona: Herr Kimura (BIM-Manager)

- Großes Bauprojekt mit 20+ Entwurfsteams, die parallel arbeiten
- Muss täglich überprüfen, ob Entwurfsänderungen die Sicherheitsstandards beeinträchtigen
- „Ich möchte automatische Sicherheitsprüfungen bei Änderungen durchführen lassen"

---

## Demo Scenario: Automatische Erkennung und Sicherheitsverifizierung von Entwurfsänderungen

### Gesamtworkflow-Übersicht

```
BIM-Modellaktualisierung     Änderungserkennung        Compliance     Review-Bericht
(IFC/RVT)              →   Differenzanalyse    →   Regelabgleich     →    KI-Generierung
                           Elementvergleich        Sicherheitsstandardprüfung
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> In einem Großprojekt aktualisieren 20 Teams parallel BIM-Modelle. Manuelle Überprüfung kann nicht mithalten, um festzustellen, ob Änderungen gegen Sicherheitsstandards verstoßen.

**Key Visual**: BIM-Modelldateiliste, Aktualisierungsverlauf mehrerer Teams

### Section 2: Change Detection (0:45–1:30)

**Narration (Zusammenfassung)**:
> Erkennung von Modelldateiaktualisierungen und automatische Analyse der Unterschiede zur vorherigen Version. Identifizierung geänderter Elemente (Strukturbauteile, Anlagenplatzierung usw.).

**Key Visual**: Änderungserkennungstrigger, Start der Differenzanalyse

### Section 3: Compliance Check (1:30–2:30)

**Narration (Zusammenfassung)**:
> Automatischer Abgleich der geänderten Elemente mit Sicherheitsstandardregeln. Verifizierung der Konformität mit seismischen Standards, Brandschutzabschnitten, Fluchtwegen usw.

**Key Visual**: Regelabgleich in Bearbeitung, Liste der Prüfpunkte

### Section 4: Results Analysis (2:30–3:45)

**Narration (Zusammenfassung)**:
> Überprüfung der Verifizierungsergebnisse. Anzeige von Verstößen, Auswirkungsbereichen und Prioritätsstufen in einer Liste.

**Key Visual**: Tabelle der erkannten Verstöße, Klassifizierung nach Priorität

### Section 5: Review Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> KI generiert einen Design-Review-Bericht. Präsentation von Verstößen im Detail, Korrekturvorschlägen und betroffenen anderen Entwurfselementen.

**Key Visual**: KI-generierter Review-Bericht

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | BIM-Modelldateiliste | Section 1 |
| 2 | Änderungserkennung / Differenzanzeige | Section 2 |
| 3 | Compliance-Check-Fortschritt | Section 3 |
| 4 | Verstoßerkennungsergebnisse | Section 4 |
| 5 | KI-Review-Bericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Änderungsverfolgung und Sicherheitsbestätigung bei paralleler Arbeit können nicht mithalten" |
| Detection | 0:45–1:30 | „Automatische Erkennung von Modellaktualisierungen und Analyse der Unterschiede" |
| Compliance | 1:30–2:30 | „Automatischer Abgleich mit Sicherheitsstandardregeln" |
| Results | 2:30–3:45 | „Sofortiges Erfassen von Verstößen und Auswirkungsbereichen" |
| Report | 3:45–5:00 | „KI präsentiert Korrekturvorschläge und Auswirkungsanalyse" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Basis-BIM-Modell (IFC-Format) | Vergleichsquelle |
| 2 | Geändertes Modell (mit strukturellen Änderungen) | Demo zur Differenzerkennung |
| 3 | Modell mit Sicherheitsstandardverstößen (3 Fälle) | Compliance-Demo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispiel-BIM-Daten | 3 Stunden |
| Bestätigung der Pipeline-Ausführung | 2 Stunden |
| Erfassung von Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Integration von 3D-Visualisierung
- Echtzeit-Änderungsbenachrichtigungen
- Konsistenzprüfung mit der Bauphase

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Change Detector) | BIM-Modelldifferenzanalyse |
| Lambda (Compliance Checker) | Abgleich mit Sicherheitsstandardregeln |
| Lambda (Report Generator) | Review-Berichtgenerierung durch Bedrock |
| Amazon Athena | Aggregation von Änderungsverlauf und Verstoßdaten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| IFC-Parsing-Fehler | Verwendung vorab analysierter Daten |
| Verzögerung beim Regelabgleich | Anzeige vorab verifizierter Ergebnisse |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über OutputDestination: Auswählbar mit OutputDestination (Pattern B)

UC10 construction-bim unterstützt seit dem Update vom 2026-05-10 den Parameter `OutputDestination`
(siehe `docs/output-destination-patterns.md`).

**Ziel-Workload**: Bau-BIM / Zeichnungs-OCR / Sicherheitskonformitätsprüfung

**2 Modi**:

### STANDARD_S3 (Standard, wie bisher)
Erstellt einen neuen S3-Bucket (`${AWS::StackName}-output-${AWS::AccountId}`) und
schreibt KI-Ergebnisse dorthin.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (andere erforderliche Parameter)
```

### FSXN_S3AP („no data movement"-Pattern)
Schreibt KI-Ergebnisse über FSxN S3 Access Point auf **dasselbe FSx ONTAP-Volume** wie die
Originaldaten zurück. SMB/NFS-Benutzer können KI-Ergebnisse direkt in der Verzeichnisstruktur
ihrer täglichen Arbeit einsehen. Es wird kein Standard-S3-Bucket erstellt.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
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
  [Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" im Projekt-README](../../README.md#aws-仕様上の制約と回避策)
  und [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verifizierte UI/UX-Screenshots

Gleiche Richtlinie wie bei Phase 7 UC15/16/17 und UC6/11/14 Demos: Ziel sind **UI/UX-Bildschirme, die
Endbenutzer in ihrer täglichen Arbeit tatsächlich sehen**. Technische Ansichten (Step Functions-Graph, CloudFormation
Stack-Events usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC10 Step Functions-Graph, erfolgreiche Lambda-Ausführung bestätigt)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC10 Step Functions Graph view (SUCCEEDED)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus
jedes Lambda / Parallel / Map-States farblich visualisiert.

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (drawings-ocr/, bim-metadata/, safety-reports/)
- Textract-Zeichnungs-OCR-Ergebnisse (Cross-Region)
- BIM-Versionsdifferenzbericht
- Bedrock-Sicherheitskonformitätsprüfung

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Voraussetzungsprüfung (gemeinsame VPC/S3 AP vorhanden)
   - `UC=construction-bim bash scripts/package_generic_uc.sh` für Lambda-Paketierung
   - `bash scripts/deploy_generic_ucs.sh UC10` für Deployment

2. **Beispieldatenplatzierung**:
   - Hochladen von Beispieldateien über S3 AP Alias zum Präfix `drawings/`
   - Starten von Step Functions `fsxn-construction-bim-demo-workflow` (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Übersicht über S3-Ausgabe-Bucket `fsxn-construction-bim-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierung**:
   - `python3 scripts/mask_uc_demos.py construction-bim-demo` für automatische Maskierung
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC10` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
