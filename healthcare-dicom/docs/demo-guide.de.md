# DICOM-Anonymisierungsworkflow — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt einen Workflow zur Anonymisierung medizinischer Bilder (DICOM). Es wird der Prozess zur automatischen Entfernung persönlicher Patienteninformationen für die gemeinsame Nutzung von Forschungsdaten und zur Überprüfung der Anonymisierungsqualität demonstriert.

**Kernbotschaft der Demo**: Automatische Entfernung von Patientenidentifikationsinformationen aus DICOM-Dateien und sichere Generierung anonymisierter Datensätze für die Forschungsnutzung.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Medizinischer Informationsmanager / Klinischer Forschungsdatenmanager |
| **Tägliche Aufgaben** | Verwaltung medizinischer Bilder, Bereitstellung von Forschungsdaten, Datenschutz |
| **Herausforderung** | Manuelle Anonymisierung großer Mengen von DICOM-Dateien ist zeitaufwändig und fehleranfällig |
| **Erwartete Ergebnisse** | Sichere und zuverlässige Anonymisierung mit automatisierter Audit-Trail |

### Persona: Herr Takahashi (Klinischer Forschungsdatenmanager)

- Benötigt Anonymisierung von 10.000+ DICOM-Dateien für multizentrische Forschung
- Zuverlässige Entfernung von Patientennamen, IDs, Geburtsdaten usw. erforderlich
- „Ich möchte null Anonymisierungslücken garantieren und gleichzeitig die Bildqualität beibehalten"

---

## Demo Scenario: DICOM-Anonymisierung für gemeinsame Forschungsdatennutzung

### Gesamtübersicht des Workflows

```
DICOM-Dateien     Tag-Analyse      Anonymisierungs-    Qualitäts-
(mit Patienten-  → Metadaten-   →  verarbeitung     →  überprüfung
informationen)     extraktion       Entfernung pers.    Anonymisierungs-
                                    Informationen       bestätigung
                                    Hashing             Berichtserstellung
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Narration (Zusammenfassung)**:
> Für multizentrische Forschung müssen 10.000 DICOM-Dateien anonymisiert werden. Manuelle Verarbeitung birgt Fehlerrisiken, und Datenschutzverletzungen sind inakzeptabel.

**Key Visual**: DICOM-Dateiliste, Hervorhebung von Patienteninformations-Tags

### Section 2: Workflow Trigger (0:45–1:30)

**Narration (Zusammenfassung)**:
> Spezifizierung des zu anonymisierenden Datensatzes und Start des Anonymisierungs-Workflows. Konfiguration der Anonymisierungsregeln (Entfernung, Hashing, Generalisierung).

**Key Visual**: Workflow-Start, Bildschirm zur Konfiguration der Anonymisierungsregeln

### Section 3: De-identification (1:30–2:30)

**Narration (Zusammenfassung)**:
> Automatische Verarbeitung der persönlichen Informations-Tags jeder DICOM-Datei. Patientenname → Hash, Geburtsdatum → Altersbereich, Einrichtungsname → anonymer Code. Bildpixeldaten werden beibehalten.

**Key Visual**: Fortschritt der Anonymisierungsverarbeitung, Vorher/Nachher der Tag-Konvertierung

### Section 4: Quality Verification (2:30–3:45)

**Narration (Zusammenfassung)**:
> Automatische Überprüfung der anonymisierten Dateien. Scannen aller Tags auf verbleibende persönliche Informationen. Überprüfung der Bildintegrität.

**Key Visual**: Überprüfungsergebnisse — Anonymisierungserfolgsrate, Liste verbleibender Risiko-Tags

### Section 5: Audit Report (3:45–5:00)

**Narration (Zusammenfassung)**:
> Automatische Generierung eines Audit-Berichts für die Anonymisierungsverarbeitung. Aufzeichnung der Verarbeitungsanzahl, Anzahl entfernter Tags, Überprüfungsergebnisse. Verwendbar als Einreichungsmaterial für Forschungsethikkommissionen.

**Key Visual**: Audit-Bericht (Verarbeitungszusammenfassung + Compliance-Nachweis)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | DICOM-Dateiliste (vor Anonymisierung) | Section 1 |
| 2 | Workflow-Start / Regelkonfiguration | Section 2 |
| 3 | Fortschritt der Anonymisierungsverarbeitung | Section 3 |
| 4 | Qualitätsüberprüfungsergebnisse | Section 4 |
| 5 | Audit-Bericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Anonymisierungslücken bei großen DICOM-Mengen sind inakzeptabel" |
| Trigger | 0:45–1:30 | „Anonymisierungsregeln konfigurieren und Workflow starten" |
| Processing | 1:30–2:30 | „Automatische Entfernung persönlicher Informations-Tags, Bildqualität wird beibehalten" |
| Verification | 2:30–3:45 | „Vollständiger Tag-Scan bestätigt null Anonymisierungslücken" |
| Report | 3:45–5:00 | „Automatische Generierung von Audit-Trails, einreichbar bei Ethikkommissionen" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Test-DICOM-Dateien (20 Stück) | Hauptverarbeitungsziel |
| 2 | DICOM mit komplexer Tag-Struktur (5 Stück) | Edge Cases |
| 3 | DICOM mit privaten Tags (3 Stück) | Hochrisiko-Überprüfung |

---

## Timeline

### Erreichbar innerhalb 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Vorbereitung von Test-DICOM-Daten | 3 Stunden |
| Bestätigung der Pipeline-Ausführung | 2 Stunden |
| Erfassung von Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Narrationsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Automatische Erkennung und Entfernung von Text in Bildern (Burn-in)
- FHIR-Integration für Anonymisierungs-Mapping-Verwaltung
- Differenzielle Anonymisierung (inkrementelle Verarbeitung zusätzlicher Daten)

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Tag Parser) | DICOM-Tag-Analyse / Erkennung persönlicher Informationen |
| Lambda (De-identifier) | Tag-Anonymisierungsverarbeitung |
| Lambda (Verifier) | Qualitätsüberprüfung der Anonymisierung |
| Lambda (Report Generator) | Audit-Berichtserstellung |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| DICOM-Parsing-Fehler | Verwendung vorverarbeiteter Daten |
| Überprüfungsfehler | Wechsel zu manuellem Bestätigungsablauf |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über das Ausgabeziel: FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom ist als **Pattern A: Native S3AP Output** klassifiziert
(siehe `docs/output-destination-patterns.md`).

**Design**: DICOM-Metadaten, Anonymisierungsergebnisse, PII-Erkennungslogs werden alle über FSxN S3 Access Point
in **dasselbe FSx ONTAP-Volume** wie die ursprünglichen medizinischen DICOM-Bilder zurückgeschrieben. Standard-S3-Buckets werden
nicht erstellt („no data movement"-Muster).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: S3 AP Alias zum Lesen von Eingabedaten
- `S3AccessPointOutputAlias`: S3 AP Alias zum Schreiben von Ausgaben (kann mit Eingabe identisch sein)

**Deployment-Beispiel**:
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (andere erforderliche Parameter)
```

**Sichtbarkeit für SMB/NFS-Benutzer**:
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # Original-DICOM
  └── metadata/patient_001/             # AI-Anonymisierungsergebnisse (im selben Volume)
      └── study_A_anonymized.json
```

Für AWS-Spezifikationsbeschränkungen siehe
[Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" in der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
sowie [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verifizierte UI/UX-Screenshots

Gemäß der gleichen Richtlinie wie bei den Demos für Phase 7 UC15/16/17 und UC6/11/14 werden **UI/UX-Bildschirme, die Endbenutzer in ihrer täglichen Arbeit tatsächlich
sehen**, als Ziel betrachtet. Technische Ansichten (Step Functions-Graph, CloudFormation-
Stack-Ereignisse usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ⚠️ **E2E-Verifizierung**: Nur teilweise Funktionen (zusätzliche Verifizierung in Produktionsumgebung empfohlen)
- 📸 **UI/UX-Aufnahme**: ✅ SFN Graph abgeschlossen (Phase 8 Theme D, Commit c66084f)

### Aufnahmen bei Re-Deployment-Verifizierung am 2026-05-10 (UI/UX-fokussiert)

#### UC5 Step Functions Graph view (SUCCEEDED)

![UC5 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

Step Functions Graph view ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus jedes Lambda / Parallel / Map-States
farblich visualisiert.

### Vorhandene Screenshots (relevante aus Phase 1-6)

![UC5 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![UC5 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### UI/UX-Zielbildschirme bei erneuter Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (dicom-metadata/, deid-reports/, diagnoses/)
- Comprehend Medical Entity-Erkennungsergebnisse (Cross-Region)
- Anonymisierte DICOM-Metadaten-JSON

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Überprüfung der Voraussetzungen (gemeinsame VPC/S3 AP-Verfügbarkeit)
   - `UC=healthcare-dicom bash scripts/package_generic_uc.sh` für Lambda-Paketierung
   - `bash scripts/deploy_generic_ucs.sh UC5` für Deployment

2. **Beispieldatenplatzierung**:
   - Hochladen von Beispieldateien über S3 AP Alias zum `dicom/`-Präfix
   - Start von Step Functions `fsxn-healthcare-dicom-demo-workflow` (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Ausgabe-Bucket `fsxn-healthcare-dicom-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (unter Bezugnahme auf das Format `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierungsverarbeitung**:
   - `python3 scripts/mask_uc_demos.py healthcare-dicom-demo` für automatische Maskierung
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC5` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
