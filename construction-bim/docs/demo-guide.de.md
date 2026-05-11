# BIM-Modelländerungserkennung und Sicherheits-Compliance-Prüfung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur BIM-Änderungserkennung und automatischen Sicherheits-Compliance-Prüfung. Verstöße werden bei Designänderungen automatisch erkannt.

**Kernbotschaft**: Sicherheitsverstöße bei BIM-Änderungen automatisch erkennen und Risiken bereits in der Entwurfsphase eliminieren.

**Voraussichtliche Dauer**: 3–5 min

---

## Ausgabeziel: auswählbar über OutputDestination (Pattern B)

Dieser UC unterstützt den `OutputDestination`-Parameter (Update vom 2026-05-10,
siehe `docs/output-destination-patterns.md`).

**Zwei Modi**:

- **STANDARD_S3** (Standard): AI-Artefakte gehen in einen neuen S3-Bucket
- **FSXN_S3AP** ("no data movement"): AI-Artefakte gehen über den S3 Access Point
  zurück auf dasselbe FSx ONTAP Volume, sichtbar für SMB/NFS-Benutzer in der
  bestehenden Verzeichnisstruktur

```bash
# FSXN_S3AP-Modus
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS-Spezifikationsbeschränkungen und Workarounds siehe
[README.de.md — AWS-Spezifikationsbeschränkungen](../../README.de.md#aws-spezifikationsbeschränkungen-und-workarounds).

---
## Workflow

```
BIM-Upload → Änderungserkennung → Vorschriftenabgleich → Verstoßerkennung → Compliance-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Sicherheitsprüfung bei jeder Änderung ist ineffizient

### Section 2 (0:45–1:30)
> BIM-Upload: Geänderte Modelldateien ablegen startet die Prüfung

### Section 3 (1:30–2:30)
> Erkennung und Abgleich: Automatische Diff-Analyse und Sicherheitsstandard-Vergleich

### Section 4 (2:30–3:45)
> Erkannte Verstöße: Liste der Sicherheitsverstöße und Schweregrade

### Section 5 (3:45–5:00)
> Compliance-Bericht: Erstellung des Berichts mit Korrekturempfehlungen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Change Detector) | BIM-Änderungserkennung |
| Lambda (Rule Matcher) | Vorschriften-Matching-Engine |
| Lambda (Report Generator) | Compliance-Berichterstellung |
| Amazon Athena | Aggregierte Verstoßhistorie-Analyse |

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

- S3-Ausgabe-Bucket (drawings-ocr/, bim-metadata/, safety-reports/)
- Textract Zeichnungs-OCR-Ergebnisse (Cross-Region)
- BIM-Versionsdiff-Bericht
- Bedrock Sicherheits-Compliance-Prüfung

### Aufnahmeanleitung

1. **Vorbereitung**: `bash scripts/verify_phase7_prerequisites.sh` ausführen, um Voraussetzungen zu prüfen
2. **Beispieldaten**: Dateien über S3 AP Alias hochladen, dann Step Functions-Workflow starten
3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser maskieren)
4. **Maskierung**: `python3 scripts/mask_uc_demos.py <uc-dir>` für automatische OCR-Maskierung ausführen
5. **Bereinigung**: `bash scripts/cleanup_generic_ucs.sh <UC>` zum Löschen des Stacks ausführen
