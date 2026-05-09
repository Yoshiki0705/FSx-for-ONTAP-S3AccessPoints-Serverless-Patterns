# EDA-Designdatei-Validierung — Demo-Leitfaden

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Dieser Leitfaden definiert eine technische Demonstration für Halbleiter-Designingenieure. Die Demo zeigt einen automatisierten Qualitätsvalidierungs-Workflow für Designdateien (GDS/OASIS) und demonstriert den Wert der Rationalisierung von Design-Reviews vor dem Tapeout.

**Kernbotschaft der Demo**: Automatisierung der IP-Block-übergreifenden Qualitätsprüfungen, die Ingenieure zuvor manuell durchführten, Abschluss innerhalb von Minuten und sofortige Handlungsfähigkeit durch KI-generierte Design-Review-Berichte.

**Geschätzte Dauer**: 3–5 Minuten (kommentiertes Bildschirmaufnahme-Video)

---

## Target Audience & Persona

### Primäre Zielgruppe: EDA-Endbenutzer (Designingenieure)

| Element | Details |
|---------|---------|
| **Position** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tägliche Aufgaben** | Layout-Design, DRC-Ausführung, IP-Block-Integration, Tapeout-Vorbereitung |
| **Herausforderungen** | Zeitaufwändige Gewinnung eines übergreifenden Qualitätsüberblicks über mehrere IP-Blöcke |
| **Tool-Umgebung** | EDA-Tools wie Calibre, Virtuoso, IC Compiler, Innovus |
| **Erwartetes Ergebnis** | Frühzeitige Erkennung von Designqualitätsproblemen zur Einhaltung des Tapeout-Zeitplans |

### Persona: Tanaka-san (Physical Design Lead)

- Verwaltet über 40 IP-Blöcke in einem großen SoC-Projekt
- Muss 2 Wochen vor dem Tapeout Qualitäts-Reviews aller Blöcke durchführen
- Individuelle Überprüfung der GDS/OASIS-Dateien jedes Blocks ist unpraktisch
- „Ich möchte eine Qualitätszusammenfassung aller Blöcke auf einen Blick sehen"

---

## Demo Scenario: Pre-tapeout Quality Review

### Szenarioübersicht

Während der Qualitäts-Review-Phase vor dem Tapeout führt der Design-Lead eine automatisierte Qualitätsvalidierung für mehrere IP-Blöcke (über 40 Dateien) durch und entscheidet über Maßnahmen basierend auf KI-generierten Review-Berichten.

### Gesamter Workflow

```
Designdateien       Automatisierte     Analyse-          KI-Review
(GDS/OASIS)    →   Validierung   →   ergebnisse   →   Berichts-
                    Workflow            Statistische      generierung
                    Auslösung          Aggregation       (Natürliche
                                       (Athena SQL)      Sprache)
```

### Demonstrierter Wert

1. **Zeitersparnis**: Übergreifende Reviews in Minuten statt Tagen abschließen
2. **Vollständigkeit**: Alle IP-Blöcke lückenlos validieren
3. **Quantitative Beurteilung**: Objektive Qualitätsbewertung durch statistische Ausreißererkennung (IQR-Methode)
4. **Handlungsfähig**: KI präsentiert spezifische empfohlene Maßnahmen

---

## Storyboard (5 Abschnitte / 3–5 Minuten)

### Section 1: Problem Statement (0:00–0:45)

**Bildschirm**: Dateiliste des Designprojekts (über 40 GDS/OASIS-Dateien)

**Zusammenfassung der Narration**:
> Zwei Wochen vor dem Tapeout. Wir müssen die Designqualität von über 40 IP-Blöcken überprüfen.
> Jede Datei einzeln in einem EDA-Tool zu öffnen ist nicht realistisch.
> Abnormale Zellanzahlen, Bounding-Box-Ausreißer, Verstöße gegen Namenskonventionen — wir brauchen eine Methode, diese übergreifend zu erkennen.

**Key Visual**:
- Verzeichnisstruktur der Designdateien (.gds, .gds2, .oas, .oasis)
- Texteinblendung: „Manuelle Überprüfung: geschätzt 3–5 Tage"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Bildschirm**: Designingenieur löst den Qualitätsvalidierungs-Workflow aus

**Zusammenfassung der Narration**:
> Nach Erreichen des Design-Meilensteins starten wir den Qualitätsvalidierungs-Workflow.
> Einfach das Zielverzeichnis angeben, und die automatisierte Validierung aller Designdateien beginnt.

**Key Visual**:
- Workflow-Ausführungsbildschirm (Step Functions-Konsole)
- Eingabeparameter: Ziel-Volume-Pfad, Dateifilter (.gds/.oasis)
- Bestätigung des Ausführungsstarts

**Aktion des Ingenieurs**:
```
Ziel: Alle Designdateien unter /vol/eda_designs/
Filter: .gds, .gds2, .oas, .oasis
Aktion: Qualitätsvalidierungs-Workflow starten
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Bildschirm**: Fortschrittsanzeige der Workflow-Ausführung

**Zusammenfassung der Narration**:
> Der Workflow führt automatisch Folgendes aus:
> 1. Erkennung und Auflistung der Designdateien
> 2. Metadaten-Extraktion aus dem Header jeder Datei (library_name, cell_count, bounding_box, units)
> 3. Statistische Analyse der extrahierten Daten (SQL-Abfragen)
> 4. KI-generierter Design-Review-Bericht
>
> Selbst bei großen GDS-Dateien (mehrere GB) ist die Verarbeitung schnell, da nur der Header-Teil (64 KB) gelesen wird.

**Key Visual**:
- Workflow-Schritte werden sequenziell abgeschlossen
- Parallelverarbeitung (Map State) zeigt gleichzeitige Verarbeitung mehrerer Dateien
- Verarbeitungszeit: ca. 2–3 Minuten (bei 40 Dateien)

---

### Section 4: Results Review (2:30–3:45)

**Bildschirm**: Athena SQL-Abfrageergebnisse und statistische Zusammenfassung

**Zusammenfassung der Narration**:
> Analyseergebnisse können frei mit SQL abgefragt werden.
> Zum Beispiel sind Ad-hoc-Analysen wie „Zellen mit abnormal großen Bounding Boxes anzeigen" möglich.

**Key Visual — Athena-Abfragebeispiel**:
```sql
-- Bounding-Box-Ausreißererkennung
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Abfrageergebnisse**:

| file_key | library_name | width | height | Bewertung |
|----------|-------------|-------|--------|-----------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Ausreißer |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Ausreißer |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Ausreißer |

---

### Section 5: Actionable Insights (3:45–5:00)

**Bildschirm**: KI-generierter Design-Review-Bericht

**Zusammenfassung der Narration**:
> Die KI interpretiert die statistischen Analyseergebnisse und generiert automatisch einen Review-Bericht für Designingenieure.
> Er enthält eine Risikobewertung, spezifische empfohlene Maßnahmen und priorisierte Aktionspunkte.
> Basierend auf diesem Bericht können Diskussionen sofort im Pre-Tapeout-Review-Meeting beginnen.

**Key Visual — KI-Review-Bericht (Auszug)**:

```markdown
# Design-Review-Bericht

## Risikobewertung: Medium

## Zusammenfassung der Befunde
- Bounding-Box-Ausreißer: 3 Elemente
- Verstöße gegen Namenskonventionen: 2 Elemente
- Ungültige Dateien: 2 Elemente

## Empfohlene Maßnahmen (nach Priorität)
1. [High] Ursache der 2 ungültigen Dateien untersuchen
2. [Medium] Layout-Optimierung für analog_frontend.oas in Betracht ziehen
3. [Low] Namenskonventionen vereinheitlichen (block-a-io → block_a_io)
```

**Abschluss**:
> Übergreifende Reviews, die manuell Tage dauerten, werden jetzt in Minuten abgeschlossen.
> Designingenieure können sich auf die Überprüfung der Ergebnisse und die Entscheidung über Maßnahmen konzentrieren.

---

## Screen Capture Plan

### Erforderliche Bildschirmaufnahmen

| # | Bildschirm | Abschnitt | Hinweise |
|---|-----------|-----------|----------|
| 1 | Verzeichnisliste der Designdateien | Section 1 | Dateistruktur auf FSx ONTAP |
| 2 | Workflow-Ausführungsstartbildschirm | Section 2 | Step Functions-Konsole |
| 3 | Workflow in Ausführung (Map State Parallelverarbeitung) | Section 3 | Fortschritt sichtbar |
| 4 | Workflow-Abschlussbildschirm | Section 3 | Alle Schritte erfolgreich |
| 5 | Athena-Abfrageeditor + Ergebnisse | Section 4 | Ausreißererkennungsabfrage |
| 6 | Metadaten-JSON-Ausgabebeispiel | Section 4 | Extraktionsergebnis für 1 Datei |
| 7 | KI-Design-Review-Bericht (Volltext) | Section 5 | Markdown-gerenderte Anzeige |
| 8 | SNS-Benachrichtigungs-E-Mail | Section 5 | Berichtsabschluss-Benachrichtigung |

### Aufnahmeverfahren

1. Beispieldaten in der Demo-Umgebung platzieren
2. Workflow manuell ausführen und bei jedem Schritt Bildschirmaufnahmen machen
3. Abfragen in der Athena-Konsole ausführen und Ergebnisse aufnehmen
4. Generierten Bericht von S3 herunterladen und anzeigen

---

## Narration Outline

### Ton und Stil

- **Perspektive**: Erste Person des Designingenieurs (Tanaka-san)
- **Ton**: Praktisch, lösungsorientiert
- **Sprache**: Japanisch (englische Untertitel optional)
- **Geschwindigkeit**: Langsam und deutlich (für eine technische Demo)

### Narrationsstruktur

| Abschnitt | Zeit | Kernbotschaft |
|-----------|------|---------------|
| Problem | 0:00–0:45 | „Qualität von über 40 Blöcken vor dem Tapeout überprüfen. Manuelle Überprüfung reicht zeitlich nicht" |
| Trigger | 0:45–1:30 | „Einfach den Workflow nach dem Design-Meilenstein starten" |
| Analysis | 1:30–2:30 | „Header-Analyse → Metadaten-Extraktion → Statistische Analyse läuft automatisch" |
| Results | 2:30–3:45 | „Frei mit SQL abfragen. Ausreißer sofort identifizieren" |
| Insights | 3:45–5:00 | „KI-Bericht präsentiert priorisierte Maßnahmen. Speist direkt in Review-Meetings ein" |

---

## Sample Data Requirements

### Erforderliche Beispieldaten

| # | Datei | Format | Zweck |
|---|-------|--------|-------|
| 1 | `top_chip_v3.gds` | GDSII | Hauptchip (großmaßstäblich, 1000+ Zellen) |
| 2 | `block_a_io.gds2` | GDSII | I/O-Block (normale Daten) |
| 3 | `memory_ctrl.oasis` | OASIS | Speichercontroller (normale Daten) |
| 4 | `analog_frontend.oas` | OASIS | Analogblock (Ausreißer: große BB) |
| 5 | `test_block_debug.gds` | GDSII | Debug-Block (Ausreißer: abnormale Höhe) |
| 6 | `legacy_io_v1.gds2` | GDSII | Legacy-Block (Ausreißer: Breite & Höhe) |
| 7 | `block-a-io.gds2` | GDSII | Beispiel für Namenskonventionsverletzung |
| 8 | `TOP CHIP (copy).gds` | GDSII | Beispiel für Namenskonventionsverletzung |

### Richtlinie zur Beispieldatengenerierung

- **Minimalkonfiguration**: 8 Dateien (obige Liste) decken alle Demo-Szenarien ab
- **Empfohlene Konfiguration**: Über 40 Dateien (für überzeugendere statistische Analyse)
- **Generierungsmethode**: Python-Skript zur Erzeugung von Testdateien mit gültigen GDSII/OASIS-Headern
- **Größe**: ~100 KB pro Datei ausreichend, da nur Header-Analyse durchgeführt wird

### Checkliste für bestehende Demo-Umgebung

- [ ] Beispieldaten auf FSx ONTAP-Volume platziert
- [ ] S3 Access Point konfiguriert
- [ ] Glue Data Catalog-Tabellendefinition vorhanden
- [ ] Athena-Arbeitsgruppe verfügbar

---

## Timeline

### Innerhalb von 1 Woche erreichbar

| # | Aufgabe | Zeitbedarf | Voraussetzungen |
|---|---------|------------|-----------------|
| 1 | Beispieldatengenerierung (8 Dateien) | 2 Stunden | Python-Umgebung |
| 2 | Workflow-Ausführungsverifizierung in Demo-Umgebung | 2 Stunden | Bereitgestellte Umgebung |
| 3 | Bildschirmaufnahmen (8 Bildschirme) | 3 Stunden | Nach Aufgabe 2 |
| 4 | Finalisierung des Narrationsskripts | 2 Stunden | Nach Aufgabe 3 |
| 5 | Videobearbeitung (Aufnahmen + Narration) | 4 Stunden | Nach Aufgaben 3, 4 |
| 6 | Review & Korrekturen | 2 Stunden | Nach Aufgabe 5 |
| **Gesamt** | | **15 Stunden** | |

### Voraussetzungen (erforderlich für 1-Wochen-Abschluss)

- Step Functions-Workflow bereitgestellt und normal funktionierend
- Lambda-Funktionen (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) verifiziert
- Athena-Tabellen und -Abfragen ausführbar
- Bedrock-Modellzugriff aktiviert

### Future Enhancements (Zukünftige Erweiterungen)

| # | Erweiterung | Übersicht | Priorität |
|---|-------------|-----------|-----------|
| 1 | DRC-Tool-Integration | Direkte Aufnahme von DRC-Ergebnisdateien aus Calibre/Pegasus | High |
| 2 | Interaktives Dashboard | Designqualitäts-Dashboard über QuickSight | Medium |
| 3 | Slack/Teams-Benachrichtigungen | Chat-Benachrichtigung bei Berichtsabschluss | Medium |
| 4 | Differenzielle Überprüfung | Automatische Erkennung und Berichterstattung von Unterschieden zur vorherigen Ausführung | High |
| 5 | Benutzerdefinierte Regeldefinitionen | Projektspezifische Qualitätsregeln ermöglichen | Medium |
| 6 | Mehrsprachige Berichte | Berichtsgenerierung in Englisch/Japanisch/Chinesisch | Low |
| 7 | CI/CD-Integration | Als automatisiertes Qualitätsgate in den Designfluss einbetten | High |
| 8 | Unterstützung großer Datenmengen | Parallelverarbeitungsoptimierung für über 1000 Dateien | Medium |

---

## Technical Notes (Für Demo-Ersteller)

### Verwendete Komponenten (nur bestehende Implementierung)

| Komponente | Rolle |
|------------|-------|
| Step Functions | Gesamte Workflow-Orchestrierung |
| Lambda (Discovery) | Erkennung und Auflistung von Designdateien |
| Lambda (MetadataExtraction) | GDSII/OASIS-Header-Parsing und Metadaten-Extraktion |
| Lambda (DrcAggregation) | Statistische Analyseausführung über Athena SQL |
| Lambda (ReportGeneration) | KI-Review-Berichtsgenerierung über Bedrock |
| Amazon Athena | SQL-Abfragen auf Metadaten |
| Amazon Bedrock | Berichtsgenerierung in natürlicher Sprache (Nova Lite / Claude) |

### Fallback-Lösungen für die Demo-Ausführung

| Szenario | Reaktion |
|----------|----------|
| Workflow-Ausführungsfehler | Vorab aufgezeichnete Ausführungsbildschirme verwenden |
| Bedrock-Antwortverzögerung | Vorab generierten Bericht anzeigen |
| Athena-Abfrage-Timeout | Vorab abgerufene Ergebnis-CSV anzeigen |
| Netzwerkausfall | Alle Bildschirme vorab aufgenommen und zu Video kompiliert |

---

*Dieses Dokument wurde als Produktionsleitfaden für ein technisches Präsentations-Demovideo erstellt.*
