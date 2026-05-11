# Datenvorverarbeitungs-Pipeline für autonomes Fahren -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Vorverarbeitungs- und Annotations-Pipeline für autonome Fahrsensordaten. Große Fahrdatenmengen werden automatisch klassifiziert und Trainingsdatensätze erstellt.

**Kernbotschaft**: Sensordaten automatisch vorverarbeiten und annotierte Datensätze für KI-Training erstellen.

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
Sensordatenerfassung → Formatkonvertierung → Frame-Klassifikation → Annotation-Generierung → Dataset-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Vorverarbeitung großer Fahrdaten ist ein Engpass

### Section 2 (0:45–1:30)
> Upload: Sensor-Logdateien ablegen startet die Pipeline

### Section 3 (1:30–2:30)
> Vorverarbeitung und Klassifikation: Automatische Formatkonvertierung und KI-Frame-Klassifikation

### Section 4 (2:30–3:45)
> Annotationsergebnisse: Überprüfung generierter Labels und Qualitätsstatistiken

### Section 5 (3:45–5:00)
> Dataset-Bericht: Trainingsbereitschaftsbericht und Qualitätsmetriken

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Python 3.13) | Sensordaten-Qualitätsvalidierung, Szenenklassifikation, Kataloggenerierung |
| Lambda SnapStart | Kaltstart-Reduzierung (`EnableSnapStart=true` Opt-in) |
| SageMaker (4-way routing) | Inferenz (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Echtes Scale-to-Zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Szenenklassifikation / Annotationsvorschläge |
| Amazon Athena | Metadatensuche und -aggregation |
| CloudFormation Guard Hooks | Sicherheitsrichtlinien-Durchsetzung bei Bereitstellung |

### Lokaler Test (Phase 6A)

```bash
# Lokaler Test mit SAM CLI
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

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
- 📸 **UI/UX-Aufnahme**: ✅ SFN Graph abgeschlossen (Phase 8 Theme D, commit 081cc66)

### Vorhandene Screenshots (aus Phase 1-6)

![UC9 Step Functions Graph-Ansicht (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### UI/UX-Zielbildschirme für Re-Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (keyframes/, annotations/, qc/)
- Rekognition Keyframe-Objekterkennungsergebnisse
- LiDAR-Punktwolke Qualitätsprüfungszusammenfassung
- COCO-kompatibles Annotations-JSON

### Aufnahmeanleitung

1. **Vorbereitung**: `bash scripts/verify_phase7_prerequisites.sh` ausführen, um Voraussetzungen zu prüfen
2. **Beispieldaten**: Dateien über S3 AP Alias hochladen, dann Step Functions-Workflow starten
3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser maskieren)
4. **Maskierung**: `python3 scripts/mask_uc_demos.py <uc-dir>` für automatische OCR-Maskierung ausführen
5. **Bereinigung**: `bash scripts/cleanup_generic_ucs.sh <UC>` zum Löschen des Stacks ausführen
