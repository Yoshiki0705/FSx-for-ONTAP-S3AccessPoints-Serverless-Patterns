# Dateiportal — Benutzerhandbuch

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | [한국어](../ko/portal-user-guide.md) | [简体中文](../zh-CN/portal-user-guide.md) | [繁體中文](../zh-TW/portal-user-guide.md) | [Français](../fr/portal-user-guide.md) | **Deutsch** | [Español](../es/portal-user-guide.md)

Anleitung für Endbenutzer, die zu einem bereits bereitgestellten File Portal eingeladen wurden. Dieses Dokument setzt voraus, dass ein Portal-Administrator die Bereitstellung abgeschlossen und Ihr Konto erstellt hat — Sie benötigen keinen AWS CLI-Zugang oder Deployment-Kenntnisse.

**Was dieses Portal bietet**: NAS-Dateien im Browser durchsuchen, AI/ML-Analysen auslösen, Ergebnisse anzeigen und den Datenschutzstatus prüfen — alles ohne VPN oder SMB/NFS-Client-Einrichtung.

---

## Erste Schritte

### 1. Anmelden

1. Öffnen Sie die von Ihrem Administrator bereitgestellte Portal-URL
2. Geben Sie Ihre E-Mail-Adresse und Ihr Passwort ein (bereitgestellt oder selbst registriert, je nach Konfiguration)
3. Falls MFA aktiviert ist, geben Sie den TOTP-Code aus Ihrer Authenticator-App ein
4. Bei der ersten Anmeldung führt Sie das **Welcome Modal** durch 3 Hauptfunktionen:
   - 📂 Datei-Browsing — NAS-Dateien im Browser durchsuchen
   - ⚡ AI-Verarbeitung — Dateien auswählen und Workflows auslösen
   - 🔒 Datenschutz — Snapshots, Sperren und Ransomware-Status

> **Tipp**: Aktivieren Sie „Nicht mehr anzeigen", um das Welcome Modal bei zukünftigen Anmeldungen zu überspringen.

### 2. Portal-Layout

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 DE ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ Seitenleiste  │  Hauptinhalt                            │
│ (Navigation)  │                                         │
│               │                    AI-Assistent-Panel → │
└───────────────┴─────────────────────────────────────────┘
```

- **Linke Seitenleiste**: Navigation gruppiert nach Durchsuchen, AI & Verarbeitung, Datenschutz, Administration
- **Hauptinhalt**: Aktiver Bereich (ändert sich beim Klicken auf Seitenleisten-Einträge)
- **Rechtes Panel**: AI-Assistent (erscheint bei Dateiauswahl in All Files)
- **Obere Leiste**: Sprachauswahl, Benutzer-E-Mail, Abmelden

### 3. Sprache

Klicken Sie auf den 🌐 Sprachselektor in der oberen Leiste, um zwischen 8 Sprachen zu wechseln: 日本語, English, 한국어, 简体中文, 繁體中文, Français, Deutsch, Español. Der Wechsel erfolgt sofort — kein Neuladen der Seite.

---

## Durchsuchen — Arbeiten mit Dateien

### All Files

Ihr Hauptdateibrowser. Zeigt den Inhalt des FSx for ONTAP-Volumes über S3 Access Point an.

| Aktion | Vorgehensweise |
|--------|---------------|
| Ordner durchsuchen | Auf einen Ordnernamen klicken |
| Eine Ebene nach oben | Auf `..` oben in der Dateiliste klicken |
| Bilder vorschauen | Auf das 🖼️-Symbol neben Bilddateien klicken |
| PDF vorschauen | Auf das 📕-Symbol klicken — öffnet im integrierten Browser-Viewer |
| Word-Dokumente vorschauen | Auf das 📝-Symbol klicken — wird im Browser gerendert |
| Datei herunterladen | Auf das 📄-Symbol klicken |
| Freigabe-Link erstellen | 🔗 klicken → TTL wählen (5 Min / 15 Min / 1 Stunde) → URL kopieren |
| AI zu einer Datei befragen | Datei auswählen → Frage im rechten AI-Panel eingeben |
| Objekte in Bildern erkennen | Bild auswählen → "Detect Objects" im AI-Panel klicken |
| Diesen Ordner verarbeiten | ⚡-Button über der Dateiliste klicken |

**PHI-geschützte Ordner**: Wenn Sie in einen Ordner namens `/dicom/`, `/phi/`, `/pii/` oder ähnlich navigieren, zeigt die AI-Verarbeitungsschaltfläche `🚫 PHI — AI Blocked` an. Dies ist eine Sicherheitsleitplanke — Dateien in diesen Ordnern können unabhängig von Ihren Berechtigungen nicht an AI-Dienste gesendet werden.

### Favorites

Häufig verwendete Dateien durch Klicken auf das ⭐-Symbol in der Dateiliste anpinnen. Angepinnte Dateien erscheinen im Favorites-Bereich für schnellen Zugriff.

### Recent

Zeigt Ihre kürzlich angesehenen, heruntergeladenen oder per AI abgefragten Dateien mit relativen Zeitstempeln (vor 3 Min., vor 2 Std.). Nur Ihre eigene Historie ist sichtbar — Aktivitäten anderer Benutzer werden nicht angezeigt.

### Upload

Drag-and-Drop-Dateiupload basierend auf Storage Browser for S3. Unterstützt außerdem:
- Ordnererstellung
- Kopieren und Löschen von Dateien
- Multi-Datei-Upload (bis zu 50 GB pro Datei)

---

## AI & Verarbeitung

### AI Processing

Lösen Sie AI/ML-Workflows für einen Ordner oder eine Dateiauswahl aus.

1. Wählen Sie ein Verarbeitungsmuster aus dem Dropdown (z.B. Legal Compliance, Financial IDP, Semiconductor EDA)
2. Legen Sie das Eingabe-Präfix fest (vorausgefüllt, wenn Sie ⚡ aus All Files geklickt haben)
3. Klicken Sie auf **Start Processing**
4. Sie werden zu Job History weitergeleitet, wo der Status alle 5 Sekunden aktualisiert wird

### Job History

Alle vergangenen Verarbeitungsaufträge mit Status, Zeitstempeln und Ausgabedaten anzeigen.

| Status | Bedeutung |
|--------|-----------|
| 🔵 RUNNING | Verarbeitung läuft |
| 🟢 SUCCEEDED | Abgeschlossen — klicken für Ergebnisse |
| 🔴 FAILED | Fehler aufgetreten — Ausgabe für Details prüfen |
| ⚪ TIMED_OUT | Maximale Ausführungszeit überschritten |

Klicken Sie auf einen Auftrag, um seine Ausgabe aufzuklappen. Falls Ergebnisse auf das Volume zurückgeschrieben wurden, führt ein Navigationslink direkt zum Ausgabeordner in All Files.

### Analytics

SQL-Abfragen auf Ihre Daten mit Amazon Athena ausführen. Dies erfordert vorkonfigurierte Glue Data Catalog-Tabellen (von Ihrem Administrator eingerichtet).

---

## Datenschutz

### Snapshots

Volume-Snapshots anzeigen — zeitpunktbezogene Kopien Ihrer Daten.

- **Liste**: Alle verfügbaren Snapshots mit Erstellungs-Zeitstempeln anzeigen
- **Wiederherstellen**: Auf "Restore" klicken, um einen FlexClone (sofortige, speichereffiziente Kopie) von einem beliebigen Snapshot zu erstellen. Der Klon erhält seinen eigenen S3 Access Point und ist innerhalb von Sekunden verfügbar.

### Lock (WORM)

Den Unveränderlichkeitsstatus Ihrer Daten über drei Mechanismen anzeigen:

| Tab | Was angezeigt wird |
|-----|-------------------|
| ONTAP SnapLock | Ob das Volume den Compliance- oder Enterprise-Modus verwendet, Aufbewahrungsfristen |
| S3 Object Lock | Ob AI-Ausgabe-Buckets WORM auf Objektebene aktiviert haben |
| Tamperproof Snapshot | Welche Snapshots gesperrt sind und wann sie ablaufen |

> **Hinweis**: Die Konfiguration von Sperreinstellungen erfordert die Rolle `storage-admin`. Reguläre Benutzer haben nur Lesezugriff auf diesen Bereich.

### ARP/AI (Ransomware-Schutz)

Den autonomen Ransomware-Schutzstatus für Ihre Volumes anzeigen.

| Was Sie sehen | Bedeutung |
|---------------|-----------|
| 🟢 No threats | Alle Volumes gesund |
| 🔴 Threat detected | ARP/AI hat verdächtige Aktivität markiert |
| Incident badge | Zeigt die aktuelle Reaktionsphase (Detected → Contained → Investigating → Resolved) |

Wenn eine Bedrohung erkannt wird und Sie in der Gruppe `storage-admin` sind, können Sie Eindämmungsmaßnahmen direkt aus diesem Panel ausführen.

---

## Administration (Erfordert `storage-admin`-Gruppe)

Diese Bereiche sind nur sichtbar/bedienbar, wenn Ihr Konto in der Cognito-Gruppe `storage-admin` ist.

### Storage Dashboard

Die Administrator-Startseite. Vier Karten zeigen:
- 💾 Anzahl der Volumes + durchschnittliche Kapazitätsauslastung
- 🛡️ ARP-geschützte Volumes + aktive Bedrohungen
- 🔐 Gesperrte (manipulationssichere) Snapshots
- 📊 Speichereffizienz-Verhältnis

Klicken Sie auf eine Karte, um in das Detailpanel einzutauchen.

### Resources

Karten-Raster-Administrationspanel mit 10 Verwaltungsbereichen nach Kategorie geordnet:

| Kategorie | Panels |
|-----------|--------|
| Speicher | Volumes, Qtrees, Quotas, Efficiency |
| Zugriffskontrolle | Export Policies, CIFS Shares, QoS |
| Schutz | ARP Admin, Snapshot Admin, SnapLock |

### Version Diff

Dateiinhalte zwischen zwei Snapshots nebeneinander vergleichen.

### Audit Trail

CloudTrail S3-Datenereignisse abfragen, um zu beantworten: „Wer hat auf was zugegriffen, und wann?"

---

### 4. Nutzung auf dem Smartphone

Es gibt keine eigene App. Öffnen Sie **dieselbe URL wie am Desktop** im Browser des
Smartphones (geprüft mit Safari unter iOS und Chrome unter Android).

<img src="../../solutions/amplify-portal/docs/screenshots/portal-files-mobile-dark.png" alt="Die Dateiliste auf dem Smartphone, dunkles Thema" width="300">

**Vorgehen**

1. Öffnen Sie die URL, die Sie von der Administration erhalten haben
2. Melden Sie sich mit E-Mail und Kennwort an, bei aktivierter MFA zusätzlich mit einem
   TOTP-Code. Das automatische Ausfüllen Ihres Kennwortmanagers funktioniert wie gewohnt
3. Am oberen Rand liegen **☰**, die Themenauswahl, die Sprachauswahl und die Abmeldung
   (⏻). Die Seitenleiste ist zunächst verborgen
4. **☰** öffnet die Navigation über dem Inhalt. Die Wahl eines Bereichs schließt sie
   wieder; zum Schließen ohne Auswahl tippen Sie auf die abgedunkelte Fläche
5. Zum Öffnen einer Datei tippen Sie auf das Symbol in ihrer Zeile (📄 / 🖼️ / 📕 / 📝).
   Die Vorschau erscheint als Blatt vom unteren Rand und wird mit **✕** geschlossen
6. Für mehrere Dateien tippen Sie auf das Kontrollfeld links in jeder Zeile. Anzahl und
   verfügbare Aktionen erscheinen über der Liste

**Unterschiede zum Desktop**

| Element | Auf dem Smartphone |
|---------|-------------------|
| Seitenleiste | eine Schublade über dem Inhalt, mit **☰** geöffnet und geschlossen |
| Spalten Größe und Geändert | entfallen aus Platzmangel; nach Name lässt sich weiter sortieren |
| E-Mail-Adresse | ausgeblendet (die Abmeldung ist nur noch ein Symbol) |
| Dateivorschau | ein Blatt vom unteren Rand, bis zu 70 % des Bildschirms. Ein PDF liest sich im Querformat besser |
| KI-Assistenzbereich | öffnet als Schublade von rechts |

> **Zum 🖥️ in der Themenauswahl**: Es ist keine Schaltfläche „zur Desktop-Ansicht
> wechseln". Die drei Möglichkeiten sind ☀️ hell, 🌙 dunkel und 🖥️ **dem Gerät folgen**;
> letzteres folgt der Darstellungseinstellung von iOS oder Android, einschließlich des
> automatischen Wechsels am Abend.

> **Datenverbrauch**: Der ZIP-Download eines Ordners überträgt dessen gesamten Inhalt.
> Prüfen Sie im Mobilfunknetz zuerst Anzahl und Größe der Dateien.

---

## Tipps & FAQ

**F: Ich sehe „ONTAP Connection Required" in einigen Panels.**
A: Das Portal ist im DemoMode oder der Administrator hat die VPC-Verbindung noch nicht konfiguriert. Datei-Browsing und AI-Funktionen funktionieren weiterhin — nur ONTAP-spezifische Panels (Snapshots, ARP, Lock) benötigen die Verbindung.

**F: Meine AI-Verarbeitungsschaltfläche zeigt „PHI — AI Blocked".**
A: Sie befinden sich in einem geschützten Ordner (`/dicom/`, `/phi/`, `/pii/` usw.). Dies ist beabsichtigt — Dateien in diesen Pfaden können nicht an AI-Dienste gesendet werden. Navigieren Sie zu einem ungeschützten Ordner, um AI-Funktionen zu nutzen.

**F: Freigabe-Links laufen schnell ab.**
A: Freigabe-Links verwenden Presigned URLs mit einer von Ihnen gewählten Gültigkeitsdauer (5 Min, 15 Min oder 1 Stunde). Für langfristiges Teilen fragen Sie Ihren Administrator nach der Nextcloud-Integration oder passen Sie die TTL-Optionen an.

**F: Dateien, die ich über NFS/SMB hochgeladen habe, werden nicht angezeigt.**
A: Sie sollten sofort erscheinen (ONTAP garantiert protokollübergreifende starke Konsistenz). Versuchen Sie, die Dateiliste zu aktualisieren. Falls sie immer noch fehlen, befindet sich die Datei möglicherweise in einem Unterordner — prüfen Sie den Pfad.

**F: Kann ich das Portal auf dem Handy nutzen?**
A: Ja. Das Vorgehen steht unter „4. Nutzung auf dem Smartphone“ im Einstieg.

**F: Wie ändere ich mein Passwort?**
A: Verwenden Sie die Cognito Hosted UI oder bitten Sie Ihren Administrator um eine Zurücksetzung.

---

## Verwandte Dokumente

| Dokument | Zielgruppe | Zweck |
|----------|-----------|-------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | Administratoren | Portal von Grund auf bereitstellen |
| [Admin Demo Guide](admin-resource-management-demo.md) | Speicheradministratoren | E2E-Demo der Verwaltungsoperationen |
| [AI Features Quick Start](ai-features-quick-start.md) | Alle Benutzer | Bedrock, Rekognition, Athena ausprobieren |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | Entwickler | Architektur und Anpassung |
| [Authorization Model](portal-authorization-model.md) | Sicherheitsteams | Cognito-Gruppen, IAM, Zugriff auf Dateiebene |
| [Compliance Guide](portal-compliance-guide.md) | Sicherheit/Compliance | Regulatorische Kontrollen verifizieren |
| [Quick Reference](portal-quick-reference.md) | Alle Rollen | 1-Seiten-Kurzreferenz |
