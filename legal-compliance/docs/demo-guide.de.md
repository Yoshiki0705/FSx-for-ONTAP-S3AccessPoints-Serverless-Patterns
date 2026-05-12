# Dateiserverberechtigungen-Audit — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Diese Demo zeigt einen automatisierten Audit-Workflow zur Erkennung übermäßiger Zugriffsberechtigungen auf Dateiservern. Es werden NTFS-ACLs analysiert, Einträge identifiziert, die gegen das Prinzip der geringsten Rechte verstoßen, und Compliance-Berichte automatisch generiert.

**Kernbotschaft der Demo**: Automatisierung von Dateiserver-Berechtigungsaudits, die manuell mehrere Wochen dauern würden, und sofortige Visualisierung von Risiken durch übermäßige Berechtigungen.

**Geschätzte Dauer**: 3–5 Minuten

---

## Target Audience & Persona

| Kategorie | Details |
|------|------|
| **Position** | Informationssicherheitsbeauftragter / IT-Compliance-Manager |
| **Tägliche Aufgaben** | Überprüfung von Zugriffsberechtigungen, Audit-Unterstützung, Verwaltung von Sicherheitsrichtlinien |
| **Herausforderung** | Manuelle Überprüfung von Berechtigungen für Tausende von Ordnern ist unrealistisch |
| **Erwartete Ergebnisse** | Früherkennung übermäßiger Berechtigungen und Automatisierung von Compliance-Nachweisen |

### Persona: Herr Sato (Informationssicherheitsmanager)

- Benötigt jährliche Überprüfung der Berechtigungen für alle freigegebenen Ordner
- Möchte gefährliche Einstellungen wie „Everyone Full Control" sofort erkennen
- Möchte Berichte für Wirtschaftsprüfungsgesellschaften effizient erstellen

---

## Demo Scenario: Automatisierung des jährlichen Berechtigungsaudits

### Gesamtübersicht des Workflows

```
Dateiserver     ACL-Erfassung    Berechtigungsanalyse    Berichtserstellung
(NTFS-Freigabe)   →   Metadaten-   →   Verstoßerkennung    →    Audit-Bericht
                   Extraktion            (Regelabgleich)      (KI-Zusammenfassung)
```

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Zusammenfassung der Erzählung**:
> Zeit für das jährliche Audit. Eine Berechtigungsüberprüfung ist für Tausende von freigegebenen Ordnern erforderlich, aber die manuelle Überprüfung würde mehrere Wochen dauern. Wenn übermäßige Berechtigungen unbeaufsichtigt bleiben, steigt das Risiko von Datenlecks.

**Key Visual**: Große Ordnerstruktur mit Overlay „Manuelles Audit: geschätzt 3–4 Wochen"

### Section 2: Workflow Trigger (0:45–1:30)

**Zusammenfassung der Erzählung**:
> Geben Sie das zu prüfende Volume an und starten Sie den Berechtigungs-Audit-Workflow.

**Key Visual**: Step Functions-Ausführungsbildschirm, Zielpfadangabe

### Section 3: ACL Analysis (1:30–2:30)

**Zusammenfassung der Erzählung**:
> NTFS-ACLs für jeden Ordner werden automatisch erfasst und Verstöße anhand folgender Regeln erkannt:
> - Übermäßige Berechtigungen für Everyone / Authenticated Users
> - Ansammlung unnötiger Vererbungen
> - Verbleibende Konten ausgeschiedener Mitarbeiter

**Key Visual**: ACL-Scan-Fortschritt durch parallele Verarbeitung

### Section 4: Results Review (2:30–3:45)

**Zusammenfassung der Erzählung**:
> Abfrage der Erkennungsergebnisse mit SQL. Überprüfung der Anzahl der Verstöße und Verteilung nach Risikoebene.

**Key Visual**: Athena-Abfrageergebnisse — Verstoßliste-Tabelle

### Section 5: Compliance Report (3:45–5:00)

**Zusammenfassung der Erzählung**:
> KI generiert automatisch einen Audit-Bericht. Präsentation von Risikobewertung, empfohlenen Maßnahmen und priorisierten Aktionen.

**Key Visual**: Generierter Audit-Bericht (Risikozusammenfassung + Handlungsempfehlungen)

---

## Screen Capture Plan

| # | Bildschirm | Abschnitt |
|---|------|-----------|
| 1 | Ordnerstruktur des Dateiservers | Section 1 |
| 2 | Start der Workflow-Ausführung | Section 2 |
| 3 | ACL-Scan parallele Verarbeitung läuft | Section 3 |
| 4 | Athena Verstoßerkennungs-Abfrageergebnisse | Section 4 |
| 5 | KI-generierter Audit-Bericht | Section 5 |

---

## Narration Outline

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Manuelle Berechtigungsaudits für Tausende von Ordnern sind unrealistisch" |
| Trigger | 0:45–1:30 | „Zielvolume angeben und Audit starten" |
| Analysis | 1:30–2:30 | „ACLs automatisch erfassen und Richtlinienverstöße erkennen" |
| Results | 2:30–3:45 | „Anzahl der Verstöße und Risikoebene sofort erfassen" |
| Report | 3:45–5:00 | „Audit-Bericht automatisch generieren, Handlungspriorität präsentieren" |

---

## Sample Data Requirements

| # | Daten | Verwendungszweck |
|---|--------|------|
| 1 | Ordner mit normalen Berechtigungen (50+) | Baseline |
| 2 | Everyone Full Control-Einstellung (5 Fälle) | Hochrisiko-Verstoß |
| 3 | Verbleibende Konten ausgeschiedener Mitarbeiter (3 Fälle) | Mittleres Risiko-Verstoß |
| 4 | Ordner mit übermäßiger Vererbung (10 Fälle) | Niedriges Risiko-Verstoß |

---

## Timeline

### Erreichbar innerhalb von 1 Woche

| Aufgabe | Erforderliche Zeit |
|--------|---------|
| Generierung von Beispiel-ACL-Daten | 2 Stunden |
| Überprüfung der Workflow-Ausführung | 2 Stunden |
| Erfassung von Bildschirmaufnahmen | 2 Stunden |
| Erstellung des Erzählungsskripts | 2 Stunden |
| Videobearbeitung | 4 Stunden |

### Future Enhancements

- Automatische Erkennung ausgeschiedener Mitarbeiter durch Active Directory-Integration
- Echtzeitüberwachung von Berechtigungsänderungen
- Automatische Ausführung von Korrekturmaßnahmen

---

## Technical Notes

| Komponente | Rolle |
|--------------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (ACL Collector) | NTFS-ACL-Metadatenerfassung |
| Lambda (Policy Checker) | Abgleich von Richtlinienverstößen |
| Lambda (Report Generator) | Audit-Berichtserstellung durch Bedrock |
| Amazon Athena | SQL-Analyse von Verstoßdaten |

### Fallback

| Szenario | Maßnahme |
|---------|------|
| ACL-Erfassung fehlgeschlagen | Verwendung vorab erfasster Daten |
| Bedrock-Verzögerung | Anzeige vorab generierter Berichte |

---

*Dieses Dokument ist ein Produktionsleitfaden für Demo-Videos für technische Präsentationen.*

---

## Über das Ausgabeziel: FSxN S3 Access Point (Pattern A)

UC1 legal-compliance wird als **Pattern A: Native S3AP Output** klassifiziert
(siehe `docs/output-destination-patterns.md`).

**Design**: Vertragsmetadaten, Audit-Logs und Zusammenfassungsberichte werden alle über den FSxN S3 Access Point
auf **dasselbe FSx ONTAP-Volume** wie die ursprünglichen Vertragsdaten zurückgeschrieben. Standard-S3-Buckets werden
nicht erstellt („no data movement"-Muster).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: S3 AP Alias zum Lesen von Eingabevertragsdaten
- `S3AccessPointOutputAlias`: S3 AP Alias zum Schreiben von Ausgaben (kann mit Eingabe identisch sein)

**Deployment-Beispiel**:
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (andere erforderliche Parameter)
```

**Sichtbarkeit für SMB/NFS-Benutzer**:
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # Originalvertrag
  └── summaries/2026/05/                # KI-generierte Zusammenfassung (im selben Volume)
      └── contract_ABC.json
```

Informationen zu AWS-Spezifikationsbeschränkungen finden Sie im
[Abschnitt „AWS-Spezifikationsbeschränkungen und Workarounds" der Projekt-README](../../README.md#aws-仕様上の制約と回避策)
sowie in [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Verifizierte UI/UX-Screenshots

Wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14 konzentrieren wir uns auf **UI/UX-Bildschirme, die Endbenutzer
in ihrer täglichen Arbeit tatsächlich sehen**. Technische Ansichten (Step Functions-Grafik, CloudFormation
Stack-Ereignisse usw.) werden in `docs/verification-results-*.md` konsolidiert.

### Verifizierungsstatus für diesen Use Case

- ✅ **E2E-Ausführung**: In Phase 1-6 bestätigt (siehe Root-README)
- 📸 **UI/UX-Neuaufnahme**: ✅ Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UC1 Step Functions-Grafik, Lambda-Ausführungserfolg bestätigt)
- 🔄 **Reproduktionsmethode**: Siehe „Aufnahmeleitfaden" am Ende dieses Dokuments

### Aufgenommen bei Redeployment-Verifizierung am 2026-05-10 (UI/UX-Fokus)

#### UC1 Step Functions Graph view (SUCCEEDED)

![UC1 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

Die Step Functions Graph-Ansicht ist der wichtigste Endbenutzer-Bildschirm, der den Ausführungsstatus jedes Lambda / Parallel / Map-Status
farblich visualisiert.

#### UC1 Step Functions Graph (SUCCEEDED — Phase 8 Theme D/E/N Verifizierung, 2:38:20)

![UC1 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-succeeded.png)

Ausgeführt mit aktiviertem Phase 8 Theme E (event-driven) + Theme N (observability).
549 ACL-Iterationen, 3871 Events, alle Schritte SUCCEEDED in 2:38:20.

#### UC1 Step Functions Graph (Zoom-Ansicht — Details zu jedem Schritt)

![UC1 Step Functions Graph (Zoom-Ansicht)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-zoomed.png)

#### UC1 S3 Access Points for FSx ONTAP (Konsolenansicht)

![UC1 S3 Access Points for FSx ONTAP](../../docs/screenshots/masked/uc1-demo/s3-access-points-for-fsx.png)

#### UC1 S3 Access Point Details (Übersichtsansicht)

![UC1 S3 Access Point Details](../../docs/screenshots/masked/uc1-demo/s3ap-detail-overview.png)

### Vorhandene Screenshots (relevante aus Phase 1-6)

#### UC1 CloudFormation Stack-Deployment abgeschlossen (Verifizierung am 2026-05-02)

![UC1 CloudFormation Stack-Deployment abgeschlossen (Verifizierung am 2026-05-02)](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### UC1 Step Functions SUCCEEDED (E2E-Ausführung erfolgreich)

![UC1 Step Functions SUCCEEDED (E2E-Ausführung erfolgreich)](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### UI/UX-Zielbildschirme bei Neuverifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (audit-reports/, acl-audits/, athena-results/ Präfixe)
- Athena-Abfrageergebnisse (ACL-Verstoßerkennungs-SQL)
- Bedrock-generierter Audit-Bericht (Compliance-Verstoßzusammenfassung)
- SNS-Benachrichtigungs-E-Mail (Audit-Alarm)

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Überprüfung der Voraussetzungen (gemeinsame VPC/S3 AP vorhanden)
   - `UC=legal-compliance bash scripts/package_generic_uc.sh` für Lambda-Paket
   - `bash scripts/deploy_generic_ucs.sh UC1` für Deployment

2. **Beispieldatenplatzierung**:
   - Beispieldateien über S3 AP Alias in `contracts/`-Präfix hochladen
   - Step Functions `fsxn-legal-compliance-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Ausgabe-Bucket `fsxn-legal-compliance-demo-output-<account>`
   - Vorschau der AI/ML-Ausgabe-JSON (siehe Format in `build/preview_*.html`)
   - SNS-E-Mail-Benachrichtigung (falls zutreffend)

4. **Maskierungsverarbeitung**:
   - `python3 scripts/mask_uc_demos.py legal-compliance-demo` für automatische Maskierung
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC1` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)

---

## Geschätzte Ausführungszeit (Phase 8 Verifizierungsergebnisse)

Die Verarbeitungszeit von UC1 ist proportional zur Anzahl der Dateien auf dem ONTAP-Volume.

| Schritt | Verarbeitungsinhalt | Gemessener Wert (549 Dateien) |
|---------|---------|---------------------|
| Discovery | Abrufen der Dateiliste über ONTAP REST API | 8 Minuten |
| AclCollection (Map) | NTFS-ACL-Erfassung für jede Datei | 2 Stunden 20 Minuten |
| AthenaAnalysis | Glue Data Catalog + Athena-Abfrage | 5 Minuten |
| ReportGeneration | Berichtserstellung mit Bedrock Nova Lite | 5 Minuten |
| **Gesamt** | | **2 Stunden 38 Minuten** |

### Geschätzte Verarbeitungszeit nach Dateianzahl

| Dateianzahl | Geschätzte Gesamtzeit | Empfohlene Verwendung |
|-----------|------------|---------|
| 10 | ~5 Minuten | Schnelldemo |
| 50 | ~15 Minuten | Standard-Demo |
| 100 | ~30 Minuten | Detaillierte Verifizierung |
| 500+ | ~2,5 Stunden | Produktionsäquivalenter Test |

### Tipps zur Leistungsoptimierung

- **Map state MaxConcurrency**: Standard 40 → Erhöhung auf 100 kann AclCollection-Zeit verkürzen
- **Lambda-Speicher**: 512 MB oder mehr für Discovery Lambda empfohlen (schnelleres VPC ENI-Anhängen)
- **Lambda-Timeout**: 900s empfohlen für Umgebungen mit vielen Dateien (Standard 300s reicht nicht aus)
- **SnapStart**: Python 3.13 + SnapStart kann Kaltstart um 50-80% reduzieren

### Phase 8 neue Funktionen

- **Event-driven Trigger** (`EnableEventDriven=true`): Automatischer Start beim Hinzufügen von Dateien zu S3AP
- **CloudWatch Alarms** (`EnableCloudWatchAlarms=true`): Automatische Benachrichtigung bei SFN-Fehler + Lambda-Fehler
- **EventBridge-Fehlerbenachrichtigung**: Push-Benachrichtigung an SNS Topic bei Ausführungsfehlern
