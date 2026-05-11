# Bohrloch-Anomalieerkennung und Compliance-Berichterstattung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur Anomalieerkennung in Bohrlochdaten und automatischen Compliance-Berichterstellung.

**Kernbotschaft**: Anomalien in Bohrlochdaten automatisch erkennen und Compliance-Berichte sofort erstellen.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
Bohrlochdaten-Erfassung → Signalvorverarbeitung → Anomalieerkennung → Vorschriftenabgleich → Compliance-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Anomaliesuche in großen Datenmengen ist ineffizient

### Section 2 (0:45–1:30)
> Upload: Bohrloch-Logdateien ablegen startet die Analyse

### Section 3 (1:30–2:30)
> Erkennung: KI-gestützte Musteranalyse erkennt Anomalien automatisch

### Section 4 (2:30–3:45)
> Ergebnisse: Liste erkannter Anomalien und Schweregradklassifikation

### Section 5 (3:45–5:00)
> Compliance-Bericht: Vorschriftenvergleich und Korrekturempfehlungen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Signal Processor) | Bohrloch-Signalvorverarbeitung |
| Lambda (Anomaly Detector) | KI-gestützte Anomalieerkennung |
| Lambda (Compliance Checker) | Vorschriften-Compliance-Prüfung |
| Amazon Athena | Aggregierte Anomaliehistorie-Analyse |

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

- S3-Ausgabe-Bucket (segy-metadata/, anomalies/, reports/)
- Athena-Abfrageergebnisse (SEG-Y-Metadatenstatistiken)
- Rekognition Bohrlochmessungs-Bildlabels
- Anomalieerkennungsbericht

### Aufnahmeanleitung

1. **Vorbereitung**: `bash scripts/verify_phase7_prerequisites.sh` ausführen, um Voraussetzungen zu prüfen
2. **Beispieldaten**: Dateien über S3 AP Alias hochladen, dann Step Functions-Workflow starten
3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser maskieren)
4. **Maskierung**: `python3 scripts/mask_uc_demos.py <uc-dir>` für automatische OCR-Maskierung ausführen
5. **Bereinigung**: `bash scripts/cleanup_generic_ucs.sh <UC>` zum Löschen des Stacks ausführen
