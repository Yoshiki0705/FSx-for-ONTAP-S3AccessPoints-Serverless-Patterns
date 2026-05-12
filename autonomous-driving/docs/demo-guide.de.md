# Fahrtenvorverarbeitung und Annotation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur Vorverarbeitung und Annotation von Fahrdaten in der Entwicklung autonomer Fahrzeuge. Große Mengen an Sensordaten werden automatisch klassifiziert und qualitätsgeprüft, um effizient Trainingsdatensätze zu erstellen.

**Kernbotschaft der Demo**: Automatisierung der Qualitätsprüfung und Metadaten-Annotation von Fahrdaten zur Beschleunigung der Erstellung von AI-Trainingsdatensätzen.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Dateningenieur / ML-Ingenieur |
| **Tägliche Aufgaben** | Fahrdatenverwaltung, Annotation, Erstellung von Trainingsdatensätzen |
| **Herausforderung** | Effiziente Extraktion nützlicher Szenen aus großen Mengen an Fahrdaten nicht möglich |
| **Erwartetes Ergebnis** | Automatisierte Datenqualitätsprüfung und effiziente Szenenklassifizierung |

### Persona: Herr Ito (Dateningenieur)

- Täglich werden TB-große Mengen an Fahrdaten akkumuliert
- Synchronisationsprüfung von Kamera, LiDAR und Radar erfolgt manuell
- „Ich möchte nur qualitativ hochwertige Daten automatisch an die Lernpipeline senden"

---

## Demo Scenario: Batch-Vorverarbeitung von Fahrdaten

### Gesamtübersicht des Workflows

```
Fahrdaten         Datenvalidierung    Szenenklassifizierung    Datensatz
(ROS bag etc.)  →  Qualitätsprüfung  →  Metadaten-           →  Katalog-
                   Synchronisations-    Annotation (AI)         generierung
                   prüfung
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Täglich werden TB-große Mengen an Fahrdaten akkumuliert. Daten schlechter Qualität (Sensorausfälle, Synchronisationsfehler) sind vermischt, manuelle Sortierung ist unrealistisch.

**Key Visual**: Ordnerstruktur der Fahrdaten, Visualisierung der Datenmengen

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration (Zusammenfassung)**:
> Beim Upload neuer Fahrdaten startet die Vorverarbeitungspipeline automatisch.

**Key Visual**: Daten-Upload → Automatischer Workflow-Start

### Section 3: Quality Validation (1:30–2:30)

**Narration (Zusammenfassung)**:
> Vollständigkeitsprüfung der Sensordaten: Automatische Erkennung von Frame-Verlusten, Zeitstempel-Synchronisation und Datenbeschädigungen.

**Key Visual**: Qualitätsprüfungsergebnisse — Integritätsscore nach Sensor

### Section 4: Scene Classification (2:30–3:45)

**Narration (Zusammenfassung)**:
> AI klassifiziert Szenen automatisch: Kreuzungen, Autobahnen, schlechtes Wetter, Nacht etc. Wird als Metadaten hinzugefügt.

**Key Visual**: Szenenklassifizierungsergebnisse-Tabelle, Verteilung nach Kategorien

### Section 5: Dataset Catalog (3:45–5:00)

**Narration (Zusammenfassung)**:
> Automatische Generierung eines Katalogs qualitätsgeprüfter Daten. Als durchsuchbarer Datensatz nach Szenenbedingungen verfügbar.

**Key Visual**: Datensatzkatalog, Suchschnittstelle

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Ordnerstruktur der Fahrdaten | Section 1 |
| 2 | Pipeline-Startbildschirm | Section 2 |
| 3 | Qualitätsprüfungsergebnisse | Section 3 |
| 4 | Szenenklassifizierungsergebnisse | Section 4 |
| 5 | Datensatzkatalog | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Manuelle Auswahl nützlicher Szenen aus TB-großen Datenmengen ist unmöglich" |
| Trigger | 0:45–1:30 | „Vorverarbeitung startet automatisch beim Upload" |
| Validation | 1:30–2:30 | „Automatische Erkennung von Sensorausfällen und Synchronisationsfehlern" |
| Classification | 2:30–3:45 | „AI klassifiziert Szenen automatisch und fügt Metadaten hinzu" |
| Catalog | 3:45–5:00 | „Automatische Generierung eines durchsuchbaren Datensatzkatalogs" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Normale Fahrdaten (5 Sitzungen) | Baseline |
| 2 | Daten mit Frame-Verlusten (2 Fälle) | Qualitätsprüfungs-Demo |
| 3 | Diverse Szenendaten (Kreuzung, Autobahn, Nacht) | Klassifizierungs-Demo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Benötigte Zeit |
|--------|---------|
| Vorbereitung von Beispiel-Fahrdaten | 3 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahmen erstellen | 2 Stunden |
| Narrationsskript erstellen | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Automatische 3D-Annotationsgenerierung
- Datenauswahl durch Active Learning
- Integration von Datenversionierung

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Python 3.13) | Sensordaten-Qualitätsprüfung, Szenenklassifizierung, Kataloggenerierung |
| Lambda SnapStart | Reduzierung von Cold Starts (Opt-in mit `EnableSnapStart=true`) |
| SageMaker (4-way routing) | Inferenz (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Echtes scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Szenenklassifizierung, Annotationsvorschläge |
| Amazon Athena | Metadatensuche und -aggregation |
| CloudFormation Guard Hooks | Durchsetzung von Sicherheitsrichtlinien beim Deployment |

### Lokaler Test (Phase 6A)

```bash
# SAM CLI でローカルテスト
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Verzögerung bei großen Datenmengen | Ausführung mit Teilmenge |
| Unzureichende Klassifizierungsgenauigkeit | Anzeige vorklassifizierter Ergebnisse |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über Ausgabeziele: Auswählbar mit OutputDestination (Pattern B)

UC9 autonomous-driving unterstützt seit dem Update vom 2026-05-10 den Parameter `OutputDestination`
(siehe `docs/output-destination-patterns.md`).

**Ziel-Workload**: ADAS / Autonome Fahrzeugdaten (Frame-Extraktion, Punktwolken-QC, Annotation, Inferenz)

**2 Modi**:

### STANDARD_S3 (Standard, wie bisher)
Erstellt einen neuen S3-Bucket (`${AWS::StackName}-output-${AWS::AccountId}`) und
schreibt AI-Artefakte dorthin.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP („no data movement"-Muster)
Schreibt AI-Artefakte über FSxN S3 Access Point zurück auf **dasselbe FSx ONTAP Volume** wie die Originaldaten.
SMB/NFS-Benutzer können AI-Artefakte direkt in ihrer Arbeitsverzeichnisstruktur einsehen.
Es wird kein Standard-S3-Bucket erstellt.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**Hinweise**:

- Angabe von `S3AccessPointName` wird dringend empfohlen (IAM-Berechtigung sowohl für Alias- als auch ARN-Format)
- Objekte über 5GB sind mit FSxN S3AP nicht möglich (AWS-Spezifikation), Multipart-Upload erforderlich
- AWS-Spezifikationsbeschränkungen siehe
  [Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
  und [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verifizierte UI/UX-Screenshots

Gleiche Richtlinie wie bei Phase 7 UC15/16/17 und UC6/11/14 Demos: Ziel sind **UI/UX-Bildschirme, die Endbenutzer
in ihrer täglichen Arbeit tatsächlich sehen**. Technische Ansichten (Step Functions Graph, CloudFormation
Stack Events etc.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifikationsstatus für diesen Use Case

- ⚠️ **E2E-Verifikation**: Nur Teilfunktionen (zusätzliche Verifikation in Produktionsumgebung empfohlen)
- 📸 **UI/UX-Aufnahme**: ✅ SFN Graph abgeschlossen (Phase 8 Theme D, Commit 081cc66)

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC9 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### UI/UX-Zielbildschirme bei erneuter Verifikation (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (keyframes/, annotations/, qc/)
- Rekognition Keyframe-Objekterkennungsergebnisse
- LiDAR-Punktwolken-Qualitätsprüfungszusammenfassung
- COCO-kompatible Annotations-JSON

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Voraussetzungsprüfung (gemeinsame VPC/S3 AP vorhanden)
   - `UC=autonomous-driving bash scripts/package_generic_uc.sh` für Lambda-Paketierung
   - `bash scripts/deploy_generic_ucs.sh UC9` für Deployment

2. **Beispieldaten platzieren**:
   - Beispieldateien über S3 AP Alias mit Präfix `footage/` hochladen
   - Step Functions `fsxn-autonomous-driving-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Übersicht über S3-Ausgabe-Bucket `fsxn-autonomous-driving-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierung**:
   - `python3 scripts/mask_uc_demos.py autonomous-driving-demo` für automatische Maskierung
   - Zusätzliche Maskierung nach `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC9` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
