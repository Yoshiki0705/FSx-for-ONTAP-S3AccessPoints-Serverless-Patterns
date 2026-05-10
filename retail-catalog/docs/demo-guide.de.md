# Produktbild-Tagging und Katalog-Metadaten-Generierung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zum automatischen Produktbild-Tagging und zur Katalog-Metadaten-Generierung. KI analysiert Produktfotos und erstellt automatisch Tags und Beschreibungen.

**Kernbotschaft**: KI extrahiert automatisch Attribute aus Produktbildern, erstellt sofort Katalog-Metadaten und beschleunigt die Produktregistrierung.

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
Bild-Upload → Visuelle Analyse → Attribut-Tagging → Beschreibungsgenerierung → Katalogbericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelles Tagging tausender Produkte ist ein Engpass

### Section 2 (0:45–1:30)
> Upload: Produktfotos ablegen startet die Verarbeitung

### Section 3 (1:30–2:30)
> KI-Analyse und Tagging: Automatische Extraktion von Farbe, Material, Kategorie per Vision-KI

### Section 4 (2:30–3:45)
> Metadaten-Generierung: Automatische Produktbeschreibungen und Suchbegriffe

### Section 5 (3:45–5:00)
> Katalogbericht: Verarbeitungsstatistiken und Qualitätsvalidierungsergebnisse

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Image Analyzer) | KI-gestützte visuelle Analyse |
| Lambda (Tag Generator) | Attribut-Tag-Generierung |
| Lambda (Description Writer) | Automatische Beschreibungserstellung |
| Amazon Athena | Katalog-Statistikanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
