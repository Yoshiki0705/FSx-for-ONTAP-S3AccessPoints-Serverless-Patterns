# Dateiportal — Leitfaden für Sicherheit und Compliance

> 🌐 Language: [English](../en/portal-compliance-guide.md) | [日本語](../ja/portal-compliance-guide.md) | [한국어](../ko/portal-compliance-guide.md) | [简体中文](../zh-CN/portal-compliance-guide.md) | [繁體中文](../zh-TW/portal-compliance-guide.md) | [Français](../fr/portal-compliance-guide.md) | **Deutsch** | [Español](../es/portal-compliance-guide.md)

Ein Leitfaden für Sicherheitsbeauftragte, Compliance-Analysten und Datenschutzverantwortliche, die regulatorische Kontrollen über das Portal **überprüfen** müssen, ohne Speicherverwaltung durchzuführen. Sie benötigen keine `storage-admin`-Berechtigungen — alle nachfolgenden Aufgaben nutzen ausschließlich Lesezugriff.

---

## Ihre Rolle im Portal

| Was Sie tun können | Wo im Portal |
|-------------------|--------------|
| Ransomware-Schutzstatus überprüfen | Seitenleiste → 🛡️ ARP/AI |
| Snapshot-Sperre und Aufbewahrungsfristen bestätigen | Seitenleiste → 🔒 Lock |
| Audit-Trail prüfen (wer hat auf was zugegriffen) | Seitenleiste → 🔍 Audit Trail |
| PHI-Schutzregel überprüfen | Seitenleiste → 📂 All Files (navigieren Sie zu `/dicom/` oder `/phi/`) |
| S3 Object Lock auf Ausgabe-Buckets überprüfen | Seitenleiste → 🔒 Lock → Registerkarte S3 Object Lock |
| EMS-Alarme anzeigen (ONTAP-Systemereignisse) | Admin → Resources (nur Lesezugriff ohne `storage-admin`) |

> **Hinweis**: Sie können keine Konfigurationen ändern (Sperreinstellungen, ARP-Status, Export-Richtlinien). Wenden Sie sich bei Änderungsbedarf an einen `storage-admin`-Benutzer.

---

## Aufgabe 1: Ransomware-Schutz überprüfen (ARP/AI)

**Regulatorischer Kontext**: FISC, NIST CSF DE.CM-4, ISO 27001 A.12.2

1. Klicken Sie auf **🛡️ ARP/AI** in der Seitenleiste
2. Bestätigen Sie, dass jedes überwachte Volume einen grünen Status zeigt (🟢 Keine Bedrohungen)
3. Falls ein Bedrohungsbadge erscheint (🔴), notieren Sie den Volume-Namen und den Erkennungszeitstempel
4. Prüfen Sie das **Incident-Lifecycle-Badge** für die aktuelle Reaktionsphase:
   - 🔴 Erkannt — Bedrohung identifiziert, Eindämmung ausstehend
   - 🟠 Eingedämmt — Angreifer-Zugriff gesperrt, Snapshot gesichert
   - 🟡 In Untersuchung — Forensische Analyse läuft
   - 🟢 Gelöst — Vorfall abgeschlossen

**Nachweis für Auditoren**: Screenshot des ARP-Panels mit dem Schutzstatus aller Volumes + aktiven Incident-Badges mit Zeitstempeln.

---

## Aufgabe 2: Snapshot-Unveränderlichkeit bestätigen (WORM)

**Regulatorischer Kontext**: SEC 17a-4, FISC 7 Jahre Aufbewahrung, HIPAA 6 Jahre, SOX 5 Jahre, NARA

1. Klicken Sie auf **🔒 Lock** in der Seitenleiste
2. Prüfen Sie drei Registerkarten:

### Registerkarte A: ONTAP SnapLock
- Überprüfen Sie den Volume-Typ: **Compliance** (niemand kann löschen, auch nicht root) oder **Enterprise** (Admin kann freigeben)
- Prüfen Sie, ob Aufbewahrungsfristen Ihrer Richtlinie entsprechen:
  - Mindestfrist ≥ regulatorische Anforderung
  - Compliance Clock ist initialisiert und läuft

### Registerkarte B: S3 Object Lock
- Überprüfen Sie, ob Object Lock auf dem Ausgabe-Bucket aktiviert ist
- Bestätigen Sie den Modus: **Compliance** für regulatorische Archive, **Governance** für AI-Ausgaben
- Prüfen Sie, ob die Standard-Aufbewahrungstage Ihrer Anforderung entsprechen

### Registerkarte C: Tamperproof Snapshots
- Prüfen Sie die Tabelle gesperrter Snapshots: Name, Erstellungszeit, Ablaufzeit
- Überprüfen Sie, ob Ablaufdaten den regulatorischen Aufbewahrungsanforderungen entsprechen:

| Regulierung | Erforderliche Aufbewahrung | Erwarteter Ablauf |
|------------|---------------------------|-------------------|
| FISC | 7 Jahre (2.557 Tage) | Erstellung + 7 Jahre |
| HIPAA | 6 Jahre (2.192 Tage) | Erstellung + 6 Jahre |
| SOX/J-SOX | 5 Jahre (1.825 Tage) | Erstellung + 5 Jahre |
| NARA | 3-75 Jahre (variabel) | Gemäß Aufbewahrungsplan |

**Nachweis für Auditoren**: Screenshot jeder Registerkarte mit Sperrstatus + Aufbewahrungsfristen.

---

## Aufgabe 3: Audit-Trail prüfen

**Regulatorischer Kontext**: FISC, SOX Section 302/404, HIPAA §164.312(b), PCI DSS 10.x

1. Klicken Sie auf **🔍 Audit Trail** in der Seitenleiste
2. Das Panel zeigt CloudTrail-S3-Datenereignisse für den S3 Access Point
3. Wichtige Felder zur Überprüfung:
   - **Wer**: IAM-Prinzipal (Cognito-Benutzeridentität)
   - **Wann**: Ereignis-Zeitstempel (UTC)
   - **Was**: API-Aktion (`GetObject`, `PutObject`, `ListObjectsV2`)
   - **Welche Datei**: S3-Schlüssel (Dateipfad)
4. Filtern Sie nach Zeitraum oder Benutzer bei der Untersuchung eines bestimmten Vorfalls

**Nachweis für Auditoren**: Exportieren oder erfassen Sie den Audit-Trail gefiltert auf den Prüfungszeitraum.

---

## Aufgabe 4: PHI-Schutzregel überprüfen

**Regulatorischer Kontext**: HIPAA §164.502 (Minimum-Necessary-Prinzip), 45 CFR 164.514

1. Klicken Sie auf **📂 All Files** in der Seitenleiste
2. Navigieren Sie zu einem Ordner namens `/dicom/`, `/phi/`, `/pii/` oder `/hipaa/`
3. Beobachten Sie, dass die AI-Verarbeitungsschaltfläche anzeigt: **🚫 PHI — AI Blocked**
4. Überprüfen Sie, dass die Schaltfläche deaktiviert ist (unabhängig von der Benutzerrolle nicht anklickbar)

**Bedeutung**: Dateien in diesen geschützten Pfaden werden strukturell daran gehindert, an externe AI-Dienste (Bedrock, Rekognition, Textract, Comprehend) gesendet zu werden. Dies wird auf UI-Ebene durch Pfad-Musterabgleich durchgesetzt und kann von keinem Benutzer überschrieben werden.

**Einschränkung**: Diese Schutzregel hängt von Ordner-Namenskonventionen ab. Dateien mit PHI-Inhalten in nicht geschützten Pfaden werden nicht blockiert. Stellen Sie sicher, dass die Ordnerstruktur-Richtlinien der Organisation vorgelagert durchgesetzt werden.

**Nachweis für Auditoren**: Screenshot der deaktivierten AI-Schaltfläche in einem `/dicom/`-Ordner.

---

## Aufgabe 5: S3 Object Lock auf AI-Ausgaben überprüfen

**Regulatorischer Kontext**: SEC 17a-4(f), CFTC 1.31, FINRA 4511

1. Klicken Sie auf **🔒 Lock** → Registerkarte **S3 Object Lock**
2. Überprüfen Sie:
   - Object Lock ist auf dem Ausgabe-Bucket **aktiviert**
   - Modus ist angemessen: **Compliance** (unveränderlich) für regulatorische Archive oder **Governance** (mit Berechtigung überschreibbar) für AI-Ausgaben
   - Standard-Aufbewahrungsfrist entspricht Ihrem Aufbewahrungsplan
3. Falls Object Lock nicht konfiguriert ist, eskalieren Sie an einen `storage-admin`-Benutzer

**Warum das wichtig ist**: In S3 gespeicherte AI-Verarbeitungsergebnisse (Klassifizierungslabels, extrahierter Text, Compliance-Berichte) können selbst regulatorische Aufzeichnungen sein. Object Lock stellt sicher, dass diese Ausgaben während der Aufbewahrungsfrist nicht geändert oder gelöscht werden können.

---

## Aufgabe 6: Incident-Response-Überprüfung

Wenn ein Ransomware-Vorfall erkannt wird:

1. Gehen Sie zu **🛡️ ARP/AI** → prüfen Sie den Incident-Badge-Status
2. Überprüfen Sie, dass die Eindämmung durchgeführt wurde:
   - Snapshot erstellt (Beweis gesichert)
   - Verdächtiger Benutzer/IP gesperrt
3. Gehen Sie zu **🔍 Audit Trail** → filtern Sie Ereignisse um den Erkennungszeitstempel
4. Dokumentieren Sie den Zeitablauf: Erkennung → Eindämmung → Untersuchungsbeginn
5. Nach Lösung überprüfen Sie, dass das Incident-Badge 🟢 Gelöst anzeigt

**Incident-Timeline-SLA-Referenz**:

| Phase | Typische Dauer | Ihr SLA |
|-------|:---:|:---:|
| Erkennung → Eindämmung | < 5 Minuten (automatisiert) | _____ |
| Eindämmung → Untersuchungsbeginn | < 1 Stunde | _____ |
| Untersuchung → Lösung | Fallabhängig | _____ |

---

## Regulatorische Zuordnung

| Portal-Funktion | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|----------------|:---:|:---:|:---:|:---:|:---:|
| ARP/AI Ransomware-Erkennung | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (Compliance-Modus) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| PHI-Schutzregel | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| Incident-Lifecycle-Verfolgung | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## Was Sie nicht tun können (und wer es kann)

| Aktion | Erforderliche Gruppe | Ansprechpartner |
|--------|:---:|---------|
| ARP/AI-Status ändern | `storage-admin` | Speicheradministrator |
| Snapshots sperren/entsperren | `storage-admin` | Speicheradministrator |
| S3 Object Lock konfigurieren | `storage-admin` | Speicheradministrator |
| Benutzer sperren/entsperren (Eindämmung) | `storage-admin` | Security Operations + Speicheradministrator |
| Volumes erstellen/löschen | `storage-admin` | Speicheradministrator |
| Export-Richtlinien ändern | `storage-admin` | Speicheradministrator |

---

## Verwandte Dokumente

| Dokument | Zweck |
|----------|-------|
| [Benutzerhandbuch](portal-user-guide.md) | Tägliche Benutzeroperationen |
| [Autorisierungsmodell](portal-authorization-model.md) | Vollständige Berechtigungsmatrix |
| [Admin-Demo-Leitfaden](admin-resource-management-demo.md) | Speicherverwaltungsoperationen |
| [Incident-Response-Playbook](../../docs/incident-response-playbook.md) | Vollständige Incident-Response-Verfahren |
| [Kurzreferenz](portal-quick-reference.md) | 1-Seiten-Zusammenfassung |
