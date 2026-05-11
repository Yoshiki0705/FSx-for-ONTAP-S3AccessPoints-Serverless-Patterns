# Sequenzierungs-QC und Varianten-Aggregation -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur Qualitätskontrolle (QC) und Varianten-Aggregation für Genomsequenzierungsdaten.

**Kernbotschaft**: Sequenzierungsdatenqualität automatisch validieren und Varianten aggregieren, damit Forscher sich auf die Analyse konzentrieren können.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
FASTQ-Upload → QC-Validierung → Varianten-Calling → Statistische Aggregation → QC-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle QC großer Sequenzierungsdaten ist zeitaufwändig

### Section 2 (0:45–1:30)
> Upload: FASTQ-Dateien ablegen startet die Pipeline

### Section 3 (1:30–2:30)
> QC und Variantenanalyse: Automatische Qualitätsvalidierung und Varianten-Calling

### Section 4 (2:30–3:45)
> Ergebnisse: QC-Metriken und Variantenstatistiken

### Section 5 (3:45–5:00)
> QC-Bericht: Umfassender Qualitätsbericht und Empfehlungen für Folgeanalysen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (QC Validator) | Sequenzierungs-Qualitätsvalidierung |
| Lambda (Variant Caller) | Varianten-Calling |
| Lambda (Stats Aggregator) | Variantenstatistik-Aggregation |
| Amazon Athena | QC-Metrik-Analyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*

---

## Verifizierte UI/UX-Screenshots

Nach dem gleichen Ansatz wie die Phase 7 UC15/16/17 und UC6/11/14 Demos, mit Fokus auf
**UI/UX-Bildschirme, die Endbenutzer tatsächlich im täglichen Betrieb sehen**.
Technische Ansichten (Step Functions-Graph, CloudFormation-Stack-Ereignisse usw.)
sind in `docs/verification-results-*.md` zusammengefasst.

### Verifizierungsstatus für diesen Anwendungsfall

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **UI/UX-Aufnahme**: ✅ SUCCEEDED (Phase 8 Theme D, commit 2b958db — nach IAM S3AP-Fix neu bereitgestellt, 3:03 alle Schritte erfolgreich)

### Vorhandene Screenshots (aus Phase 1-6)

![UC7 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

![UC7 Step Functions Graph (zoomed)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme für Re-Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (fastq-qc/, variant-summary/, entities/)
- Athena-Abfrageergebnisse (Variantenfrequenzaggregation)
- Comprehend Medical-Entitäten (Gene, Krankheiten, Mutationen)
- Bedrock-generierter Forschungsbericht

### Aufnahmeanleitung

1. **Vorbereitung**: `bash scripts/verify_phase7_prerequisites.sh` ausführen, um Voraussetzungen zu prüfen
2. **Beispieldaten**: Dateien über S3 AP Alias hochladen, dann Step Functions-Workflow starten
3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser maskieren)
4. **Maskierung**: `python3 scripts/mask_uc_demos.py <uc-dir>` für automatische OCR-Maskierung ausführen
5. **Bereinigung**: `bash scripts/cleanup_generic_ucs.sh <UC>` zum Löschen des Stacks ausführen
