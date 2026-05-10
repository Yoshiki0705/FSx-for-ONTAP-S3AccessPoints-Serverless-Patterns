# Lieferschein-OCR und Bestandsanalyse -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine OCR-Pipeline für Lieferscheine und Bestandsanalyse. Papierdokumente werden automatisch digitalisiert für Echtzeit-Bestandsübersicht.

**Kernbotschaft**: Lieferscheine automatisch per OCR verarbeiten, Bestandsdaten in Echtzeit aktualisieren und Logistikeffizienz steigern.

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
Scan-Upload → OCR-Extraktion → Feld-Parsing → Bestandsaktualisierung → Analysebericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Eingabe von Papierdokumenten ist fehleranfällig und zeitaufwändig

### Section 2 (0:45–1:30)
> Upload: Gescannte Lieferschein-Bilder ablegen startet die Verarbeitung

### Section 3 (1:30–2:30)
> OCR und Parsing: Textextraktion und Konvertierung in strukturierte Daten

### Section 4 (2:30–3:45)
> Bestandsaktualisierung: Echtzeit-Aktualisierung basierend auf extrahierten Daten

### Section 5 (3:45–5:00)
> Analysebericht: Logistik-Dashboard und Anomalie-Erkennungsalarme

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (OCR Engine) | Lieferschein-Textextraktion |
| Lambda (Field Parser) | Strukturierte Daten-Parsing |
| Lambda (Inventory Updater) | Bestandsdaten-Aktualisierung |
| Amazon Athena | Logistik-Statistikanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
