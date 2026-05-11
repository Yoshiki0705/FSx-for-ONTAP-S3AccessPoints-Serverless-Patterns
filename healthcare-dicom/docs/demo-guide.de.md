# DICOM-Anonymisierungs-Workflow -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine automatische Anonymisierungs-Pipeline für DICOM-Dateien. Patientenidentifikationsdaten werden entfernt, um einen sicheren Forschungsdatenaustausch zu ermöglichen.

**Kernbotschaft**: Patientendaten automatisch aus DICOM-Dateien entfernen für konformen und sicheren Datenaustausch.

**Voraussichtliche Dauer**: 3–5 min

---

## Ausgabeziel: FSxN S3 Access Point (Pattern A)

Dieser UC gehört zum **Pattern A: Native S3AP Output**
(siehe `docs/output-destination-patterns.md`).

**Design**: Alle AI/ML-Artefakte werden über den FSxN S3 Access Point auf
**dasselbe FSx ONTAP Volume** wie die Quelldaten zurückgeschrieben. Kein separater
Standard-S3-Bucket wird erstellt ("no data movement"-Pattern).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: Eingabe-S3-AP-Alias
- `S3AccessPointOutputAlias`: Ausgabe-S3-AP-Alias (kann identisch mit Eingabe sein)

AWS-Spezifikationsbeschränkungen und Workarounds siehe
[README.de.md — AWS-Spezifikationsbeschränkungen](../../README.de.md#aws-spezifikationsbeschränkungen-und-workarounds).

---
## Workflow

```
DICOM-Upload → Metadaten-Extraktion → PHI-Erkennung → Anonymisierung → Validierungsbericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Forschungsdatenaustausch erfordert Einhaltung der Patientenschutzvorschriften

### Section 2 (0:45–1:30)
> Upload: DICOM-Dateien ablegen startet automatische Verarbeitung

### Section 3 (1:30–2:30)
> PHI-Erkennung und Anonymisierung: KI-gestützte Erkennung und automatische Maskierung

### Section 4 (2:30–3:45)
> Ergebnisse: Überprüfung anonymisierter Dateien und Verarbeitungsstatistiken

### Section 5 (3:45–5:00)
> Validierungsbericht: Compliance-Bericht erstellen und Datenaustausch genehmigen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (DICOM Parser) | DICOM-Metadaten-Extraktion |
| Lambda (PHI Detector) | KI-gestützte Erkennung personenbezogener Daten |
| Lambda (Anonymizer) | Anonymisierungsverarbeitung |
| Amazon Athena | Aggregierte Ergebnisanalyse |

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
- 📸 **UI/UX**: Not yet captured

### Vorhandene Screenshots (aus Phase 1-6)

*(Keine zutreffend. Bitte bei Re-Verifizierung aufnehmen.)*

### UI/UX-Zielbildschirme für Re-Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical Entitätserkennungsergebnisse (Cross-Region)
- De-identifizierte DICOM-Metadaten-JSON

### Aufnahmeanleitung

1. **Vorbereitung**: `bash scripts/verify_phase7_prerequisites.sh` ausführen, um Voraussetzungen zu prüfen
2. **Beispieldaten**: Dateien über S3 AP Alias hochladen, dann Step Functions-Workflow starten
3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser maskieren)
4. **Maskierung**: `python3 scripts/mask_uc_demos.py <uc-dir>` für automatische OCR-Maskierung ausführen
5. **Bereinigung**: `bash scripts/cleanup_generic_ucs.sh <UC>` zum Löschen des Stacks ausführen
