# ORIGIN_PULL SigV4 × S3 AP alias — Checklist de vérification sur matériel

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## Objectif

Procédure reproductible pour trancher, sur matériel réel, les points marqués **à vérifier (TBV)** dans le
[comparatif CDN](cdn-comparison.fr.md) : à savoir **si la signature d'origine SigV4 de chaque CDN
fonctionne sur l'hôte `accesspoint alias` du S3 Access Point FSx for ONTAP comme sur un bucket S3 standard**.

À utiliser pour décider si `DeliveryMode=ORIGIN_PULL` (M1/M2) de `content-edge-delivery` est viable.
**M3 (PUBLISH_PUSH) ne dépend pas de cette vérification** (il évite l'auth d'origine).

> **Distinction** : il s'agit d'une mesure dans un environnement de test spécifique. Ne pas considérer le
> comportement général de S3 ni le bilan d'un CDN sur des buckets standard comme une garantie pour l'alias S3 AP.

---

## 0. Prérequis

- Un système de fichiers FSx for ONTAP et un S3 Access Point en **Internet-origin** (le VPC-origin ne peut
  pas servir les CDN)
- L'alias S3 AP (ex. `<alias>-ext-s3alias`) et la région cible
- Un objet de test sous le **préfixe approuvé** (ex. `delivery-approved/test-1mb.bin`)
  - Conformément au principe permission-aware, ne pas utiliser de données master contrôlées par ACL
- Des identifiants IAM à **moindre privilège** pour la signature d'origine (`s3:GetObject` sur l'AP cible
  uniquement) ; préférer des identifiants éphémères
- Un hôte de test (curl ≥ 7.75 prend en charge `--aws-sigv4`), AWS CLI v2

> **Sécurité** : ne jamais laisser de clés d'accès dans les logs, captures ou commits pendant la
> vérification. Référencer par nom de clé, pas par valeur (politique de dépôt public).

---

## 1. Vérification de référence (sans CDN / la plus importante)

Sans CDN, confirmer directement **si l'hôte alias S3 AP accepte SigV4**. C'est le point crucial commun à
tous les CDN.

### 1.1 AWS CLI (signature SDK)

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- Attendu : HTTP 200 et récupération réussie de l'objet.
- En cas d'échec : isoler IAM / politique AP / identité de fichier ONTAP (UNIX UID / AD) dans l'autorisation
  à deux niveaux.

### 1.2 SigV4 brut (approxime la signature d'origine du CDN)

Les CDN signent généralement les pulls d'origine en SigV4 avec une clé d'accès fixe. `curl --aws-sigv4`
approxime ce comportement :

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **Si cela renvoie 200** : l'hôte alias accepte SigV4 comme un bucket standard → M1/M4 probablement viables.
- **En cas d'échec** : une différence d'adressage propre à l'alias peut être en cause → vérifier dans la
  config d'origine de chaque CDN le format d'hôte, la région, le nom de service (`s3`) et la gestion
  path-style vs virtual-host.
- Avec des identifiants temporaires, ajouter `-H "x-amz-security-token: $AWS_SESSION_TOKEN"`.

### 1.3 Contrôles négatifs (reconfirmer la spec)

- Un GET non signé renvoie **403/AccessDenied** (confirme l'application de Block Public Access).
- Les URL présignées sont indisponibles (génération impossible/non prise en charge) → jetons spectateur via
  mécanismes natifs du CDN.

---

## 2. Procédures par CDN

Pour chaque CDN, définir « origine = hôte alias S3 AP » et confirmer qu'un fetch d'origine sur cache-miss
renvoie 200.

### 2.1 Amazon CloudFront (M1 / OAC) — référence
- Déployer le template `content-edge-delivery` avec `EnableCloudFront=true` (OAC + `SigningProtocol: sigv4`).
- Vérifier : `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200.
- Attendu : réussite selon le tutoriel officiel AWS (**avéré**).

### 2.2 Fastly (M1 / SigV4 natif)
- Configurer l'hôte alias comme origine privée S3-compatible et activer la signature SigV4 (région, service `s3`).
- Vérifier : GET via le service Fastly → 200. Vérifier que la forme virtual-host de l'alias est signée
  correctement par l'implémentation SigV4 de Fastly.

### 2.3 Cloudflare (M2 / signature Workers)
- Implémenter SigV4 dans un Worker et fetch signé vers l'hôte alias (si le S3 AP est utilisé directement
  comme origine, pas R2). Vérifier : GET via le Worker → 200 ; vérifier les en-têtes signés / le hash de payload.

### 2.4 Akamai (M1 / Cloud Access Manager)
- Configurer la signature AWS dans Cloud Access Manager et définir l'hôte alias via Origin Characteristics.
- Vérifier : GET via la propriété Akamai → 200 ; confirmer que la signature s'applique sur l'hôte AP alias.

### 2.5 Bunny.net (M1 / origin-pull S3)
- Définir l'origine de la Pull Zone sur l'hôte alias avec le type d'origine AWS S3. Vérifier : GET via la
  Pull Zone → 200.

### 2.6 Google Cloud CDN / Media CDN (M1 / private S3 origin)
- Configurer l'hôte alias avec l'auth SigV4 d'origine privée S3-compatible. Vérifier : GET via Media CDN →
  200 ; vérifier aussi le chemin d'egress cross-cloud.

---

## 3. Critères de réussite/échec

| Résultat | Condition |
|----------|-----------|
| **PASS** | La référence 1.2 est 200 ET un GET sur cache-miss via le CDN est 200 ; les jetons spectateur fonctionnent via le mécanisme natif du CDN |
| **CONDITIONAL** | Le GET via le CDN est 200 mais nécessite une config supplémentaire (path-style, etc.) ou des contraintes (en-têtes spécifiques) |
| **FAIL** | SigV4 vers l'hôte alias ne fonctionne pas sur le CDN ; un contournement est requis (signature M2 / proxy M4 / bascule M3) |
| **BLOCKED** | Les prérequis (Internet-origin, IAM, objet de test) ne sont pas en place ; impossible de vérifier |

---

## 4. Contrôles sécurité/gouvernance pendant la vérification

- [ ] Objets de test uniquement sous `delivery-approved/` (pas de master contrôlé par ACL)
- [ ] IAM de signature d'origine limité à `s3:GetObject` sur l'AP cible
- [ ] Pas de clés longue durée laissées à l'edge/config (préférer éphémères ; révoquer après)
- [ ] Pas de clés d'accès, valeurs d'alias réelles ou ID de compte dans logs/captures/commits
- [ ] Jetons spectateur via mécanismes natifs du CDN (pas d'URL présignées S3)
- [ ] Nettoyer les ressources temporaires (distributions, pull zones, etc.) créées pour la vérification

---

## 5. Tableau d'enregistrement des résultats (preuves)

| CDN | Mécanisme | Config faite | Référence 1.2 | GET via CDN | Jeton spectateur | Résultat | Preuve (statut HTTP/en-têtes/horodatage) | Date | Rôle |
|-----|-----------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> Note d'enregistrement : valeurs d'alias, ID de compte, IP en placeholders (`<alias>-ext-s3alias`,
> `123456789012`). Traiter les résultats comme des mesures dans un environnement de test spécifique, non
> comme des garanties générales.

---

## 6. Remontée des résultats

- Reporter les résultats confirmés dans le [comparatif CDN](cdn-comparison.fr.md) section 3 « TBV propre au
  S3 AP » et 4.1 « à vérifier » (TBV → résultat mesuré).
- Pour les CDN en FAIL, recommander `DeliveryMode=PUBLISH_PUSH` (M3) dans `content-edge-delivery`.

## Documents associés

- [Comparatif d'intégration CDN/edge](cdn-comparison.fr.md)
- [UC content-edge-delivery](../solutions/edge/content-delivery/README.fr.md)
- [Notes de compatibilité S3AP](s3ap-compatibility-notes.md)
