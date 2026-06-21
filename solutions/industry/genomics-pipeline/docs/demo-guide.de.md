# Sequenzierungs-QC und Varianten-Aggregation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline für Qualitätskontrolle (QC) und Variantenaggregation von Next-Generation-Sequencing (NGS)-Daten. Die Sequenzierungsqualität wird automatisch validiert und Variant-Calling-Ergebnisse werden aggregiert und als Bericht aufbereitet.

**Kernbotschaft der Demo**: Automatisierung der QC von Sequenzierungsdaten und sofortige Generierung von Variantenaggregationsberichten. Gewährleistung der Zuverlässigkeit der Analyse.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Punkt | Details |
|------|------|
| **Position** | Bioinformatiker / Genomanalyse-Forscher |
| **Tägliche Aufgaben** | Sequenzierungsdaten-QC, Variant Calling, Ergebnisinterpretation |
| **Herausforderung** | Manuelle QC-Prüfung großer Probenmengen ist zeitaufwändig |
| **Erwartete Ergebnisse** | Effizienzsteigerung durch QC-Automatisierung und Variantenaggregation |

### Persona: Herr Kato (Bioinformatiker)

- Verarbeitet wöchentlich 100+ Sequenzierungsdatenproben
- Benötigt Früherkennung von Proben, die QC-Standards nicht erfüllen
- „Ich möchte nur QC-geprüfte Proben automatisch an die nachgelagerte Analyse senden"

---

## Demo Scenario: Sequenzierungs-Batch-QC

### Gesamtworkflow-Übersicht

```
FASTQ/BAM-Dateien    QC-Analyse      Qualitätsbewertung    Variantenaggregation
(100+ Proben)     →  Metriken    →   Pass/Fail        →   Berichtsgenerierung
                     Berechnung      Filter
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Wöchentlich über 100 Sequenzierungsdatenproben. Wenn Proben schlechter Qualität in die nachgelagerte Analyse gelangen, sinkt die Zuverlässigkeit der Gesamtergebnisse.

**Key Visual**: Liste der Sequenzierungsdatendateien

### Section 2: Pipeline Trigger (0:45–1:30)

**Narration (Zusammenfassung)**:
> Nach Abschluss des Sequenzierungslaufs startet die QC-Pipeline automatisch. Alle Proben werden parallel verarbeitet.

**Key Visual**: Workflow-Start, Probenliste

### Section 3: QC Metrics (1:30–2:30)

**Narration (Zusammenfassung)**:
> Berechnung der QC-Metriken für jede Probe: Read-Anzahl, Q30-Rate, Mapping-Rate, Coverage-Tiefe, Duplikationsrate.

**Key Visual**: QC-Metrik-Berechnung in Bearbeitung, Metrikenliste

### Section 4: Quality Filtering (2:30–3:45)

**Narration (Zusammenfassung)**:
> Pass/Fail-Bewertung basierend auf QC-Kriterien. Klassifizierung der Ursachen für Fail-Proben (niedrige Qualität der Reads, niedrige Coverage usw.).

**Key Visual**: Pass/Fail-Bewertungsergebnisse, Fail-Ursachenklassifizierung

### Section 5: Variant Summary (3:45–5:00)

**Narration (Zusammenfassung)**:
> Aggregation der Variant-Calling-Ergebnisse von QC-geprüften Proben. Probenvergleich, Variantenverteilung, Generierung von AI-Zusammenfassungsberichten.

**Key Visual**: Variantenaggregationsbericht (statistische Zusammenfassung + AI-Interpretation)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Sequenzierungsdatenliste | Section 1 |
| 2 | Pipeline-Startbildschirm | Section 2 |
| 3 | QC-Metrik-Ergebnisse | Section 3 |
| 4 | Pass/Fail-Bewertungsergebnisse | Section 4 |
| 5 | Variantenaggregationsbericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Einschleusung minderwertiger Proben beeinträchtigt die Zuverlässigkeit der gesamten Analyse" |
| Trigger | 0:45–1:30 | „QC startet automatisch nach Abschluss des Laufs" |
| Metrics | 1:30–2:30 | „Berechnung wichtiger QC-Metriken für alle Proben" |
| Filtering | 2:30–3:45 | „Automatische Pass/Fail-Bewertung basierend auf Kriterien" |
| Summary | 3:45–5:00 | „Sofortige Generierung von Variantenaggregation und AI-Zusammenfassung" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Hochwertige FASTQ-Metriken (20 Proben) | Baseline |
| 2 | Minderwertige Proben (Q30 < 80%, 3 Fälle) | Fail-Erkennungs-Demo |
| 3 | Niedrige Coverage-Proben (2 Fälle) | Klassifizierungs-Demo |
| 4 | Variant-Calling-Ergebnisse (VCF-Zusammenfassung) | Aggregations-Demo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung der Proben-QC-Daten | 3 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahmen | 2 Stunden |
| Narrationsskript-Erstellung | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Echtzeit-Sequenzierungsüberwachung
- Automatische Generierung klinischer Berichte
- Multi-Omics-Integrationsanalyse

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (QC Calculator) | Berechnung der Sequenzierungs-QC-Metriken |
| Lambda (Quality Filter) | Pass/Fail-Bewertung und Klassifizierung |
| Lambda (Variant Aggregator) | Variantenaggregation |
| Lambda (Report Generator) | Zusammenfassungsberichtsgenerierung durch Bedrock |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Verzögerung bei der Verarbeitung großer Datenmengen | Ausführung mit Teilmenge |
| Bedrock-Verzögerung | Anzeige vorab generierter Berichte |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Verifizierte UI/UX-Screenshots

Phase 7 UC15/16/17 und UC6/11/14 folgen demselben Ansatz: **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich sehen**, sind das Ziel. Technische Ansichten (Step Functions-Graph, CloudFormation-Stack-Ereignisse usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC7 Step Functions-Graph, Lambda-Ausführung erfolgreich bestätigt)
- 📸 **UI/UX-Aufnahme (Phase 8 Theme D)**: ✅ SUCCEEDED-Aufnahme abgeschlossen (Commit 2b958db — nach IAM S3AP-Korrektur neu bereitgestellt, alle Schritte erfolgreich in 3:03)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC7 Step Functions Graph view (SUCCEEDED)

![UC7 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

Die Step Functions Graph-Ansicht ist der wichtigste Bildschirm für Endbenutzer, der den Ausführungsstatus jedes Lambda-/Parallel-/Map-Status farblich visualisiert.

#### UC7 Step Functions Graph (SUCCEEDED — Phase 8 Theme D Neuaufnahme)

![UC7 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

Nach IAM S3AP-Korrektur neu bereitgestellt. Alle Schritte SUCCEEDED (3:03).

#### UC7 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)

![UC7 Step Functions Graph (Zoom-Ansicht)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### Vorhandene Screenshots (relevante aus Phase 1-6)

#### UC7 Comprehend Medical Genomanalyse-Ergebnisse (Cross-Region us-east-1)

![UC7 Comprehend Medical Genomanalyse-Ergebnisse (Cross-Region us-east-1)](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (fastq-qc/, variant-summary/, entities/)
- Athena-Abfrageergebnisse (Variantenfrequenzaggregation)
- Comprehend Medical medizinische Entitäten (Genes, Diseases, Mutations)
- Von Bedrock generierte Forschungsberichte

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Voraussetzungsprüfung (gemeinsame VPC/S3 AP vorhanden)
   - `UC=genomics-pipeline bash scripts/package_generic_uc.sh` für Lambda-Paketierung
   - `bash scripts/deploy_generic_ucs.sh UC7` für Deployment

2. **Beispieldatenplatzierung**:
   - Hochladen von Beispieldateien über S3 AP Alias zum `fastq/`-Präfix
   - Starten von Step Functions `fsxn-genomics-pipeline-demo-workflow` (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Übersicht über S3-Ausgabe-Bucket `fsxn-genomics-pipeline-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (Format siehe `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierungsverarbeitung**:
   - `python3 scripts/mask_uc_demos.py genomics-pipeline-demo` für automatische Maskierung
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC7` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
