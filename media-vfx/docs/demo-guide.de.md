# VFX-Rendering-Qualitätsprüfung — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur Qualitätsprüfung von VFX-Rendering-Ausgaben. Durch automatische Validierung von Rendering-Frames werden Artefakte und fehlerhafte Frames frühzeitig erkannt.

**Kernbotschaft der Demo**: Automatische Validierung großer Mengen von Rendering-Frames und sofortige Erkennung von Qualitätsproblemen. Beschleunigung der Entscheidung über Re-Rendering.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Punkt | Details |
|------|------|
| **Position** | VFX Supervisor / Rendering TD |
| **Tägliche Aufgaben** | Verwaltung von Rendering-Jobs, Qualitätsprüfung, Shot-Freigabe |
| **Herausforderung** | Visuelle Prüfung von Tausenden von Frames erfordert enorme Zeit |
| **Erwartetes Ergebnis** | Automatische Erkennung problematischer Frames und beschleunigte Re-Rendering-Entscheidungen |

### Persona: Nakamura-san (VFX Supervisor)

- 1 Projekt mit 50+ Shots, jeder Shot 100–500 Frames
- Qualitätsprüfung nach Rendering-Abschluss ist Engpass
- „Möchte schwarze Frames, übermäßiges Rauschen, fehlende Texturen automatisch erkennen"

---

## Demo Scenario: Qualitätsvalidierung von Rendering-Batches

### Gesamtübersicht des Workflows

```
Rendering-Ausgabe    Frame-Analyse     Qualitätsbeurteilung    QC-Bericht
(EXR/PNG)        →   Metadaten-    →   Anomalie-          →    Shot-spezifische
                     Extraktion        Erkennung               Zusammenfassung
                                       (Statistische Analyse)
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Tausende von Frames aus der Rendering-Farm. Visuelle Prüfung auf schwarze Frames, Rauschen, fehlende Texturen usw. ist unrealistisch.

**Key Visual**: Rendering-Ausgabeordner (große Menge an EXR-Dateien)

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration (Zusammenfassung)**:
> Nach Abschluss des Rendering-Jobs startet die Qualitätsprüfungs-Pipeline automatisch. Parallele Verarbeitung pro Shot.

**Key Visual**: Workflow-Start, Shot-Liste

### Section 3: Frame Analysis (1:30–2:30)

**Narration (Zusammenfassung)**:
> Berechnung der Pixelstatistiken für jeden Frame (durchschnittliche Helligkeit, Varianz, Histogramm). Prüfung der Konsistenz zwischen Frames.

**Key Visual**: Frame-Analyse in Bearbeitung, Pixelstatistik-Diagramme

### Section 4: Quality Assessment (2:30–3:45)

**Narration (Zusammenfassung)**:
> Erkennung statistischer Ausreißer und Identifizierung problematischer Frames. Klassifizierung von schwarzen Frames (Helligkeit Null), übermäßigem Rauschen (abnormale Varianz) usw.

**Key Visual**: Liste problematischer Frames, Kategorisierung

### Section 5: QC Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> Generierung von Shot-spezifischen QC-Berichten. Präsentation der Frame-Bereiche, die Re-Rendering erfordern, und geschätzte Ursachen.

**Key Visual**: KI-generierter QC-Bericht (Shot-spezifische Zusammenfassung + empfohlene Maßnahmen)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Rendering-Ausgabeordner | Section 1 |
| 2 | Pipeline-Startbildschirm | Section 2 |
| 3 | Frame-Analyse-Fortschritt | Section 3 |
| 4 | Ergebnisse der Problemframe-Erkennung | Section 4 |
| 5 | QC-Bericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Visuelle Prüfung von Tausenden von Frames ist unrealistisch" |
| Trigger | 0:45–1:30 | „QC startet automatisch nach Rendering-Abschluss" |
| Analysis | 1:30–2:30 | „Quantitative Bewertung der Frame-Qualität durch Pixelstatistiken" |
| Assessment | 2:30–3:45 | „Automatische Klassifizierung und Identifizierung problematischer Frames" |
| Report | 3:45–5:00 | „Sofortige Unterstützung bei Re-Rendering-Entscheidungen" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Normale Frames (100 Stück) | Baseline |
| 2 | Schwarze Frames (3 Stück) | Anomalie-Erkennungs-Demo |
| 3 | Frames mit übermäßigem Rauschen (5 Stück) | Qualitätsbeurteilungs-Demo |
| 4 | Frames mit fehlenden Texturen (2 Stück) | Klassifizierungs-Demo |

---

## Timeline

### Erreichbar innerhalb von 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Sample-Frame-Daten | 3 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Artefakterkennung durch Deep Learning
- Integration mit Rendering-Farm (automatisches Re-Rendering)
- Integration in Shot-Tracking-System

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Frame Analyzer) | Extraktion von Frame-Metadaten und Pixelstatistiken |
| Lambda (Quality Checker) | Statistische Qualitätsbeurteilung |
| Lambda (Report Generator) | QC-Berichtsgenerierung durch Bedrock |
| Amazon Athena | Aggregationsanalyse von Frame-Statistiken |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Verzögerung bei der Verarbeitung großer Frames | Umstellung auf Thumbnail-Analyse |
| Bedrock-Verzögerung | Anzeige vorab generierter Berichte |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über das Ausgabeziel: FSxN S3 Access Point (Pattern A)

UC4 media-vfx ist als **Pattern A: Native S3AP Output** klassifiziert
(siehe `docs/output-destination-patterns.md`).

**Design**: Rendering-Metadaten und Frame-Qualitätsbewertungen werden alle über FSxN S3 Access Point
auf **dasselbe FSx ONTAP Volume** wie die Original-Rendering-Assets zurückgeschrieben. Standard-S3-Buckets werden
nicht erstellt („no data movement"-Pattern).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: S3 AP Alias zum Lesen von Eingabedaten
- `S3AccessPointOutputAlias`: S3 AP Alias zum Schreiben von Ausgaben (kann mit Eingabe identisch sein)

**Deployment-Beispiel**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (andere erforderliche Parameter)
```

**Sichtbarkeit für SMB/NFS-Benutzer**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # Original-Render-Frame
  └── qc/shot_001/                     # Frame-Qualitätsbewertung (im selben Volume)
      └── frame_0001_qc.json
```

Für Einschränkungen gemäß AWS-Spezifikationen siehe
[Abschnitt „AWS-Spezifikationseinschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
sowie [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verifizierte UI/UX-Screenshots

Gemäß der gleichen Richtlinie wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14 werden **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich
sehen**, als Ziel betrachtet. Technische Ansichten (Step Functions Graph, CloudFormation
Stack-Events usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ⚠️ **E2E-Verifizierung**: Nur teilweise Funktionen (zusätzliche Verifizierung in Produktionsumgebung empfohlen)
- 📸 **UI/UX-Aufnahme**: ✅ SFN Graph abgeschlossen (Phase 8 Theme D, Commit 3c90042)

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC4 Step Functions Graph-Ansicht (SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![UC4 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei erneuter Verifizierung (empfohlene Aufnahmeliste)

- (Bei erneuter Verifizierung zu definieren)

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - Voraussetzungen mit `bash scripts/verify_phase7_prerequisites.sh` prüfen (gemeinsame VPC/S3 AP vorhanden)
   - Lambda-Paket mit `UC=media-vfx bash scripts/package_generic_uc.sh`
   - Deployment mit `bash scripts/deploy_generic_ucs.sh UC4`

2. **Sample-Daten platzieren**:
   - Sample-Dateien über S3 AP Alias mit Präfix `renders/` hochladen
   - Step Functions `fsxn-media-vfx-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Übersicht über S3-Ausgabe-Bucket `fsxn-media-vfx-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierung**:
   - Automatische Maskierung mit `python3 scripts/mask_uc_demos.py media-vfx-demo`
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - Löschen mit `bash scripts/cleanup_generic_ucs.sh UC4`
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
