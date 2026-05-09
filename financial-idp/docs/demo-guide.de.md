# Automatisierte Vertrags- und Rechnungsverarbeitung — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine automatisierte Verarbeitungspipeline für Verträge und Rechnungen. Sie kombiniert OCR-Textextraktion mit Entitätsextraktion zur automatischen Generierung strukturierter Daten.

**Kernbotschaft**: Papierbasierte Verträge und Rechnungen automatisch digitalisieren und Schlüsselinformationen sofort extrahieren.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: 200+ Rechnungen monatlich manuell zu verarbeiten ist nicht tragbar

### Section 2 (0:45–1:30)
> Upload: Dateien ablegen startet automatische Verarbeitung

### Section 3 (1:30–2:30)
> OCR und Extraktion: OCR + KI für Dokumentklassifizierung und Feldextraktion

### Section 4 (2:30–3:45)
> Strukturierte Ausgabe: Sofort nutzbare strukturierte Daten

### Section 5 (3:45–5:00)
> Validierung und Bericht: Konfidenzwerte zeigen prüfungsbedürftige Elemente

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (OCR Processor) | Textextraktion über Textract |
| Lambda (Entity Extractor) | Entitätsextraktion über Bedrock |
| Lambda (Classifier) | Dokumenttyp-Klassifizierung |
| Amazon Athena | Aggregierte Analyse extrahierter Daten |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
