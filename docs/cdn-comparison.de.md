# CDN-/Edge-Auslieferungsintegration im Vergleich — Auslieferung aus FSx for ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. Geltungsbereich

Eine Referenz zur technischen Machbarkeit der Auslieferung von Daten auf FSx for ONTAP
S3 Access Points (S3 AP) über ein CDN/Edge-Netzwerk. Dieses Dokument **bewertet keine** Anbieter, vergleicht
weder Preis noch Leistung und macht keine Marketingaussagen. Es behandelt ausschließlich, **was technisch
machbar ist, was nicht und was verifiziert werden muss** angesichts der Einschränkungen des FSx for ONTAP S3 AP.
Die Anbieterauswahl hängt von Faktoren außerhalb dieses Dokuments ab (Verträge, SLAs, Betrieb, regionale
Anforderungen) und liegt beim Kunden.

## 1. S3-AP-Einschränkungen, die das Auslieferungsdesign bestimmen

| Einschränkung | Detail | Auswirkung auf die Auslieferung |
|---------------|--------|---------------------------------|
| Block Public Access erzwungen (nicht deaktivierbar) | Standardmäßig an, unveränderlich | Kein unauthentifizierter öffentlicher Origin; Origin-Auth erforderlich |
| Origin-Auth ist SigV4 (IAM) | Anfragen durch IAM / AP-Policy bewertet | CDN muss Origin-Anfragen mit AWS SigV4 signieren |
| Zweistufige Autorisierung (AWS + ONTAP) | IAM, dann ONTAP-Dateiidentität (UNIX UID / Windows AD) | Auslieferung auf das beschränkt, was die ONTAP-Identität lesen kann |
| Presigned URLs nicht unterstützt | Offiziell nicht unterstützt | Zuschauer-Token-Auth kann keine S3-Presigned-URLs nutzen; CDN-native Tokens verwenden |
| NetworkOrigin (Internet/VPC, unveränderlich) | CDN greift aus managed/externem Netzwerk zu | CDN-Integration benötigt **Internet-Origin** |
| PutObject max. 5 GB | Limit eines einzelnen PUT | Große Rückschreibvorgänge benötigen Multipart |

## 2. Integrationsmechanismen (anbieterneutral)

- **M1 — Natives SigV4-Origin-Pull**: Das CDN ruft das S3 AP direkt ab und signiert Origin-Anfragen mit
  SigV4. Machbar, wenn das CDN SigV4-Origin-Signierung mitbringt. **Zu verifizieren**: Der
  `accesspoint alias`-Host des S3 AP unterscheidet sich von einem Standard-Bucket; das SigV4-Verhalten muss
  auf Hardware validiert werden.
- **M2 — SigV4-Signierung per Edge-Compute**: SigV4 in der Edge-Laufzeit des CDN
  (Workers/Compute/EdgeWorkers) selbst implementieren. Machbar, wenn keine native Origin-Signierung
  vorhanden ist; Signierung/Schlüsselverwaltung in Eigenregie.
- **M3 — Push in einen CDN-nativen S3-kompatiblen Speicher**: FSx als Master behalten, nur freigegebene
  Renditions in den Objektspeicher des CDN replizieren. Umgeht die Origin-Auth-Frage; anbieterneutral;
  risikoärmster erster Schritt.
- **M4 — Selbstverwalteter SigV4-Signierungsproxy**: Einen Signierungs-Zwischendienst (Lambda Function URL /
  ALB) als Origin platzieren. Funktioniert mit fast jedem CDN; der Proxy wird zum Verfügbarkeits-/Skalierungspunkt.

> Universelle Einschränkung: Zuschauer-Token-Auth kann keine S3-Presigned-URLs nutzen — CDN-native Tokens
> verwenden. Öffentliche Auslieferung umgeht NFS/SMB-ACLs, daher nur freigegebene Renditions ausliefern
> (siehe Abschnitt 4).

## 3. Mechanismus-Unterstützung je Auslieferungsnetzwerk (faktenbasiert)

○ = dokumentierte native Funktion / △ = bedingt oder selbst implementiert / − = keine solche Funktion / TBV = S3-AP-spezifische Verifizierung erforderlich.

| Netzwerk | M1 natives SigV4-Pull | M2 Edge-Signierung | M3 eigener S3-kompatibler Speicher | Zuschauer-Token | S3-AP-spezifisches TBV |
|----------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | (zu Standard-S3) | CloudFront signierte URL/Cookie | **Erprobt** (offizielles AWS-Tutorial zeigt S3 AP + OAC) |
| Akamai | ○ Cloud Access Manager (AWS-Signierung) | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | Signierung auf AP-alias-Host TBV |
| Fastly | ○ SigV4 zu S3-kompatiblem privaten Origin | △ Compute | ○ Fastly Object Storage | Fastly signierte URL | SigV4 auf AP alias TBV |
| Cloudflare | − (kein natives SigV4 am Proxy) | ○ SigV4-Signierung via Workers | ○ R2 (S3-kompatibel) | Cloudflare signierte URL | Workers-Signierung + AP alias TBV |
| Bunny.net | △ S3-Origin-Pull (AWS-S3-Origin-Typ) | − | ○ Bunny Storage (S3-kompatible API, beta) | Pull-Zone-Token-Auth | Signierung auf AP alias TBV |
| Google Cloud CDN / Media CDN | ○ SigV4-Auth für privaten S3-kompatiblen Origin | △ Media-CDN-Routing | (GCS / beliebig S3-kompatibel) | Media CDN signierte URL/Cookie | Cross-Cloud-Egress + AP alias TBV |

### Erwähnt, aber nicht in der Tabelle eingestuft
- **Azure Front Door / Azure CDN**: derselbe Mechanismus (M1/M4) kann zutreffen; außerhalb des
  Hauptbereichs; TBV.
- **Gcore**: S3-kompatibler Objektspeicher + Speicher-als-Origin (M3); außerhalb des Hauptbereichs.
- **Edgio (ehemals Limelight / Edgecast)**: **CDN-Dienst zum 2025-01-15 eingestellt**; die meisten Assets von
  Akamai übernommen. **Keine aktive Option** — ausgeschlossen.

> Quellen sind öffentliche Anbieterdokumente (CloudFront OAC, Akamai Cloud Access Manager, Fastly
> S3-kompatible private Origins, Cloudflare Workers/R2, Bunny Storage, Google Media CDN). Alle beschreiben
> **Standard-S3-kompatible Buckets**; das Verhalten am accesspoint alias des FSx for ONTAP S3 AP ist TBV.

## 4. Feste Sicherheitsanforderungen (mechanismusunabhängig)

1. Öffentliche Auslieferung umgeht NFS/SMB-ACLs — **nur freigegebene Renditions** ausliefern;
   ACL-kontrollierte Masterdaten niemals direkt in die Auslieferungsschicht leiten.
2. Master (ACL-kontrolliert, sensibel) von Auslieferungsartefakten (öffentlich/halböffentlich) trennen.
   M3 macht diese Trennung natürlich.
3. Zuschauer-Auth über CDN-native Token-Mechanismen (keine S3-Presigned-URLs).
4. Origin-Anmeldedaten mit minimalen Rechten; keine Langzeitschlüssel an der Edge; kurzlebige Anmeldedaten bevorzugen.
5. Auslieferungslogs: Zuschauer-PII beim Zurückschreiben der Logs nach FSx berücksichtigen.
6. **Freigabe-Nachvollziehbarkeit**: erfassen, welches Objekt von wem und wann für die öffentliche
   Auslieferung freigegeben wurde. Objekte ohne erfassten Freigeber werden **sichtbar gemacht**
   (`unrecorded`), nicht stillschweigend blockiert.
7. **Datenresidenz / Geo-Beschränkung**: CDNs liefern global aus. Daten, die eine Region nicht verlassen
   dürfen, ausschließen oder Geo-Blocking erzwingen; Residenzprüfungen in den Freigabeprozess aufnehmen.

### 4.1 Evidenzklassifizierung
- **Öffentliche Evidenz**: Anbieterfähigkeiten in Abschnitt 3 — basierend auf öffentlichen Dokumenten,
  **zeitabhängig**, vor Einführung erneut prüfen.
- **Zu verifizieren (dieses Projekt)**: Verhalten der SigV4-Origin-Signierung am accesspoint alias des
  FSx for ONTAP S3 AP.

## 5. Machbarkeitszusammenfassung

| Frage | Antwort |
|-------|---------|
| S3 AP als unauthentifizierten CDN-Origin freigeben? | **Nein** (BPA erzwungen) |
| Direkt vom S3 AP über ein CDN ausliefern? | **Ja, bedingt** — M1/M2 mit SigV4; AP-alias-Signierung ist TBV |
| Über ein CDN ohne SigV4 ausliefern? | **Ja** — M3 (Push) oder M4 (Signierungsproxy) |
| S3-Presigned-URLs für Zuschauer nutzen? | **Nein** — CDN-native Tokens verwenden |
| ONTAP-ACLs zur Auslieferungszeit erzwingen? | **Nein** — über „nur freigegebene Renditions" + Nachvollziehbarkeit sichergestellt |
| Erster Schritt mit geringstem Verifizierungsrisiko? | **M3 (Push)** — vermeidet Origin-Auth, anbieterneutral, DemoMode-freundlich |

> **Governance Caveat**: Dies sind technische Referenzinformationen. Anbieterfunktionen ändern sich; vor der
> Einführung mit den aktuellsten offiziellen Dokumenten erneut prüfen. Die SigV4-Origin-Signierung am
> accesspoint alias des S3 AP ist ein Projektverifizierungspunkt (TBV). Die Anbieterauswahl liegt beim Kunden.
