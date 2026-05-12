# Produktbild-Tagging und Katalog-Metadatengenerierung — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine Pipeline zur automatischen Tagging von Produktbildern und Generierung von Katalog-Metadaten. Durch KI-gestützte Bildanalyse werden Produktattribute automatisch extrahiert und ein durchsuchbarer Katalog erstellt.

**Kernbotschaft der Demo**: KI extrahiert automatisch Attribute (Farbe, Material, Kategorie usw.) aus Produktbildern und generiert sofort Katalog-Metadaten.

**Voraussichtliche Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Punkt | Details |
|------|------|
| **Position** | E-Commerce-Betreiber / Katalogmanager / MD-Verantwortlicher |
| **Tägliche Aufgaben** | Produktregistrierung, Bildverwaltung, Katalogaktualisierung |
| **Herausforderung** | Attributeingabe und Tagging neuer Produkte ist zeitaufwändig |
| **Erwartete Ergebnisse** | Automatisierung der Produktregistrierung und Verbesserung der Durchsuchbarkeit |

### Persona: Yoshida-san (E-Commerce-Katalogmanager)

- Registriert wöchentlich 200+ neue Produkte
- Gibt manuell 10+ Attribut-Tags pro Produkt ein
- „Ich möchte Tags automatisch generieren, indem ich einfach Produktbilder hochlade"

---

## Demo Scenario: Batch-Registrierung neuer Produkte

### Gesamtworkflow

```
Produktbild       Bildanalyse      Attributextraktion    Katalogaktualisierung
(JPEG/PNG)   →   KI-Analyse    →   Tag-Generierung  →    Metadaten
                  Objekterkennung  Kategorisierung       Registrierung
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Wöchentlich über 200 neue Produkte. Die manuelle Eingabe von Tags für Farbe, Material, Kategorie, Stil usw. für jedes Produkt ist eine enorme Arbeit. Es treten auch Eingabefehler und Inkonsistenzen auf.

**Key Visual**: Produktbild-Ordner, manuelle Tag-Eingabemaske

### Section 2: Image Upload (0:45–1:30)

**Narration (Zusammenfassung)**:
> Einfach Produktbilder in einen Ordner legen, und die automatische Tagging-Pipeline startet.

**Key Visual**: Bild-Upload → automatischer Workflow-Start

### Section 3: AI Analysis (1:30–2:30)

**Narration (Zusammenfassung)**:
> KI analysiert jedes Bild und bestimmt automatisch Produktkategorie, Farbe, Material, Muster und Stil. Mehrere Attribute werden gleichzeitig extrahiert.

**Key Visual**: Bildanalyseverarbeitung, Attributextraktionsergebnisse

### Section 4: Tag Generation (2:30–3:45)

**Narration (Zusammenfassung)**:
> Extrahierte Attribute werden in standardisierte Tags umgewandelt. Konsistenz mit dem bestehenden Tag-System wird sichergestellt.

**Key Visual**: Liste generierter Tags, Verteilung nach Kategorien

### Section 5: Catalog Update (3:45–5:00)

**Narration (Zusammenfassung)**:
> Metadaten werden automatisch im Katalog registriert. Trägt zur Verbesserung der Durchsuchbarkeit und Genauigkeit von Produktempfehlungen bei. Generiert einen Verarbeitungszusammenfassungsbericht.

**Key Visual**: Katalogaktualisierungsergebnisse, KI-Zusammenfassungsbericht

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Produktbild-Ordner | Section 1 |
| 2 | Pipeline-Startbildschirm | Section 2 |
| 3 | KI-Bildanalyseergebnisse | Section 3 |
| 4 | Liste der Tag-Generierungsergebnisse | Section 4 |
| 5 | Katalogaktualisierungszusammenfassung | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Manuelles Tagging von 200 Produkten pro Woche ist enorme Arbeit" |
| Upload | 0:45–1:30 | „Automatisches Tagging startet nur durch Bildablage" |
| Analysis | 1:30–2:30 | „KI bestimmt automatisch Farbe, Material und Kategorie" |
| Tags | 2:30–3:45 | „Standardisierte Tags werden automatisch generiert" |
| Catalog | 3:45–5:00 | „Automatische Katalogregistrierung, Durchsuchbarkeit verbessert sich" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Bekleidungsproduktbilder (10 Stück) | Hauptverarbeitungsobjekt |
| 2 | Möbelproduktbilder (5 Stück) | Kategorisierungsdemo |
| 3 | Accessoire-Bilder (5 Stück) | Multi-Attribut-Extraktionsdemo |
| 4 | Bestehendes Tag-System-Master | Standardisierungsdemo |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispielproduktbildern | 2 Stunden |
| Überprüfung der Pipeline-Ausführung | 2 Stunden |
| Erfassung von Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Ähnliche Produktsuche
- Automatische Produktbeschreibungsgenerierung
- Trendanalyse-Integration

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Image Analyzer) | Bildanalyse durch Bedrock/Rekognition |
| Lambda (Tag Generator) | Attribut-Tag-Generierung und -Standardisierung |
| Lambda (Catalog Updater) | Katalog-Metadatenregistrierung |
| Lambda (Report Generator) | Generierung von Verarbeitungszusammenfassungsberichten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| Unzureichende Bildanalysegenauigkeit | Verwendung vorab analysierter Ergebnisse |
| Bedrock-Verzögerung | Anzeige vorab generierter Tags |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Verifizierte UI/UX-Screenshots (AWS-Verifizierung 2026-05-10)

Gleiche Richtlinie wie Phase 7: Aufnahme von **UI/UX-Bildschirmen, die E-Commerce-Mitarbeiter tatsächlich in ihrer täglichen Arbeit verwenden**.
Bildschirme für technische Benutzer (Step Functions-Grafiken usw.) sind ausgeschlossen.

### Auswahl des Ausgabeziels: Standard-S3 vs. FSxN S3AP

UC11 unterstützt seit dem Update vom 2026-05-10 den Parameter `OutputDestination`.
Durch **Zurückschreiben von KI-Ergebnissen auf dasselbe FSx-Volume** können SMB/NFS-Benutzer
automatisch generierte Tag-JSONs innerhalb der Verzeichnisstruktur der Produktbilder einsehen
("no data movement"-Muster).

```bash
# STANDARD_S3-Modus (Standard, wie bisher)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP-Modus (KI-Ergebnisse auf FSx ONTAP-Volume zurückschreiben)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS-Spezifikationsbeschränkungen und Workarounds siehe [Abschnitt "AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策).

### 1. Automatische Tagging-Ergebnisse für Produktbilder

KI-Analyseergebnisse, die E-Commerce-Manager bei der Registrierung neuer Produkte erhalten. Rekognition hat 7 Labels aus dem tatsächlichen Bild erkannt
(`Oval` 99,93%, `Food`, `Furniture`, `Table`, `Sweets`, `Cocoa`, `Dessert`).

<!-- SCREENSHOT: uc11-product-tags.png
     Inhalt: Produktbild + KI-erkannte Tag-Liste (mit Konfidenz)
     Maskiert: Konto-ID, Bucket-Name -->
![UC11: Produkt-Tags](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. S3-Ausgabe-Bucket — Überblick über Tag- und Qualitätsprüfungsergebnisse

Bildschirm, auf dem E-Commerce-Betriebsmitarbeiter Batch-Verarbeitungsergebnisse überprüfen.
Mit den 2 Präfixen `tags/` und `quality/` wird für jedes Produkt ein JSON generiert.

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     Inhalt: S3-Konsole mit tags/-, quality/-Präfixen
     Maskiert: Konto-ID -->
![UC11: S3-Ausgabe-Bucket](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### Gemessene Werte (AWS-Deployment-Verifizierung 2026-05-10)

- **Step Functions-Ausführung**: SUCCEEDED, parallele Verarbeitung von 4 Produktbildern
- **Rekognition**: 7 Labels aus tatsächlichem Bild erkannt (höchste Konfidenz 99,93%)
- **Generierte JSONs**: tags/*.json (~750 Bytes), quality/*.json (~420 Bytes)
- **Tatsächlicher Stack**: `fsxn-retail-catalog-demo` (ap-northeast-1, Verifizierung 2026-05-10)
