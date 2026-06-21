# UC22: Transport und Schiene — Inspektionsbildanalyse / Wartungsberichtsverwaltung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Überblick

Ein serverloser Workflow zur Erkennung von Verschlechterungsindikatoren in Eisenbahninfrastruktur-Inspektionsbildern. **Sicherheitskritische Infrastruktur: niedrigere Erkennungsschwelle + obligatorische menschliche Überprüfung.**

## Success Metrics

| Metrik | Zielwert |
|--------|----------|
| Fehlererkennungsrate (Standard) | >= 85% |
| Fehlererkennungsrate (sicherheitskritisch) | >= 95% |
| Genauigkeit Schweregradklassifizierung | >= 80% |
| Falsch-Negativ-Rate (sicherheitskritisch) | < 5% |


## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **zwischen NFS/SMB/S3 AP geteilt**. Die parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinflussen.
- Bei der Verarbeitung großer Dateien prüfen Sie die FSx for ONTAP Throughput Capacity (MBps) und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken (ThroughputUtilization) und erhöhen Sie schrittweise.

## Governance-Hinweis

> AI-Erkennungsergebnisse sind keine endgültigen Urteile — die Bestätigung durch qualifizierte Ingenieure ist obligatorisch.

> **S3 AP NetworkOrigin Hinweis**: Die Discovery Lambda wird innerhalb eines VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Points `Internet` ist, kann über S3 Gateway VPC Endpoint nicht zugegriffen werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen VPC-origin S3 AP oder konfigurieren Sie NAT Gateway-Zugriff. Siehe [S3AP-Kompatibilitätshinweise](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
