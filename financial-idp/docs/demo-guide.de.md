# Automatische Verarbeitung von Verträgen und Rechnungen — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt eine automatisierte Verarbeitungspipeline für Verträge und Rechnungen. Durch die Kombination von OCR-basierter Textextraktion und Entity-Extraktion werden strukturierte Daten automatisch aus unstrukturierten Dokumenten generiert.

**Kernbotschaft der Demo**: Papierbasierte Verträge und Rechnungen werden automatisch digitalisiert, und wichtige Informationen wie Beträge, Daten und Geschäftspartner werden sofort extrahiert und strukturiert.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Manager Buchhaltungsabteilung / Vertragsmanagement-Verantwortlicher |
| **Tägliche Aufgaben** | Rechnungsverarbeitung, Vertragsverwaltung, Zahlungsfreigabe |
| **Herausforderung** | Manuelle Eingabe großer Mengen an Papierdokumenten ist zeitaufwändig |
| **Erwartete Ergebnisse** | Automatisierung der Dokumentenverarbeitung und Reduzierung von Eingabefehlern |

### Persona: Herr Yamada (Leiter Buchhaltungsabteilung)

- Verarbeitet monatlich 200+ Rechnungen
- Fehler und Verzögerungen durch manuelle Eingabe sind problematisch
- „Ich möchte, dass Beträge und Zahlungsfristen automatisch extrahiert werden, sobald eine Rechnung eintrifft"

---

## Demo Scenario: Rechnungs-Batch-Verarbeitung

### Gesamtworkflow-Übersicht

```
Dokumentenscan      OCR-Verarbeitung    Entity-           Strukturierte Daten
(PDF/Bild)      →   Textextraktion  →   Extraktion/   →   Ausgabe (JSON)
                                        Klassifizierung
                                        (KI-Analyse)
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Monatlich treffen über 200 Rechnungen ein. Die manuelle Eingabe von Beträgen, Daten und Geschäftspartnern ist zeitaufwändig und fehleranfällig.

**Key Visual**: Liste zahlreicher PDF-Rechnungsdateien

### Section 2: Document Upload (0:45–1:30)

**Narration (Zusammenfassung)**:
> Durch einfaches Ablegen gescannter Dokumente auf dem Dateiserver wird die automatische Verarbeitungspipeline gestartet.

**Key Visual**: Datei-Upload → Automatischer Workflow-Start

### Section 3: OCR & Extraction (1:30–2:30)

**Narration (Zusammenfassung)**:
> OCR extrahiert Text, und KI bestimmt den Dokumenttyp. Rechnungen, Verträge und Quittungen werden automatisch klassifiziert, und wichtige Felder werden aus jedem Dokument extrahiert.

**Key Visual**: OCR-Verarbeitungsfortschritt, Dokumentklassifizierungsergebnisse

### Section 4: Structured Output (2:30–3:45)

**Narration (Zusammenfassung)**:
> Extraktionsergebnisse werden als strukturierte Daten ausgegeben. Beträge, Zahlungsfristen, Geschäftspartnernamen, Rechnungsnummern usw. sind im JSON-Format verfügbar.

**Key Visual**: Extraktionsergebnistabelle (Rechnungsnummer, Betrag, Frist, Geschäftspartner)

### Section 5: Validation & Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> KI bewertet die Zuverlässigkeit der Extraktionsergebnisse und markiert Elemente mit niedriger Zuverlässigkeit. Der Verarbeitungszusammenfassungsbericht bietet einen Überblick über den gesamten Verarbeitungsstatus.

**Key Visual**: Ergebnisse mit Zuverlässigkeitsscore, Verarbeitungszusammenfassungsbericht

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Liste der Rechnungs-PDF-Dateien | Section 1 |
| 2 | Automatischer Workflow-Start | Section 2 |
| 3 | OCR-Verarbeitung/Dokumentklassifizierungsergebnisse | Section 3 |
| 4 | Strukturierte Datenausgabe (JSON/Tabelle) | Section 4 |
| 5 | Verarbeitungszusammenfassungsbericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Die manuelle Verarbeitung von 200 Rechnungen pro Monat ist nicht mehr tragbar" |
| Upload | 0:45–1:30 | „Automatische Verarbeitung startet allein durch Dateiablage" |
| OCR | 1:30–2:30 | „OCR + KI für Dokumentklassifizierung und Feldextraktion" |
| Output | 2:30–3:45 | „Sofort als strukturierte Daten nutzbar" |
| Report | 3:45–5:00 | „Zuverlässigkeitsbewertung zeigt Stellen an, die menschliche Überprüfung erfordern" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Rechnungs-PDFs (10 Stück) | Hauptverarbeitungsobjekt |
| 2 | Vertrags-PDFs (3 Stück) | Dokumentklassifizierungs-Demo |
| 3 | Quittungsbilder (3 Stück) | Bild-OCR-Demo |
| 4 | Scans niedriger Qualität (2 Stück) | Zuverlässigkeitsbewertungs-Demo |

---

## Timeline

### Innerhalb 1 Woche erreichbar

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Beispieldokumenten | 3 Stunden |
| Pipeline-Ausführungsbestätigung | 2 Stunden |
| Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Automatische Integration in Buchhaltungssysteme
- Integration von Genehmigungsworkflows
- Unterstützung mehrsprachiger Dokumente (Englisch, Chinesisch)

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (OCR Processor) | Dokumenttextextraktion mit Textract |
| Lambda (Entity Extractor) | Entity-Extraktion mit Bedrock |
| Lambda (Classifier) | Dokumenttypklassifizierung |
| Amazon Athena | Aggregationsanalyse extrahierter Daten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| OCR-Genauigkeitsverlust | Vorverarbeiteten Text verwenden |
| Bedrock-Verzögerung | Vorab generierte Ergebnisse anzeigen |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über das Ausgabeziel: FSxN S3 Access Point (Pattern A)

UC2 financial-idp ist als **Pattern A: Native S3AP Output** klassifiziert
(siehe `docs/output-destination-patterns.md`).

**Design**: OCR-Ergebnisse von Rechnungen, strukturierte Metadaten und BedRock-Zusammenfassungen werden alle über den FSxN S3 Access Point
auf **dasselbe FSx ONTAP Volume** wie die Original-Rechnungs-PDFs zurückgeschrieben. Standard-S3-Buckets werden
nicht erstellt („no data movement"-Pattern).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: S3 AP Alias zum Lesen von Eingabedaten
- `S3AccessPointOutputAlias`: S3 AP Alias zum Schreiben von Ausgaben (kann mit Eingabe identisch sein)

**Deployment-Beispiel**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (andere erforderliche Parameter)
```

**Sichtbarkeit für SMB/NFS-Benutzer**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # Original-Rechnung
  └── summaries/2026/05/                # KI-generierte Zusammenfassung (im selben Volume)
      └── invoice_001.json
```

Für AWS-Spezifikationsbeschränkungen siehe
[Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" im Projekt-README](../../README.md#aws-仕様上の制約と回避策)
sowie [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verifizierte UI/UX-Screenshots

Gemäß der gleichen Richtlinie wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14 werden **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich
sehen**, als Ziel betrachtet. Technische Ansichten (Step Functions Graph, CloudFormation
Stack-Events usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ⚠️ **E2E-Verifizierung**: Nur teilweise Funktionen (zusätzliche Verifizierung in Produktionsumgebung empfohlen)
- 📸 **UI/UX-Aufnahme**: ✅ SFN Graph abgeschlossen (Phase 8 Theme D, Commit 081cc66)

### Aufnahmen bei Re-Deployment-Verifizierung am 2026-05-10 (UI/UX-fokussiert)

#### UC2 Step Functions Graph view (SUCCEEDED)

![UC2 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

Die Step Functions Graph View ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus jedes Lambda / Parallel / Map State
farblich visualisiert.

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC2 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### UI/UX-Zielbildschirme bei Re-Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (textract-results/, comprehend-entities/, reports/)
- Textract OCR-Ergebnis-JSON (aus Verträgen und Rechnungen extrahierte Felder)
- Comprehend Entity-Erkennungsergebnisse (Organisationsnamen, Daten, Beträge)
- Von Bedrock generierte Zusammenfassungsberichte

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - Voraussetzungen mit `bash scripts/verify_phase7_prerequisites.sh` prüfen (gemeinsame VPC/S3 AP vorhanden)
   - Lambda-Paket mit `UC=financial-idp bash scripts/package_generic_uc.sh`
   - Deployment mit `bash scripts/deploy_generic_ucs.sh UC2`

2. **Beispieldaten platzieren**:
   - Beispieldateien über S3 AP Alias mit Präfix `invoices/` hochladen
   - Step Functions `fsxn-financial-idp-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Ausgabe-Bucket `fsxn-financial-idp-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSONs (Format aus `build/preview_*.html` als Referenz)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierung**:
   - Automatische Maskierung mit `python3 scripts/mask_uc_demos.py financial-idp-demo`
   - Zusätzliche Maskierung nach `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - Löschen mit `bash scripts/cleanup_generic_ucs.sh UC2`
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
