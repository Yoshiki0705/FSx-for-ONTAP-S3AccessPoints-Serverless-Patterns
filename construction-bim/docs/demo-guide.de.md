# BIM-Modelländerungserkennung und Sicherheits-Compliance-Prüfung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur BIM-Änderungserkennung und automatischen Sicherheits-Compliance-Prüfung. Verstöße werden bei Designänderungen automatisch erkannt.

**Kernbotschaft**: Sicherheitsverstöße bei BIM-Änderungen automatisch erkennen und Risiken bereits in der Entwurfsphase eliminieren.

**Voraussichtliche Dauer**: 3–5 min

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
