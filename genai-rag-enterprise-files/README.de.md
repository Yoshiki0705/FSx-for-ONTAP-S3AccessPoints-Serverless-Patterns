# GenAI RAG — Unternehmensdateien

🌐 **Language / Sprache**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Ein Pattern, das vertrauliche Dokumente auf Unternehmens-Dateiservern (FSx for ONTAP) sicher über S3 Access Points an Amazon Bedrock / RAG-Pipelines bereitstellt — **ohne Kopie nach S3**. Realisiert Permission-aware RAG unter Beibehaltung der Dateiberechtigungen (ACL/NTFS).

## Gelöste Probleme

| Problem | Lösung |
|---------|--------|
| Datenausbreitung durch Kopieren sensibler Dateien nach S3 | Direktes Lesen über S3 AP, keine Kopie nötig |
| Verlust von Dateiberechtigungen | ACL-Abruf über ONTAP REST API, Filterung bei RAG-Antwort |
| Probleme mit Datenaktualität | FlexCache + S3 AP liefert aktuelle Daten |
| Vollvolumen-Verarbeitung großer Dateiserver | EventBridge Scheduler + Delta-Erkennung für Effizienz |
| Distanz zwischen KI-Verarbeitung und Daten | FlexCache platziert Daten nahe am KI-Verarbeitungs-VPC |

## Permission-aware RAG Konzept

1. **Bei der Indexierung**: ACL/Berechtigungsinformationen für jedes Dokument über ONTAP REST API abrufen und als Metadaten im Vektorspeicher speichern
2. **Bei der Abfrage**: Suchbereich auf nur für den Benutzer zugängliche Dokumente basierend auf AD SID / Gruppenmitgliedschaft filtern
3. **Bei der Antwort**: Nur gefilterte Dokumente an Bedrock zur Antwortgenerierung übergeben

## Erfolgskennzahlen

| Kennzahl | Ziel |
|----------|------|
| Verarbeitete Dateien pro Ausführung | > 200 Dateien |
| ACL-Extraktionserfolgsrate | > 95% |
| Embedding-Generierungszeit | < 5 Min. / 100 Dateien |
| Permission-aware Filtergenauigkeit | > 99% |
| Human Review Rate | < 10% (Chunks mit niedriger Konfidenz) |

---

## Governance-Hinweis

> Dieses Pattern bietet technische Architekturberatung. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Organisationen sollten qualifizierte Fachleute konsultieren.
