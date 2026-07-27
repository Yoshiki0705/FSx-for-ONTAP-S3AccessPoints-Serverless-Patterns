# Dateiportal — Kurzreferenz

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | **Deutsch** | [Español](../es/portal-quick-reference.md)

Einseiter für die tägliche Portal-Nutzung. Drucken Sie diese Seite aus oder setzen Sie ein Lesezeichen.

---

## Navigation

| Seitenleisten-Bereich | Funktion |
|:---:|------|
| 📂 All Files | Durchsuchen, Vorschau, Download, Teilen, AI-Q&A |
| ⭐ Favorites | Angeheftete Dateien |
| 🕐 Recent | Ihr Zugriffsverlauf |
| 📤 Upload | Drag-and-Drop-Upload (max. 5 GB/Datei) |
| ⚡ AI Processing | AI/ML-Workflows auf Ordner anwenden |
| 📋 Job History | Vergangene Job-Ergebnisse + Status |
| 📊 Analytics | Athena-SQL-Abfragen |
| 📸 Snapshots | Point-in-Time-Kopien + FlexClone-Wiederherstellung |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | Ransomware-Schutzstatus |
| 🔧 Resources | Speicherverwaltung (nur Admin) |
| 🔄 Version Diff | Dateien über Snapshots hinweg vergleichen |
| 🔍 Audit Trail | Wer hat wann auf was zugegriffen |

---

## Häufige Aufgaben (alle Benutzer)

| Ich möchte... | So geht's |
|--------------|-----------|
| Dateien durchsuchen | Seitenleiste → 📂 All Files → Ordner anklicken |
| PDF-Vorschau anzeigen | 📕 neben der Datei anklicken |
| Word-Dokument-Vorschau | 📝 neben der Datei anklicken |
| Datei herunterladen | 📄 neben der Datei anklicken |
| Dateilink teilen | 🔗 anklicken → TTL wählen → URL kopieren |
| AI zu einer Datei befragen | Datei auswählen → Frage im rechten Panel eingeben |
| Objekte in Bild erkennen | Bild auswählen → "Detect Objects" im rechten Panel |
| Dateien hochladen | Seitenleiste → 📤 Upload → Drag & Drop |
| AI auf Ordner anwenden | In All Files ⚡ über der Dateiliste anklicken |
| Job-Ergebnisse prüfen | Seitenleiste → 📋 Job History → Job anklicken |
| Aus Snapshot wiederherstellen | Seitenleiste → 📸 Snapshots → "Restore"-Button |
| Sprache wechseln | 🌐 in der oberen Leiste anklicken |

---

## Häufige Aufgaben (Compliance / Sicherheit)

| Ich möchte... | So geht's |
|--------------|-----------|
| Ransomware-Status prüfen | Seitenleiste → 🛡️ ARP/AI |
| WORM-Sperren überprüfen | Seitenleiste → 🔒 Lock → Registerkarte SnapLock |
| Ausgabe-Bucket-Sperre prüfen | Seitenleiste → 🔒 Lock → Registerkarte S3 Object Lock |
| Gesperrte Snapshots anzeigen | Seitenleiste → 🔒 Lock → Registerkarte Tamperproof |
| Zugriffsaudit prüfen | Seitenleiste → 🔍 Audit Trail |
| PHI-Schutzregel überprüfen | All Files → zu `/dicom/` navigieren → Button zeigt 🚫 |

---

## Häufige Aufgaben (Speicheradministrator)

| Ich möchte... | So geht's |
|--------------|-----------|
| Health-Dashboard anzeigen | Seitenleiste → 🔧 Resources (Dashboard erscheint zuerst) |
| Volumes verwalten | Resources → Storage → Volumes |
| Export-Richtlinien konfigurieren | Resources → Access Control → Export Policies |
| ARP auf Volumes aktivieren | Resources → Protection → ARP Admin |
| Snapshot sperren | Resources → Protection → Snapshot Admin → Lock-Formular |
| Kompromittierten Benutzer sperren | Seitenleiste → 🛡️ ARP/AI → Registerkarte Contain → Block SMB User |
| Nach Lösung entsperren | Seitenleiste → 🛡️ ARP/AI → Registerkarte Unblock |
| EMS-Alarme prüfen | Resources → (EMS-Ereignisse in der Überwachung) |

---

## Tastenkürzel

| Taste | Aktion |
|-------|--------|
| `Tab` | Zwischen interaktiven Elementen wechseln |
| `Enter` | Button aktivieren / Ordner öffnen |
| `Escape` | Modal schließen / Panel verbergen |

---

## Status-Indikatoren

| Symbol | Bedeutung |
|:---:|---------|
| 🟢 | Gesund / Keine Bedrohungen / Gelöst |
| 🔴 | Bedrohung erkannt / Fehler |
| 🟠 | Eingedämmt (Vorfall aktiv) |
| 🟡 | In Untersuchung |
| 🚫 | PHI — AI blockiert (Schutzregel aktiv) |
| ⚠️ | Warnung (Kapazität > 85 % usw.) |

---

## Zugriffsebenen

| Gruppe | Kann | Kann nicht |
|--------|------|------------|
| `authenticated` | Durchsuchen, Download, Upload, AI, Schutzstatus anzeigen | Speicherkonfiguration ändern |
| `storage-admin` | Alles oben + Volumes erstellen/löschen, Snapshots sperren, Benutzer sperren, Richtlinien verwalten | — |

---

## Schnelle Fehlerbehebung

| Symptom | Lösung |
|---------|--------|
| "ONTAP Connection Required" | Normal im DemoMode. Bitten Sie den Admin, VPC zu konfigurieren. |
| AI-Button zeigt 🚫 | Sie befinden sich in einem PHI-geschützten Ordner. Navigieren Sie woanders hin. |
| Geteilter Link abgelaufen | Generieren Sie einen neuen (🔗). Max. TTL = 1 Stunde. |
| Datei nach NFS-Schreibvorgang nicht sichtbar | Aktualisieren Sie die Dateiliste. Sollte sofort erscheinen. |
| Endloses Laden | Internetverbindung prüfen. Abmelden → erneut anmelden. |

---

## Dokumentationsübersicht

| Ihre Rolle | Starten Sie hier |
|-----------|-----------------|
| Endbenutzer (tägliche Aufgaben) | [Benutzerhandbuch](portal-user-guide.md) |
| Sicherheit / Compliance | [Compliance-Leitfaden](portal-compliance-guide.md) |
| Speicheradministrator | [Admin-Demo-Leitfaden](admin-resource-management-demo.md) |
| IT-Administrator (Bereitstellung) | [Erste-Schritte-Anleitung](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| Entwickler (Anpassung) | [Implementierungsleitfaden](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
