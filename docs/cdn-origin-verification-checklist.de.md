# ORIGIN_PULL SigV4 × S3 AP alias — Hardware-Verifizierungs-Checkliste

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## Zweck

Eine reproduzierbare Prozedur, um auf echter Hardware die im [CDN-Vergleich](cdn-comparison.de.md) als
**zu verifizieren (TBV)** markierten Punkte zu klären: nämlich **ob die SigV4-Origin-Signierung jedes CDN am
`accesspoint alias`-Host des FSx for ONTAP S3 Access Point genauso funktioniert wie an einem Standard-S3-Bucket**.

Dient der Entscheidung, ob `DeliveryMode=ORIGIN_PULL` (M1/M2) von `solutions/edge/content-delivery` tragfähig ist.
**M3 (PUBLISH_PUSH) hängt nicht von dieser Verifizierung ab** (es vermeidet die Origin-Auth).

> **Abgrenzung**: Dies ist eine Messung in einer bestimmten Testumgebung. Allgemeines S3-Verhalten oder die
> Erfolgsbilanz eines CDN an Standard-Buckets nicht als Garantie für den S3-AP-Alias behandeln.

---

## 0. Voraussetzungen

- Ein FSx-for-ONTAP-Dateisystem und ein **Internet-origin**-S3-Access-Point (VPC-origin kann CDNs nicht bedienen)
- Der S3-AP-Alias (z. B. `<alias>-ext-s3alias`) und die Zielregion
- Ein Testobjekt unter dem **freigegebenen Präfix** (z. B. `delivery-approved/test-1mb.bin`)
  - Gemäß dem permission-aware-Prinzip keine ACL-kontrollierten Masterdaten zur Verifizierung verwenden
- IAM-Anmeldedaten mit **minimalen Rechten** für die Origin-Signierung (nur `s3:GetObject` auf dem Ziel-AP);
  kurzlebige Anmeldedaten bevorzugen
- Ein Test-Host (curl ≥ 7.75 unterstützt `--aws-sigv4`), AWS CLI v2

> **Sicherheit**: Während der Verifizierung keine Zugriffsschlüssel in Logs, Screenshots oder Commits
> belassen. Per Schlüsselname referenzieren, nicht per Wert (Richtlinie für öffentliche Repos).

---

## 1. Baseline-Verifizierung (ohne CDN / am wichtigsten)

Ohne CDN direkt bestätigen, **ob der S3-AP-Alias-Host SigV4 akzeptiert**. Dies ist der für alle CDNs
gemeinsame Kernpunkt.

### 1.1 AWS CLI (SDK-Signierung)

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- Erwartet: HTTP 200 und erfolgreicher Objektabruf.
- Bei Fehler: IAM / AP-Policy / ONTAP-seitige Identität (UNIX UID / AD) in der zweistufigen Autorisierung isolieren.

### 1.2 Rohes SigV4 (approximiert die Origin-Signierung des CDN)

CDNs signieren Origin-Pulls meist mit einem festen Zugriffsschlüssel per SigV4. `curl --aws-sigv4`
approximiert dieses Verhalten:

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **Wenn dies 200 liefert**: Der Alias-Host akzeptiert SigV4 wie ein Standard-Bucket → M1/M4 wahrscheinlich tragfähig.
- **Bei Fehler**: Eine alias-spezifische Adressierungsdifferenz kann die Ursache sein → in der
  Origin-Konfiguration jedes CDN Host-Format, Region, Servicename (`s3`) und Path-Style- vs.
  Virtual-Host-Handhabung einzeln prüfen.
- Bei temporären Anmeldedaten `-H "x-amz-security-token: $AWS_SESSION_TOKEN"` ergänzen.

### 1.3 Negativprüfungen (Spezifikation rückbestätigen)

- Ein unsignierter GET liefert **403/AccessDenied** (bestätigt die Durchsetzung von Block Public Access).
- Presigned URLs sind nicht verfügbar (nicht erzeugbar/nicht unterstützt) → Zuschauer-Tokens über
  CDN-native Mechanismen.

---

## 2. Prozeduren je CDN

Für jedes CDN „Origin = S3-AP-Alias-Host" festlegen und bestätigen, dass ein Origin-Fetch bei Cache-Miss
200 liefert.

### 2.1 Amazon CloudFront (M1 / OAC) — Referenz
- `solutions/edge/content-delivery`-Template mit `EnableCloudFront=true` bereitstellen (OAC + `SigningProtocol: sigv4`).
- Verifizieren: `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200.
- Erwartet: Erfolg gemäß dem offiziellen AWS-Tutorial (**erprobt**).

### 2.2 Fastly (M1 / natives SigV4)
- Den Alias-Host als S3-kompatiblen privaten Origin konfigurieren und SigV4-Signierung aktivieren (Region,
  Service `s3`). Verifizieren: GET über den Fastly-Service → 200; prüfen, ob die Virtual-Host-Form des Alias
  von Fastlys SigV4-Implementierung korrekt signiert wird.

### 2.3 Cloudflare (M2 / Workers-Signierung)
- SigV4 in einem Worker implementieren und signierten Fetch an den Alias-Host (wenn das S3 AP direkt als
  Origin statt R2 genutzt wird). Verifizieren: GET über den Worker → 200; signierte Header / Payload-Hash-Handhabung prüfen.

### 2.4 Akamai (M1 / Cloud Access Manager)
- AWS-Signierung im Cloud Access Manager konfigurieren und den Alias-Host über Origin Characteristics setzen.
- Verifizieren: GET über die Akamai-Property → 200; bestätigen, dass die Signierung am AP-Alias-Host greift.

### 2.5 Bunny.net (M1 / S3-Origin-Pull)
- Den Pull-Zone-Origin per AWS-S3-Origin-Typ auf den Alias-Host setzen. Verifizieren: GET über die Pull Zone → 200.

### 2.6 Google Cloud CDN / Media CDN (M1 / private S3 origin)
- Den Alias-Host mit SigV4-Auth für privaten S3-kompatiblen Origin konfigurieren. Verifizieren: GET über
  Media CDN → 200; auch den Cross-Cloud-Egress-Pfad prüfen.

---

## 3. Pass/Fail-Kriterien

| Ergebnis | Bedingung |
|----------|-----------|
| **PASS** | Baseline 1.2 ist 200 UND ein Cache-Miss-GET über das CDN ist 200; Zuschauer-Tokens funktionieren über CDN-nativen Mechanismus |
| **CONDITIONAL** | CDN-GET ist 200, erfordert aber zusätzliche Konfiguration (z. B. Path-Style) oder Einschränkungen (bestimmte Header) |
| **FAIL** | SigV4 zum Alias-Host funktioniert auf dem CDN nicht; ein Workaround ist nötig (M2-Signierung / M4-Proxy / Wechsel zu M3) |
| **BLOCKED** | Voraussetzungen (Internet-origin, IAM, Testobjekt) fehlen; Verifizierung nicht möglich |

---

## 4. Sicherheits-/Governance-Prüfungen während der Verifizierung

- [ ] Testobjekte nur unter `delivery-approved/` (kein ACL-kontrollierter Master)
- [ ] Origin-Signierungs-IAM auf `s3:GetObject` am Ziel-AP beschränkt
- [ ] Keine Langzeitschlüssel an Edge/Config belassen (kurzlebige bevorzugen; danach widerrufen)
- [ ] Keine Zugriffsschlüssel, echten Alias-Werte oder Konto-IDs in Logs/Screenshots/Commits
- [ ] Zuschauer-Tokens über CDN-native Mechanismen (keine S3-Presigned-URLs)
- [ ] Für die Verifizierung erstellte temporäre Ressourcen (Distributions, Pull Zones usw.) aufräumen

---

## 5. Ergebnis-Aufzeichnungstabelle (Nachweise)

| CDN | Mechanismus | Config erledigt | Baseline 1.2 | GET über CDN | Zuschauer-Token | Ergebnis | Nachweis (HTTP-Status/Header/Zeitstempel) | Datum | Rolle |
|-----|-------------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> Aufzeichnungshinweis: Alias-Werte, Konto-IDs, IPs als Platzhalter (`<alias>-ext-s3alias`, `123456789012`).
> Ergebnisse als Messungen in einer bestimmten Testumgebung behandeln, nicht als allgemeine Garantien.

---

## 6. Ergebnisse zurückspielen

- Bestätigte Ergebnisse in den [CDN-Vergleich](cdn-comparison.de.md) Abschnitt 3 „S3-AP-spezifisches TBV"
  und 4.1 „zu verifizieren" übernehmen (TBV → gemessenes Ergebnis).
- Für CDNs mit FAIL `DeliveryMode=PUBLISH_PUSH` (M3) in `solutions/edge/content-delivery` empfehlen.

## Zugehörige Dokumente

- [CDN/Edge-Auslieferungsvergleich](cdn-comparison.de.md)
- [content-edge-delivery UC](../solutions/edge/content-delivery/README.de.md)
- [S3AP-Kompatibilitätshinweise](s3ap-compatibility-notes.md)
