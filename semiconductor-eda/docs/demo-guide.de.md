# EDA Design File Validation — Demo-Leitfaden

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Executive Summary

Dieser Leitfaden definiert eine technische Demonstration für Halbleiter-Design-Ingenieure. Die Demo zeigt einen automatisierten Qualitätsvalidierungs-Workflow für Design-Dateien (GDS/OASIS) und demonstriert den Wert der Effizienzsteigerung bei Design-Reviews vor dem Tape-out.

**Kernbotschaft der Demo**: Qualitätsprüfungen über IP-Blöcke hinweg, die Design-Ingenieure manuell durchführten, werden durch einen automatisierten Workflow innerhalb weniger Minuten abgeschlossen, und KI-generierte Design-Review-Berichte ermöglichen sofortiges Handeln.

**Geschätzte Dauer**: 3–5 Minuten (Screencast-Video mit Narration)

---

## Target Audience & Persona

### Primary Audience: EDA-Endanwender (Design-Ingenieure)

| Kategorie | Details |
|------|------|
| **Position** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tägliche Aufgaben** | Layout-Design, DRC-Ausführung, IP-Block-Integration, Tape-out-Vorbereitung |
| **Herausforderungen** | Zeitaufwändige übergreifende Qualitätserfassung mehrerer IP-Blöcke |
| **Tool-Umgebung** | EDA-Tools wie Calibre, Virtuoso, IC Compiler, Innovus etc. |
| **Erwartete Ergebnisse** | Frühzeitige Erkennung von Design-Qualitätsproblemen und Einhaltung des Tape-out-Zeitplans |

### Persona: Herr Tanaka (Physical Design Lead)

- Verwaltet 40+ IP-Blöcke in einem großen SoC-Projekt
- Muss 2 Wochen vor Tape-out ein Qualitätsreview aller Blöcke durchführen
- Individuelle Überprüfung der GDS/OASIS-Dateien jedes Blocks ist unrealistisch
- „Ich möchte eine Qualitätszusammenfassung aller Blöcke auf einen Blick erfassen"

---

## Demo Scenario: Pre-tapeout Quality Review

### Szenario-Übersicht

In der Qualitätsreview-Phase vor dem Tape-out führt der Design Lead eine automatisierte Qualitätsvalidierung für mehrere IP-Blöcke (40+ Dateien) durch und trifft Entscheidungen basierend auf KI-generierten Review-Berichten.

### Workflow-Gesamtbild

```
Design-Dateien        Automatisierte      Analyseergebnisse      KI-Review
(GDS/OASIS)    →     Validierung    →    Statistische      →    Berichtserstellung
                     Workflow-Trigger    Aggregation            (natürliche Sprache)
                                         (Athena SQL)
```

### In der Demo demonstrierter Wert

1. **Zeitersparnis**: Übergreifendes Review, das manuell Tage dauert, in Minuten abgeschlossen
2. **Vollständigkeit**: Lückenlose Validierung aller IP-Blöcke
3. **Quantitative Bewertung**: Objektive Qualitätsbewertung durch statistische Ausreißererkennung (IQR-Methode)
4. **Handlungsfähigkeit**: KI präsentiert konkrete empfohlene Maßnahmen

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Bildschirm**: Dateiliste des Design-Projekts (40+ GDS/OASIS-Dateien)

**Narrations-Zusammenfassung**:
> 2 Wochen vor Tape-out. Die Design-Qualität von über 40 IP-Blöcken muss überprüft werden.
> Jede Datei einzeln mit EDA-Tools zu öffnen und zu prüfen ist nicht realistisch.
> Anomalien in der Zellanzahl, Ausreißer bei Bounding Boxes, Verstöße gegen Namenskonventionen – eine Methode zur übergreifenden Erkennung ist erforderlich.

**Key Visual**:
- Verzeichnisstruktur der Design-Dateien (.gds, .gds2, .oas, .oasis)
- Text-Overlay „Manuelles Review: geschätzt 3–5 Tage"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Bildschirm**: Design-Ingenieur triggert den Qualitätsvalidierungs-Workflow

**Narrations-Zusammenfassung**:
> Nach Erreichen des Design-Meilensteins wird der Qualitätsvalidierungs-Workflow gestartet.
> Durch bloße Angabe des Zielverzeichnisses beginnt die automatisierte Validierung aller Design-Dateien.

**Key Visual**:
- Workflow-Ausführungsbildschirm (Step Functions-Konsole)
- Eingabeparameter: Ziel-Volume-Pfad, Dateifilter (.gds/.oasis)
- Bestätigung des Ausführungsstarts

**Ingenieur-Aktion**:
```
Ziel: Alle Design-Dateien unter /vol/eda_designs/
Filter: .gds, .gds2, .oas, .oasis
Ausführung: Start des Qualitätsvalidierungs-Workflows
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Bildschirm**: Fortschrittsanzeige während der Workflow-Ausführung

**Narrations-Zusammenfassung**:
> Der Workflow führt automatisch Folgendes aus:
> 1. Erkennung und Auflistung der Design-Dateien
> 2. Metadaten-Extraktion aus dem Header jeder Datei (library_name, cell_count, bounding_box, units)
> 3. Statistische Analyse der extrahierten Daten (SQL-Abfragen)
> 4. KI-generierte Design-Review-Berichtserstellung
>
> Selbst bei großen GDS-Dateien (mehrere GB) erfolgt die Verarbeitung schnell, da nur der Header-Teil (64KB) gelesen wird.

**Key Visual**:
- Sequenzielle Fertigstellung der einzelnen Workflow-Schritte
- Anzeige der parallelen Verarbeitung mehrerer Dateien (Map State)
- Verarbeitungszeit: ca. 2–3 Minuten (bei 40 Dateien)

---

### Section 4: Results Review (2:30–3:45)

**Bildschirm**: Athena SQL-Abfrageergebnisse und statistische Zusammenfassung

**Narrations-Zusammenfassung**:
> Analyseergebnisse können frei mit SQL abgefragt werden.
> Beispielsweise sind Ad-hoc-Analysen wie „Zellen mit abnormal großer Bounding Box anzeigen" möglich.

**Key Visual — Athena-Abfragebeispiel**:
```sql
-- Erkennung von Bounding-Box-Ausreißern
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Abfrageergebnis**:

| file_key | library_name | width | height | Bewertung |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Ausreißer |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Ausreißer |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Ausreißer |

---

### Section 5: Actionable Insights (3:45–5:00)

**Bildschirm**: KI-generierter Design-Review-Bericht

**Narrations-Zusammenfassung**:
> Die KI interpretiert die statistischen Analyseergebnisse und generiert automatisch einen Review-Bericht für Design-Ingenieure.
> Dieser enthält Risikobewertungen, konkrete empfohlene Maßnahmen und priorisierte Action Items.
> Basierend auf diesem Bericht kann in Review-Meetings vor dem Tape-out sofort mit der Diskussion begonnen werden.

**Key Visual — KI-Review-Bericht (Auszug)**:

```markdown
# Design-Review-Bericht

## Risikobewertung: Medium

## Zusammenfassung der Erkenntnisse
- Bounding-Box-Ausreißer: 3 Fälle
- Verstöße gegen Namenskonventionen: 2 Fälle
- Ungültige Dateien: 2 Fälle

## Empfohlene Maßnahmen (nach Priorität)
1. [High] Ursachenuntersuchung für 2 ungültige Dateien
2. [Medium] Prüfung der Layout-Optimierung für analog_frontend.oas
3. [Low] Vereinheitlichung der Namenskonventionen (block-a-io → block_a_io)
```

**Abschluss**:
> Übergreifendes Review, das manuell Tage dauerte, in Minuten abgeschlossen.
> Design-Ingenieure können sich auf die Überprüfung der Analyseergebnisse und Entscheidungsfindung konzentrieren.

---

## Screen Capture Plan

### Liste der erforderlichen Bildschirmaufnahmen

| # | Bildschirm | Abschnitt | Anmerkungen |
|---|------|-----------|------|
| 1 | Design-Dateiverzeichnisliste | Section 1 | Dateistruktur auf FSx ONTAP |
| 2 | Workflow-Startbildschirm | Section 2 | Step Functions-Konsole |
| 3 | Workflow in Ausführung (Map State parallele Verarbeitung) | Section 3 | Fortschritt sichtbar |
| 4 | Workflow-Abschlussbildschirm | Section 3 | Alle Schritte erfolgreich |
| 5 | Athena Query Editor + Ergebnisse | Section 4 | Ausreißererkennungs-Abfrage |
| 6 | Metadaten-JSON-Ausgabebeispiel | Section 4 | Extraktionsergebnis für 1 Datei |
| 7 | Vollständiger KI-Design-Review-Bericht | Section 5 | Markdown-Rendering-Anzeige |
| 8 | SNS-Benachrichtigungs-E-Mail | Section 5 | Berichtsfertigstellungsbenachrichtigung |

### Aufnahmeverfahren

1. Beispieldaten in der Demo-Umgebung platzieren
2. Workflow manuell ausführen und bei jedem Schritt Bildschirmaufnahmen machen
3. Abfragen in der Athena-Konsole ausführen und Ergebnisse aufnehmen
4. Generierten Bericht von S3 herunterladen und anzeigen

---

## Verifizierte UI/UX-Screenshots (Reverifizierung 2026-05-10)

Nach derselben Richtlinie wie Phase 7 UC15/16/17 wurden **UI/UX-Bildschirme aufgenommen, die Design-Ingenieure in ihrer täglichen Arbeit tatsächlich sehen**. Technische Ansichten wie Step Functions-Graphen wurden ausgeschlossen (Details siehe
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md)).

### 1. FSx for NetApp ONTAP Volumes — Volume für Design-Dateien

Volume-Liste von ONTAP aus Sicht des Design-Ingenieurs. GDS/OASIS-Dateien werden in `eda_demo_vol` mit NTFS ACL-Verwaltung platziert.

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     Inhalt: FSx-Konsole mit ONTAP Volumes-Liste (eda_demo_vol etc.), Status=Created, Type=ONTAP
     Maskierung: Konto-ID, tatsächliche SVM-ID, Dateisystem-ID -->
![UC6: FSx Volumes-Liste](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. S3-Ausgabe-Bucket — Liste der Design-Dokumente und Analyseergebnisse

Bildschirm, auf dem Design-Review-Verantwortliche nach Workflow-Abschluss die Ergebnisse überprüfen.
Organisiert in 3 Präfixen: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     Inhalt: S3-Konsole zur Überprüfung der Top-Level-Präfixe des Buckets
     Maskierung: Konto-ID, Bucket-Namenspräfix -->
![UC6: S3-Ausgabe-Bucket](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. S3-Ausgabe-Bucket — Liste der Design-Dokumente und Analyseergebnisse

Bildschirm, auf dem Design-Review-Verantwortliche nach Workflow-Abschluss die Ergebnisse überprüfen.
Organisiert in 3 Präfixen: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     Inhalt: S3-Konsole zur Überprüfung der Top-Level-Präfixe des Buckets
     Maskierung: Konto-ID, Bucket-Namenspräfix -->
![UC6: S3-Ausgabe-Bucket](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Athena-Abfrageergebnisse — SQL-Analyse von EDA-Metadaten

Bildschirm, auf dem Design Leads ad hoc DRC-Informationen erkunden.
Workgroup ist `fsxn-eda-uc6-workgroup`, Datenbank ist `fsxn-eda-uc6-db`.

<!-- SCREENSHOT: uc6-athena-query-result.png
     Inhalt: SELECT-Ergebnisse der EDA-Metadatentabelle (file_key, library_name, cell_count, bounding_box)
     Maskierung: Konto-ID -->
![UC6: Athena-Abfrageergebnisse](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Bedrock-generierter Design-Review-Bericht

**Highlight-Funktion von UC6**: Basierend auf Athena DRC-Aggregationsergebnissen generiert Bedrock Nova Lite
einen japanischsprachigen Review-Bericht für Physical Design Leads.

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     Inhalt: Executive Summary + Zellanzahlanalyse + Liste der Namenskonventionsverstöße + Risikobewertung (High/Medium/Low)
     Tatsächlicher Beispielinhalt:
       ## 設計レビューサマリー
       ### エグゼクティブサマリー
       今回のDRC集計結果に基づき、設計品質の全体評価を以下に示します。
       設計ファイルは合計2件で、セル数分布は安定しており、バウンディングボックス外れ値は確認されませんでした。
       しかし、命名規則違反が6件見つかりました。
       ...
       ### リスク評価
       - **High**: なし
       - **Medium**: 命名規則違反が6件確認されました。
       - **Low**: セル数分布やバウンディングボックス外れ値に問題はありません。
     Maskierung: Konto-ID -->
![UC6: Bedrock Design-Review-Bericht](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### Gemessene Werte (AWS-Deployment-Verifizierung 2026-05-10)

- **Step Functions-Ausführungszeit**: ~30 Sekunden (Discovery + Map(2 Dateien) + DRC + Report)
- **Bedrock-generierter Bericht**: 2.093 Bytes (japanisches Markdown-Format)
- **Athena-Abfrage**: 0,02 KB gescannt, Laufzeit 812 ms
- **Tatsächlicher Stack**: `fsxn-eda-uc6` (ap-northeast-1, Stand 2026-05-10 in Betrieb)

---

## Narration Outline

### Ton & Stil

- **Perspektive**: Ich-Perspektive des Design-Ingenieurs (Herr Tanaka)
- **Ton**: Praktisch, problemlösungsorientiert
- **Sprache**: Japanisch (Option für englische Untertitel)
- **Geschwindigkeit**: Langsam und deutlich (für technische Demo)

### Narrations-Struktur

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|--------------|
| Problem | 0:00–0:45 | „Qualitätsprüfung von 40+ Blöcken vor Tape-out erforderlich. Manuell nicht zu schaffen" |
| Trigger | 0:45–1:30 | „Nach Design-Meilenstein einfach Workflow starten" |
| Analysis | 1:30–2:30 | „Header-Analyse → Metadaten-Extraktion → Statistische Analyse läuft automatisch" |
| Results | 2:30–3:45 | „Freie Abfragen mit SQL. Sofortige Identifizierung von Ausreißern" |
| Insights | 3:45–5:00 | „KI-Bericht präsentiert priorisierte Maßnahmen. Direkt für Review-Meetings nutzbar" |

---

## Sample Data Requirements

### Erforderliche Beispieldaten

| # | Datei | Format | Verwendungszweck |
|---|---------|------------|------|
| 1 | `top_chip_v3.gds` | GDSII | Haupt-Chip (groß, 1000+ Zellen) |
| 2 | `block_a_io.gds2` | GDSII | I/O-Block (normale Daten) |
| 3 | `memory_ctrl.oasis` | OASIS | Speicher-Controller (normale Daten) |
| 4 | `analog_frontend.oas` | OASIS | Analogblock (Ausreißer: große BB) |
| 5 | `test_block_debug.gds` | GDSII | Debug-Block (Ausreißer: abnormale Höhe) |
| 6 | `legacy_io_v1.gds2` | GDSII | Legacy-Block (Ausreißer: Breite/Höhe) |
| 7 | `block-a-io.gds2` | GDSII | Beispiel für Namenskonventionsverstoß |
| 8 | `TOP CHIP (copy).gds` | GDSII | Beispiel für Namenskonventionsverstoß |

### Richtlinie zur Generierung von Beispieldaten

- **Minimalkonfiguration**: 8 Dateien (obige Liste) decken alle Demo-Szenarien ab
- **Empfohlene Konfiguration**: 40+ Dateien (erhöhte Überzeugungskraft der statistischen Analyse)
- **Generierungsmethode**: Python-Skript zur Erzeugung von Testdateien mit gültigen GDSII/OASIS-Headern
- **Größe**: Nur Header-Analyse, daher reichen ca. 100KB pro Datei

### Überprüfungspunkte für bestehende Demo-Umgebung

- [ ] Sind Beispieldaten im FSx ONTAP Volume platziert?
- [ ] Ist der S3 Access Point konfiguriert?
- [ ] Existiert die Glue Data Catalog-Tabellendefinition?
- [ ] Ist die Athena Workgroup verfügbar?

---

## Timeline

### Innerhalb 1 Woche erreichbar

| # | Aufgabe | Erforderliche Zeit | Voraussetzungen |
|---|--------|---------|---------|
| 1 | Generierung von Beispieldaten (8 Dateien) | 2 Stunden | Python-Umgebung |
| 2 | Workflow-Ausführungsbestätigung in Demo-Umgebung | 2 Stunden | Bereitgestellte Umgebung |
| 3 | Bildschirmaufnahmen (8 Bildschirme) | 3 Stunden | Nach Abschluss von Aufgabe 2 |
| 4 | Finalisierung des Narrationsskripts | 2 Stunden | Nach Abschluss von Aufgabe 3 |
| 5 | Videobearbeitung (Aufnahmen + Narration) | 4 Stunden | Nach Abschluss von Aufgaben 3, 4 |
| 6 | Review & Korrekturen | 2 Stunden | Nach Abschluss von Aufgabe 5 |
| **Gesamt** | | **15 Stunden** | |

### Voraussetzungen (für 1-Wochen-Erreichung erforderlich)

- Step Functions-Workflow ist bereitgestellt und funktioniert ordnungsgemäß
- Lambda-Funktionen (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) sind funktionsgeprüft
- Athena-Tabellen und -Abfragen sind ausführbar
- Bedrock-Modellzugriff ist aktiviert

### Future Enhancements (zukünftige Erweiterungen)

| # | Erweiterung | Übersicht | Priorität |
|---|---------|------|--------|
| 1 | DRC-Tool-Integration | Direkte Übernahme von Calibre/Pegasus DRC-Ergebnisdateien | High |
| 2 | Interaktives Dashboard | Design-Qualitäts-Dashboard mit QuickSight | Medium |
| 3 | Slack/Teams-Benachrichtigung | Chat-Benachrichtigung bei Fertigstellung des Review-Berichts | Medium |
| 4 | Differenz-Review | Automatische Erkennung und Berichterstattung von Unterschieden zur vorherigen Ausführung | High |
| 5 | Benutzerdefinierte Regeldefinition | Konfigurierbare projektspezifische Qualitätsregeln | Medium |
| 6 | Mehrsprachige Berichte | Berichtserstellung in Englisch/Japanisch/Chinesisch | Low |
| 7 | CI/CD-Integration | Einbindung als automatisches Qualitätsgate im Design-Flow | High |
| 8 | Unterstützung großer Datenmengen | Optimierung der parallelen Verarbeitung für 1000+ Dateien | Medium |

---

## Technical Notes (für Demo-Ersteller)

### Verwendete Komponenten (nur bestehende Implementierung)

| Komponente | Rolle |
|--------------|------|
| Step Functions | Orchestrierung des gesamten Workflows |
| Lambda (Discovery) | Erkennung und Auflistung von Design-Dateien |
| Lambda (MetadataExtraction) | GDSII/OASIS-Header-Parsing und Metadaten-Extraktion |
| Lambda (DrcAggregation) | Ausführung statistischer Analysen mit Athena SQL |
| Lambda (ReportGeneration) | KI-Review-Berichtserstellung mit Bedrock |
| Amazon Athena | SQL-Abfragen auf Metadaten |
| Amazon Bedrock | Natürlichsprachliche Berichtserstellung (Nova Lite / Claude) |

### Fallback bei Demo-Ausführung

| Szenario | Maßnahme |
|---------|------|
| Workflow-Ausführungsfehler | Verwendung vorab aufgezeichneter Ausführungsbildschirme |
| Bedrock-Antwortverzögerung | Anzeige vorab generierter Berichte |
| Athena-Abfrage-Timeout | Anzeige vorab abgerufener Ergebnis-CSV |
| Netzwerkausfall | Alle Bildschirme vorab aufgenommen und als Video erstellt |

---

*Dieses Dokument wurde als Produktionsleitfaden für Demo-Videos für technische Präsentationen erstellt.*
