# Schadensbeurteilung durch Unfallfotos und Versicherungsleistungsbericht — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur automatischen Schadensbeurteilung und Generierung von Versicherungsanspruchsberichten aus Unfallfotos. Durch Bildanalyse zur Schadensbewertung und KI-gestützte Berichtserstellung wird der Bewertungsprozess effizienter gestaltet.

**Kernbotschaft der Demo**: KI analysiert automatisch Unfallfotos, bewertet das Schadensausmaß und generiert sofort Versicherungsanspruchsberichte.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Punkt | Details |
|------|------|
| **Position** | Schadensregulierer / Claims Adjuster |
| **Tägliche Aufgaben** | Prüfung von Unfallfotos, Schadensbewertung, Versicherungssummenberechnung, Berichtserstellung |
| **Herausforderung** | Große Anzahl von Schadenfällen muss schnell bearbeitet werden |
| **Erwartete Ergebnisse** | Beschleunigung des Bewertungsprozesses und Sicherstellung der Konsistenz |

### Persona: Herr Kobayashi (Schadensregulierer)

- Bearbeitet monatlich 100+ Versicherungsansprüche
- Beurteilt Schadensausmaß anhand von Fotos und erstellt Berichte
- „Ich möchte die Erstbewertung automatisieren und mich auf komplexe Fälle konzentrieren"

---

## Demo Scenario: Schadensbewertung bei Autounfällen

### Gesamtworkflow

```
Unfallfotos      Bildanalyse     Schadensbewertung    Anspruchsbericht
(mehrere)    →   Schadenserkennung  →  Schweregrad    →    KI-Generierung
                 Bereichsidentifikation  Kostenschätzung
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Monatlich über 100 Versicherungsansprüche. Bei jedem Fall müssen mehrere Unfallfotos geprüft, das Schadensausmaß bewertet und ein Bericht erstellt werden. Die manuelle Bearbeitung kann nicht mithalten.

**Key Visual**: Liste der Versicherungsansprüche, Beispiele von Unfallfotos

### Section 2: Photo Upload (0:45–1:30)

**Narration (Zusammenfassung)**:
> Sobald Unfallfotos hochgeladen werden, startet die automatische Bewertungspipeline. Verarbeitung erfolgt pro Fall.

**Key Visual**: Foto-Upload → Automatischer Workflow-Start

### Section 3: Damage Detection (1:30–2:30)

**Narration (Zusammenfassung)**:
> KI analysiert die Fotos und erkennt Schadensstellen. Identifiziert Schadensarten (Dellen, Kratzer, Brüche) und Bereiche (Stoßstange, Tür, Kotflügel usw.).

**Key Visual**: Schadenserkennungsergebnisse, Bereichszuordnung

### Section 4: Assessment (2:30–3:45)

**Narration (Zusammenfassung)**:
> Bewertet das Schadensausmaß, entscheidet über Reparatur/Austausch und berechnet geschätzte Kosten. Vergleich mit ähnlichen früheren Fällen wird ebenfalls durchgeführt.

**Key Visual**: Schadensbewertungstabelle, Kostenschätzung

### Section 5: Claims Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> KI generiert automatisch einen Versicherungsanspruchsbericht. Enthält Schadensübersicht, geschätzte Kosten und empfohlene Maßnahmen. Der Schadensregulierer muss nur noch prüfen und genehmigen.

**Key Visual**: KI-generierter Anspruchsbericht (Schadensübersicht + Kostenschätzung)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Liste der Anspruchsfälle | Section 1 |
| 2 | Foto-Upload & Pipeline-Start | Section 2 |
| 3 | Schadenserkennungsergebnisse | Section 3 |
| 4 | Schadensbewertung & Kostenschätzung | Section 4 |
| 5 | Versicherungsanspruchsbericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Manuelle Bewertung von 100 Ansprüchen pro Monat ist nicht machbar" |
| Upload | 0:45–1:30 | „Foto-Upload startet automatische Bewertung" |
| Detection | 1:30–2:30 | „KI erkennt automatisch Schadensstellen und -arten" |
| Assessment | 2:30–3:45 | „Automatische Schätzung von Schadensausmaß und Reparaturkosten" |
| Report | 3:45–5:00 | „Automatische Generierung des Anspruchsberichts, nur Prüfung & Genehmigung erforderlich" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Fotos mit geringfügigen Schäden (5 Fälle) | Basis-Bewertungsdemo |
| 2 | Fotos mit mittleren Schäden (3 Fälle) | Demo der Bewertungsgenauigkeit |
| 3 | Fotos mit schweren Schäden (2 Fälle) | Demo der Totalschadenbeurteilung |

---

## Timeline

### Innerhalb 1 Woche erreichbar

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispielfotodaten | 2 Stunden |
| Überprüfung der Pipeline-Ausführung | 2 Stunden |
| Erfassung von Screenshots | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Schadenserkennung aus Videos
- Automatischer Abgleich mit Werkstattkostenvoranschlägen
- Betrugserkennung

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Image Analyzer) | Schadenserkennung durch Bedrock/Rekognition |
| Lambda (Damage Assessor) | Schadensgradbeurteilung & Kostenschätzung |
| Lambda (Report Generator) | Anspruchsberichtsgenerierung durch Bedrock |
| Amazon Athena | Referenz & Vergleich früherer Falldaten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Unzureichende Bildanalysegenauigkeit | Verwendung vorab analysierter Ergebnisse |
| Bedrock-Verzögerung | Anzeige vorab generierter Berichte |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Verifizierte UI/UX-Screenshots (AWS-Verifizierung 2026-05-10)

Gleiche Richtlinie wie Phase 7: Aufnahme von **UI/UX-Bildschirmen, die Versicherungsregulierer tatsächlich in ihrer täglichen Arbeit verwenden**.
Bildschirme für technische Benutzer (Step Functions-Grafiken usw.) sind ausgeschlossen.

### Auswahl des Ausgabeziels: Standard-S3 vs. FSxN S3AP

UC14 unterstützt seit dem Update vom 2026-05-10 den Parameter `OutputDestination`.
Durch **Zurückschreiben der KI-Ergebnisse auf dasselbe FSx-Volume** können Anspruchsbearbeiter
Schadensbewertungs-JSON, OCR-Ergebnisse und Anspruchsberichte innerhalb der Verzeichnisstruktur
des Anspruchsfalls einsehen („no data movement"-Muster, auch aus PII-Schutzperspektive vorteilhaft).

```bash
# STANDARD_S3-Modus (Standard, wie bisher)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP-Modus (KI-Ergebnisse auf FSx ONTAP-Volume zurückschreiben)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS-Spezifikationsbeschränkungen und Workarounds siehe [Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策).

### 1. Versicherungsanspruchsbericht — Übersicht für Schadensregulierer

Bericht, der Unfallfotos-Rekognition-Analyse + Kostenvoranschlags-Textract-OCR + Bewertungsempfehlung integriert.
Beurteilung `MANUAL_REVIEW` + Konfidenz 75%, Sachbearbeiter prüft Punkte, die nicht automatisiert werden können.

<!-- SCREENSHOT: uc14-claims-report.png
     Inhalt: Versicherungsanspruchsbericht (Anspruchs-ID, Schadensübersicht, Kostenvoranschlagskorrelation, empfohlene Beurteilung)
            + Rekognition-Erkennungslabelliste + Textract-OCR-Ergebnisse
     Maskiert: Konto-ID, Bucket-Name -->
![UC14: Versicherungsanspruchsbericht](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. S3-Ausgabe-Bucket — Übersicht der Bewertungsartefakte

Bildschirm, auf dem Schadensregulierer Artefakte pro Anspruchsfall überprüfen.
`assessments/` (Rekognition-Analyse) + `estimates/` (Textract-OCR) + `reports/` (integrierter Bericht).

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     Inhalt: S3-Konsole mit assessments/-, estimates/-, reports/-Präfixen
     Maskiert: Konto-ID -->
![UC14: S3-Ausgabe-Bucket](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### Gemessene Werte (AWS-Deployment-Verifizierung 2026-05-10)

- **Step Functions-Ausführung**: SUCCEEDED
- **Rekognition**: Erkennung von `Maroon` 90,79%, `Business Card` 84,51% usw. auf Unfallfotos
- **Textract**: OCR von `Total: 1270.00 USD` usw. aus Kostenvoranschlags-PDF über Cross-Region us-east-1
- **Generierte Artefakte**: assessments/*.json, estimates/*.json, reports/*.txt
- **Tatsächlicher Stack**: `fsxn-insurance-claims-demo` (ap-northeast-1, Verifizierung am 2026-05-10)
