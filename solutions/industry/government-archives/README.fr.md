# UC16 : Administrations publiques — Archivage numérique des documents publics et réponse FOIA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.md) | [Script de démo](docs/demo-guide.md) | [Dépannage](../docs/phase7-troubleshooting.md)

## Vue d'ensemble

Pipeline automatisé pour l'archivage numérique des documents publics
des administrations et la réponse aux demandes d'accès à l'information
(FOIA : Freedom of Information Act), reposant sur
FSx for ONTAP S3 Access Points.

## Cas d'usage

Numériser, classifier et caviarder (rédaction) automatiquement le grand
volume de documents publics (PDF, images numérisées, e-mails) détenus par
les administrations, afin de répondre rapidement aux demandes d'accès à l'information.

### Flux de traitement

```
FSx for ONTAP (Stockage des documents publics — ACL NTFS par service)
  → S3 Access Point
    → Workflow Step Functions
      → Discovery : Détection de nouveaux documents (PDF, TIFF, EML, MSG)
      → OCR : Numérisation des documents avec Textract (interrégion car ap-northeast-1 non pris en charge)
      → Classification : Classification des documents avec Comprehend (détermination du niveau de confidentialité)
      → EntityExtraction : Détection des données personnelles (nom, adresse, SSN, numéro de téléphone)
      → Redaction : Caviardage automatique des informations confidentielles (rédaction)
      → IndexGeneration : Génération d'un index de recherche plein texte (OpenSearch, désactivable)
      → ComplianceCheck : Vérification de la période de conservation / du calendrier d'élimination (NARA GRS)
```

### Données ciblées

| Format de données | Description | Taille typique |
|-----------|------|-----------|
| PDF | Documents publics, rapports, contrats | 100 KB – 50 MB |
| TIFF | Documents numérisés | 1 – 100 MB |
| EML / MSG | Archives d'e-mails | 10 KB – 10 MB |
| DOCX / XLSX | Documents Office | 50 KB – 20 MB |

### Services AWS

| Service | Usage |
|---------|------|
| FSx for ONTAP | Stockage persistant des documents publics (ACL NTFS par service) |
| S3 Access Points | Accès aux documents depuis le serverless |
| Step Functions | Orchestration du workflow |
| Lambda | Classification des documents, détection des données personnelles, caviardage |
| Amazon Textract ⚠️ | OCR des documents (interrégion via us-east-1) |
| Amazon Comprehend | Extraction d'entités, classification des documents, détection des données personnelles |
| Amazon Bedrock | Résumé des documents, génération de brouillons de réponse FOIA |
| Amazon Macie | Détection automatique des données sensibles |
| DynamoDB | Métadonnées des documents, gestion de l'état de traitement |
| OpenSearch Serverless | Index de recherche plein texte (optionnel, désactivé par défaut) |
| SNS | Alertes d'échéance FOIA |

### Adéquation au secteur public

- **Conformité NARA (National Archives and Records Administration)** : Répond aux exigences de gestion des archives électroniques
- **Réponse FOIA** : Suit automatiquement l'échéance de réponse de 20 jours ouvrés
- **FedRAMP High** : Conforme sur AWS GovCloud
- **Section 508** : Prise en charge de l'accessibilité (OCR + génération de textes alternatifs)
- **Records Management** : Gestion automatique des périodes de conservation et des calendriers d'élimination

### Flux de réponse FOIA

```
Réception de la demande FOIA
  → Recherche des documents ciblés (OpenSearch)
  → Détermination du niveau de confidentialité des documents correspondants
  → Caviardage automatique (données personnelles, informations de sécurité nationale)
  → Notification aux relecteurs
  → Suivi de l'échéance de réponse (20 jours ouvrés)
  → Génération du paquet de documents publiables
```

## Écrans vérifiés (captures d'écran)

### 1. Stockage des documents publics (via S3 Access Point)

Après réception d'une demande d'accès à l'information, les documents ciblés sont stockés sous le préfixe `archives/YYYY/MM/`.

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     Contenu : Liste des documents PDF sous le préfixe archives/ sur le S3 AP
     Masque : ID de compte, ARN du S3 AP, noms des documents -->
![UC16 : Confirmation du stockage des documents publics](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. Consultation des documents caviardés

Texte stocké sous le préfixe `redacted/` après traitement, où les données
personnelles sont remplacées par le marqueur `[REDACTED]`. **Écran que les agents généraux relisent avant publication.**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     Contenu : Aperçu du texte redacted dans la console S3, marqueurs [REDACTED] visibles
     Masque : ID de compte, noms des documents caviardés (noms d'exemple uniquement) -->
![UC16 : Aperçu du document caviardé](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. Métadonnées de caviardage (sidecar JSON)

Données sidecar pour l'audit. Les données personnelles d'origine ne sont pas conservées — seulement des hachages SHA-256.
Les décalages, les types d'entités (NAME / EMAIL / SSN, etc.) et la confiance sont enregistrés.

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     Contenu : Vue formatée de redaction-metadata/*.json
     Masque : ID de compte, noms des documents d'origine -->
![UC16 : Métadonnées de caviardage JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. Rappel d'échéance FOIA (notification e-mail SNS)

E-mail de rappel que les responsables FOIA reçoivent 3 jours ouvrés avant l'échéance.
En cas de dépassement, une notification OVERDUE avec severity=HIGH.

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     Contenu : E-mail FOIA_DEADLINE_APPROACHING affiché dans un client de messagerie
     Masque : e-mails destinataire/expéditeur, request_id (ID d'exemple uniquement) -->
![UC16 : E-mail de rappel d'échéance FOIA](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. Calendrier de conservation NARA GRS (DynamoDB Explorer)

Table `fsxn-uc16-demo-retention`. Pour chaque document, le code NARA GRS
(GRS 2.1 / 2.2 / 1.1), la durée de conservation (3 / 7 / 30 ans) et la date d'élimination prévue sont enregistrés.

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     Contenu : Liste des éléments de la table retention dans DynamoDB Explorer
     Masque : ID de compte, document_key (noms d'exemple uniquement) -->
![UC16 : Table du calendrier de conservation](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
Accélérer la réponse aux demandes d'accès à l'information en automatisant l'archivage des documents publics et la réponse FOIA (OCR, classification, caviardage, gestion des échéances de conservation).

### Metrics
| Métrique | Valeur cible (exemple) |
|-----------|------------|
| Documents traités / exécution | > 500 documents |
| Taux de réussite d'extraction de texte OCR | > 95% |
| Précision de détection des données personnelles | > 95% |
| Temps de caviardage / document | < 30 secondes |
| Réduction du temps de réponse FOIA | > 50% |
| Taux obligatoire de Human Review | 100% (tous les résultats de caviardage requièrent une confirmation humaine) |

> **Pourquoi 100% de Human Review** : Comme un caviardage manqué affecte directement la divulgation d'informations et la protection des données personnelles, la confirmation humaine de chaque élément est obligatoire.

### Measurement Method
Historique d'exécution Step Functions, résultats de détection PII de Comprehend, diff avant/après caviardage, historique de conservation DynamoDB, CloudWatch Metrics. Les résultats de relecture sont enregistrés dans DynamoDB afin que, lors des audits, « qui a confirmé/approuvé quoi et quand » soit traçable.

### Sample Run Results (exemple mesuré)

**Environnement** : FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| Indicateur | Before (manuel) | After (automatisation S3AP) |
|------|-------------|-------------------|
| Temps de réponse FOIA | Jours à semaines | 389 ms (10 docs, sequential) |
| Détection de documents | Recherche manuelle | 32 ms (10 documents) |
| Lecture de fichier | Accès individuel | avg 36 ms / document |
| Qualité du caviardage | Dépend de l'agent, incohérences | Détection PII Comprehend + caviardage automatique |
| Human Review | Aucun ou irrégulier | 100% (tous les éléments requièrent une confirmation humaine) |
| Piste d'audit | Registres personnels | DynamoDB (who/when/what) + S3 Object Lock |
| Gestion des échéances de conservation | Manuel | Suivi automatique + alertes |

> **Remarque** : Le sample run d'UC16 est une validation utilisant des documents d'exemple synthétiques ou non sensibles et ne représente pas des documents administratifs réels ni des données de production. Ce sample run valide uniquement le chemin de traitement. La qualité du caviardage, l'exhaustivité de la Human Review et l'évaluation de la piste d'audit doivent être menées séparément dans un PoC spécifique au client.

## Déploiement

### Validation préalable

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Déploiement en une commande

```bash
bash scripts/deploy_phase7.sh government-archives
```

### Déploiement manuel

```bash
# Prérequis : AWS SAM CLI requis. sam build empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### Modes OpenSearch

| Mode | Usage | Coût mensuel (estimation) |
|--------|------|-------------------|
| `none` | Validation / exploitation à faible coût (par défaut) | $0 |
| `serverless` | Charges variables, paiement à l'usage | $350 – $700 |
| `managed` | Charges fixes, faible coût | $35 – $100 |

## Arborescence des répertoires

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # Textract interrégion
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # Période de conservation NARA GRS
│   └── foia_deadline_reminder/handler.py  # Suivi sur 20 jours ouvrés
├── tests/                            # 52 pytest (Hypothesis inclus)
└── README.md
```


---

## Liens vers la documentation AWS

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [Guide de l'utilisateur](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guide du développeur](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [Guide du développeur](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [Guide du développeur](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [Guide de l'utilisateur](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [Guide du développeur](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Alignement sur le Well-Architected Framework

| Pilier | Alignement |
|----|------|
| Excellence opérationnelle | X-Ray, EMF, suivi des échéances FOIA, 52+ tests |
| Sécurité | Rédaction des données personnelles, sidecar d'audit SHA-256, Macie, 100% Human Review |
| Fiabilité | Step Functions Retry/Catch, OCR interrégion, tests de résilience |
| Efficacité des performances | Détection PII parallèle, index OpenSearch, traitement par lots |
| Optimisation des coûts | Serverless, OpenSearch Serverless, indexation conditionnelle |
| Durabilité | Conformité NARA GRS, gestion de la conservation, calendrier d'élimination automatique |





---

## Estimation des coûts (approximation mensuelle)

> **Remarque** : Les chiffres ci-dessous sont des approximations pour la région ap-northeast-1 ; les coûts réels varient selon l'usage. Consultez les derniers tarifs sur [AWS Pricing Calculator](https://calculator.aws/).

### Composants serverless (paiement à l'usage)

| Service | Prix unitaire | Usage estimé | Approx. mensuelle |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 fonctions × 100 docs/jour | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/jour | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/jour | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/exécution | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/requête | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/jour | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mois | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### Coût fixe (FSx for ONTAP — suppose un environnement existant)

| Composant | Mensuel |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (partage un environnement existant) |
| S3 Access Point | Aucun frais supplémentaire (frais S3 API uniquement) |

### Estimation totale

| Configuration | Approx. mensuelle |
|------|---------|
| Minimale (une fois par jour) | ~$5-15 |
| Standard (horaire) | ~$15-50 |
| Grande échelle (haute fréquence + alarmes) | ~$50-150 |

> **Governance Caveat** : Les estimations de coûts sont approximatives et non garanties. La facturation réelle varie selon le modèle d'usage, le volume de données et la région.

---

## Tests locaux

### Vérification des prérequis

```bash
# Vérifier les prérequis
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (pour sam local)
aws sts get-caller-identity  # Identifiants AWS
```

### sam local invoke

```bash
# Build
# Prérequis : AWS SAM CLI requis. sam build empaquette automatiquement le code et la couche partagée.
sam build

# Exécution locale de la fonction Lambda Discovery
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Avec surcharge des variables d'environnement
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Tests unitaires

```bash
python3 -m pytest tests/ -v
```

Pour plus de détails, consultez le [Guide de démarrage rapide des tests locaux](../docs/local-testing-quick-start.md).

---

## Exemple de sortie (Output Sample)

Exemple de sortie du traitement d'archivage des documents publics / FOIA :

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **Remarque** : Ce qui précède est un exemple de sortie ; les valeurs réelles varient selon l'environnement et les données d'entrée. Les chiffres de benchmark sont une référence de dimensionnement, et non une limite de service.

---

## Governance Note

> Ce modèle fournit des indications d'architecture technique. Il ne s'agit pas de conseils juridiques, de conformité ou réglementaires. Les organisations doivent consulter des professionnels qualifiés.

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement des S3 Access Points for FSx for ONTAP, consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
