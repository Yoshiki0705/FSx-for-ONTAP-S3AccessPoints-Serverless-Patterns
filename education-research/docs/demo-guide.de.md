# Klassifizierung von Forschungsarbeiten und Analyse von Zitationsnetzwerken — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur automatischen Klassifizierung wissenschaftlicher Arbeiten und Analyse von Zitationsnetzwerken. Aus einer großen Anzahl von PDF-Dokumenten werden Metadaten extrahiert und Forschungstrends visualisiert.

**Kernbotschaft der Demo**: Durch automatische Klassifizierung von Dokumentensammlungen und Analyse von Zitationsbeziehungen können Gesamtüberblick über Forschungsfelder und wichtige Arbeiten sofort erfasst werden.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Forscher / Bibliotheks- und Informationswissenschaftler / Forschungsadministrator |
| **Tägliche Aufgaben** | Literaturrecherche, Forschungstrendanalyse, Dokumentenverwaltung |
| **Herausforderung** | Effiziente Identifizierung relevanter Forschung aus großen Mengen von Arbeiten nicht möglich |
| **Erwartete Ergebnisse** | Mapping von Forschungsfeldern und automatische Identifizierung wichtiger Arbeiten |

### Persona: Watanabe-san (Forscher)

- Führt Literaturrecherche zu neuem Forschungsthema durch
- Hat 500+ PDF-Dokumente gesammelt, kann aber keinen Gesamtüberblick gewinnen
- „Möchte automatisch nach Fachgebieten klassifizieren und wichtige, häufig zitierte Arbeiten identifizieren"

---

## Demo Scenario: Automatische Analyse von Literatursammlungen

### Workflow-Übersicht

```
PDF-Dokumente     Metadatenextraktion    Klassifizierung    Visualisierter
(500+ Stück)   →  Titel/Autoren      →  Themenklassif. →  Bericht
                  Zitationsinformationen Zitationsanalyse   Netzwerkkarte
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Über 500 PDF-Dokumente gesammelt. Möchte Verteilung nach Fachgebieten, wichtige Arbeiten und Forschungstrends erfassen, aber alle zu lesen ist unmöglich.

**Key Visual**: Liste von PDF-Dokumenten (große Menge)

### Section 2: Metadata Extraction (0:45–1:30)

**Narration (Zusammenfassung)**:
> Automatische Extraktion von Titel, Autoren, Abstract und Zitationslisten aus jedem PDF-Dokument.

**Key Visual**: Metadatenextraktionsprozess, Beispiel extrahierter Ergebnisse

### Section 3: Classification (1:30–2:30)

**Narration (Zusammenfassung)**:
> KI analysiert Abstracts und klassifiziert automatisch nach Forschungsthemen. Clustering bildet Gruppen verwandter Arbeiten.

**Key Visual**: Themenklassifizierungsergebnisse, Anzahl der Arbeiten nach Kategorie

### Section 4: Citation Analysis (2:30–3:45)

**Narration (Zusammenfassung)**:
> Analyse von Zitationsbeziehungen zur Identifizierung wichtiger, häufig zitierter Arbeiten. Analyse der Struktur des Zitationsnetzwerks.

**Key Visual**: Zitationsnetzwerkstatistiken, Ranking wichtiger Arbeiten

### Section 5: Research Map (3:45–5:00)

**Narration (Zusammenfassung)**:
> KI generiert Gesamtüberblick über Forschungsfeld als Summary-Bericht. Präsentation von Trends, Lücken und zukünftigen Forschungsrichtungen.

**Key Visual**: Forschungskartenbericht (Trendanalyse + empfohlene Literatur)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | PDF-Dokumentensammlung | Section 1 |
| 2 | Metadatenextraktionsergebnisse | Section 2 |
| 3 | Themenklassifizierungsergebnisse | Section 3 |
| 4 | Zitationsnetzwerkstatistiken | Section 4 |
| 5 | Forschungskartenbericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Möchte Gesamtüberblick über 500 Arbeiten gewinnen" |
| Extraction | 0:45–1:30 | „Automatische Metadatenextraktion aus PDFs" |
| Classification | 1:30–2:30 | „KI klassifiziert automatisch nach Themen" |
| Citation | 2:30–3:45 | „Identifizierung wichtiger Arbeiten durch Zitationsnetzwerk" |
| Map | 3:45–5:00 | „Visualisierung von Gesamtüberblick und Trends des Forschungsfelds" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | PDF-Dokumente (30 Stück, 3 Fachgebiete) | Hauptverarbeitungsobjekt |
| 2 | Zitationsbeziehungsdaten (mit gegenseitigen Zitationen) | Netzwerkanalyse-Demo |
| 3 | Häufig zitierte Arbeiten (5 Stück) | Demo zur Identifizierung wichtiger Arbeiten |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispieldokumentendaten | 3 Stunden |
| Überprüfung der Pipeline-Ausführung | 2 Stunden |
| Erfassung von Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Interaktive Visualisierung des Zitationsnetzwerks
- Dokumentenempfehlungssystem
- Automatische Klassifizierung regelmäßig neu erscheinender Arbeiten

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (PDF Parser) | Metadatenextraktion aus PDF-Dokumenten |
| Lambda (Classifier) | Themenklassifizierung durch Bedrock |
| Lambda (Citation Analyzer) | Aufbau und Analyse des Zitationsnetzwerks |
| Amazon Athena | Metadatenaggregation und -suche |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| PDF-Parsing fehlgeschlagen | Verwendung vorab extrahierter Daten |
| Unzureichende Klassifizierungsgenauigkeit | Anzeige vorab klassifizierter Ergebnisse |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Verifizierte UI/UX-Screenshots

Nach demselben Ansatz wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14 werden **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich sehen**, als Ziel verwendet. Technische Ansichten (Step Functions-Graphen, CloudFormation-Stack-Ereignisse usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC13 Step Functions-Graph, erfolgreiche Lambda-Ausführung bestätigt)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC13 Step Functions Graph view (SUCCEEDED)

![UC13 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

Die Step Functions Graph-Ansicht ist der wichtigste Bildschirm für Endbenutzer, der den Ausführungsstatus jedes Lambda-/Parallel-/Map-Status farblich visualisiert.

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC13 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph (Gesamtübersicht)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (papers-ocr/, citations/, reports/)
- Textract-Dokument-OCR-Ergebnisse (Cross-Region)
- Comprehend-Entitätserkennung (Autoren, Zitationen, Schlüsselwörter)
- Forschungsnetzwerk-Analysebericht

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - Voraussetzungen mit `bash scripts/verify_phase7_prerequisites.sh` prüfen (gemeinsame VPC/S3 AP vorhanden)
   - Lambda-Paket mit `UC=education-research bash scripts/package_generic_uc.sh`
   - Deployment mit `bash scripts/deploy_generic_ucs.sh UC13`

2. **Beispieldatenplatzierung**:
   - Beispieldateien über S3 AP Alias mit Präfix `papers/` hochladen
   - Step Functions `fsxn-education-research-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Übersicht über S3-Ausgabe-Bucket `fsxn-education-research-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format von `build/preview_*.html` als Referenz)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierungsverarbeitung**:
   - Automatische Maskierung mit `python3 scripts/mask_uc_demos.py education-research-demo`
   - Zusätzliche Maskierung nach `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - Löschen mit `bash scripts/cleanup_generic_ucs.sh UC13`
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
