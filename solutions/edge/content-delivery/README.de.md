# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/Edge (anbieterneutral)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Anbieterneutrales Serverless-Muster, das FSx for NetApp ONTAP als **Single Source of Truth (Master)**
beibehält und **freigegebene Renditions** auf S3 Access Points (S3 AP) über ein CDN/Edge-Netzwerk
auslieferbar macht.

Den technischen Machbarkeitsvergleich der Auslieferungsnetzwerke (CloudFront / Akamai / Fastly /
Cloudflare / Bunny.net / Google Media CDN usw.) finden Sie unter **[CDN-Vergleich](../docs/cdn-comparison.de.md)**.

> Dies ist eine Referenzimplementierung. Anbieterauswahl, Rechteverwaltung, Geo-Beschränkungen und
> Compliance liegen in der Verantwortung des Kunden.

> **TL;DR (30s)**: Ohne den ONTAP/NAS-Master zu verschieben, **nur freigegebene Renditions** über CloudFront
> oder ein Drittanbieter-CDN ausliefern. Mit dem risikoärmsten `PUBLISH_PUSH` (M3) beginnen. SigV4-Direct-Pull
> (ORIGIN_PULL) erst nach Messung mit der [Verifizierungs-Checkliste](../docs/cdn-origin-verification-checklist.de.md) einsetzen.

## Geschäftsergebnis & Einführung (Outcome / Adoption)

Nach **Geschäftsergebnis** bewerten, nicht nach „es wurde bereitgestellt".

| Aspekt | Outcome / Metrik / Messmethode |
|---|---|
| Geschäftsergebnis | Edge-Auslieferung ohne Master-Duplikat (nur freigegebene Renditions werden kopiert) |
| Metrik | In die Auslieferungsschicht durchsickernde Master-Objekte = 0 / Anzahl `unrecorded`-Freigaben |
| Messung | `provenance` und `skipped`/`published` aus dem Publish-Manifest aggregieren |

- **Sicherer Experimentierrahmen**: `DemoMode=true` validiert die Logik ohne FSx/externes CDN.
- **Business Sponsor**: einen Auslieferungs-Owner (Medien-/Plattformteam) benennen, der Go/No-Go freigibt.
- **Go/No-Go-Checkliste**: keine Objekte außerhalb `ApprovedPrefix` adressiert; Freigabe-Nachweis erfasst;
  Zuschauer-Tokens über CDN-nativen Mechanismus; bei ORIGIN_PULL ist die SigV4×alias-Messung PASS.
- Künftige Arbeit als **Evidenz-Erweiterung** (TBV → gemessen) darstellen, nicht als Unvollständigkeit.

## Partner/SI-Leitfaden

- **Erste Kundenfrage**: „Möchten Sie bestehende NAS/ONTAP-Assets ohne Kopie an die Edge-Auslieferung
  anbinden? Erfolgt die Auslieferung über CloudFront oder ein vertraglich gebundenes CDN (z. B. Akamai)?"
- **PoC-Ergebnisse**: DemoMode-Demo → Auslieferungsmanifest der freigegebenen Renditions → (optional)
  Hardware-SigV4-Verifizierungsergebnis. Den [CDN-Vergleich](../docs/cdn-comparison.de.md) direkt im Kundengespräch nutzen.

## Zwei Integrationsmechanismen

- **ORIGIN_PULL**: keine Objektkopie; erzeugt ein Origin-Referenzmanifest für ein CDN, das das S3 AP direkt
  per SigV4 abruft. CloudFront wird über OAC nativ unterstützt (Referenz). SigV4-Origin-Signierung auf
  Drittanbieter-CDNs ist **zu verifizieren**.
- **PUBLISH_PUSH**: repliziert freigegebene Renditions in den S3-kompatiblen Objektspeicher des CDN. Umgeht
  die Origin-Auth-Frage und bleibt anbieterneutral — der risikoärmste erste Schritt.

## Schlüsselkomponenten

| Komponente | Rolle |
|---|---|
| `functions/publish/handler.py` | Spiegelt freigegebene Renditions in die Auslieferungsschicht und schreibt ein Auslieferungsmanifest zurück ins S3 AP |
| `functions/delivery_log_sync/handler.py` | Normalisiert CDN-Auslieferungslogs (IP-Maskierung) und schreibt sie zur Korrelation mit Produktionsdaten ins S3 AP zurück |
| Step Functions | Publish → SNS-Benachrichtigung |
| CloudFront (optional) | Referenzauslieferung für ORIGIN_PULL (OAC + SigV4) |

## Deployment

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

## Sicherheit / Governance

- **permission-aware**: Auslieferung ist auf Objekte unter `ApprovedPrefix` beschränkt. ACL-kontrollierte
  Masterdaten werden nicht direkt ausgeliefert.
- **Zuschauer-Authentifizierung**: S3-Presigned-URLs nicht unterstützt → CDN-native Token-Mechanismen.
- **PII**: Client-IP wird beim Zurückschreiben der Logs maskiert (`RedactClientIp=true`).
- **Least Privilege**: Auslieferungs-Lambdas laufen **außerhalb des VPC** für den Internet-origin-Zugriff.

> **Governance Note**: Die Auslieferung erzwingt keine ONTAP-Dateiberechtigungen. Die Auslieferungsgrenze
> wird durch die Regel „nur freigegebene Renditions", den Freigabe-Trail und die Zugriffskontrollen des
> Auslieferungsziels gewährleistet.

### Verantwortlichkeiten (RACI / Public Sector)

| Rolle | Verantwortung |
|---|---|
| Data Owner | Endverantwortung für Klassifizierung, Residenz und Freigabe-Eignung |
| Approver | Genehmigt Platzierung unter `ApprovedPrefix`; setzt Freigabe-Nachweis (approved-by / approval-id) |
| Audit Reviewer | Prüft regelmäßig `provenance` in Manifesten und Auslieferungslogs |
| Ops Owner | Empfängt Alarme, bearbeitet Vorfälle, führt Rollback aus |

- KI/automatische Entscheidungen sind **assistierende Signale**; die Freigabe entscheiden Menschen
  (Data Owner / Approver).
- **Nicht sensible synthetische/Beispiel**-Daten zur Verifizierung verwenden (keine Produktions-Personendaten).
- Technische Validierung **ersetzt nicht** die rechtliche/Compliance-/Datenschutzbewertung.

## Betrieb / Runbook

- **Alarme**: mit `EnableCloudWatchAlarms=true` benachrichtigen Lambda-Fehler (publish/log-sync) und Step-
  Functions-Fehler via SNS (`NotificationEmail`).
- **Triage**: Publish-Fehler → `/aws/lambda/<stack>-publish` prüfen; S3-AP-Autz (IAM + AP-Policy + ONTAP-
  Identität) von der External-Store-Auth (Secrets Manager) trennen. External-Push-Fehler →
  `ExternalStoreSecretName`, Endpoint, Bucket prüfen. Verdacht auf Grenzverletzung →
  [Incident-Response-Playbook](../docs/incident-response-playbook.md).
- **Rollback**: Auslieferung publiziert nur freigegebene Renditions; bei Fehlveröffentlichung das Objekt vom
  Auslieferungsziel (CDN-Store/Distribution) entfernen, aus `ApprovedPrefix` zurückziehen und neu publizieren.
- **External-Store-Auth**: für PUBLISH_PUSH zu Akamai/R2/Fastly gelten AWS-Standardanmeldedaten nicht —
  `ExternalStoreSecretName` setzen (Secrets Manager, `{"access_key_id","secret_access_key"}`).

## Zugehörige Dokumente

- [CDN/Edge-Auslieferungsvergleich](../docs/cdn-comparison.de.md)
- [ORIGIN_PULL SigV4 Verifizierungs-Checkliste](../docs/cdn-origin-verification-checklist.de.md) (Hardware-Prozedur)
- [Vergleich alternativer Architekturen](../docs/comparison-alternatives.md)
- [Incident-Response-Playbook](../docs/incident-response-playbook.md)
