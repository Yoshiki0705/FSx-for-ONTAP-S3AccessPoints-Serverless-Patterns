# Publikationsklassifikation und Zitationsnetzwerk-Analyse -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur automatischen Klassifikation von Publikationen und Zitationsnetzwerk-Analyse. Publikationen werden thematisch klassifiziert und Zitationsbeziehungen visualisiert.

**Kernbotschaft**: Publikationen automatisch per KI klassifizieren und Zitationsnetzwerke analysieren, um Forschungstrends sofort zu erkennen.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
Publikations-Upload → Metadaten-Extraktion → KI-Klassifikation → Zitationsnetzwerk-Aufbau → Analysebericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Tausende Publikationen manuell zu klassifizieren ist unrealistisch

### Section 2 (0:45–1:30)
> Upload: PDF-Dateien ablegen startet die Analyse-Pipeline

### Section 3 (1:30–2:30)
> KI-Klassifikation und Netzwerkaufbau: Thematische Klassifikation und Zitationsextraktion

### Section 4 (2:30–3:45)
> Ergebnisse: Thematische Cluster und Identifikation von Schlüsselpublikationen

### Section 5 (3:45–5:00)
> Trendbericht: Trendanalyse nach Fachgebiet und empfohlene Publikationsliste

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (PDF Parser) | Publikations-Metadaten-Extraktion |
| Lambda (Topic Classifier) | KI-gestützte thematische Klassifikation |
| Lambda (Citation Analyzer) | Zitationsnetzwerk-Aufbau |
| Amazon Athena | Aggregierte Trendanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
