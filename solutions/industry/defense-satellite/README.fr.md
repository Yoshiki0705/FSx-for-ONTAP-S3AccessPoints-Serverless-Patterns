# UC15: Défense / Spatial — Pipeline d'analyse d'imagerie satellite

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.fr.md) | [Script de démonstration](docs/demo-guide.fr.md) | [Dépannage](../docs/phase7-troubleshooting.md)

## Présentation

Pipeline d'analyse automatisée d'imagerie satellite (SAR / optique) exploitant
Amazon FSx for NetApp ONTAP S3 Access Points. Les données d'imagerie satellite de
grand volume sont stockées sur FSx for ONTAP, et le traitement serverless est exécuté
via S3 Access Points.

## Cas d'usage

Les agences de défense et de renseignement ainsi que les organisations liées au
spatial traitent et analysent automatiquement les données d'observation de la Terre
(Earth Observation) acquises par satellite.

### Flux de traitement

```
FSx for ONTAP (stockage d'imagerie satellite)
  → S3 Access Point
    → Workflow Step Functions
      → Discovery : détection de nouvelles images (GeoTIFF, NITF, HDF5)
      → Tiling : découpage des grandes images en tuiles (conversion Cloud Optimized GeoTIFF)
      → ObjectDetection : détection d'objets avec Rekognition / SageMaker
      → ChangeDetection : détection de changement par comparaison de séries temporelles
      → GeoEnrichment : enrichissement des métadonnées (coordonnées, date/heure de prise, résolution)
      → AlertGeneration : génération d'alerte en cas de détection d'anomalie
```

### Données ciblées

| Format de données | Description | Taille typique |
|-----------|------|-----------|
| GeoTIFF | Imagerie satellite optique | 100 MB – 10 GB |
| NITF | Format d'image standard militaire | 500 MB – 50 GB |
| HDF5 | Données SAR (Sentinel-1, etc.) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | Image déjà découpée en tuiles | 10 – 500 MB |

### Services AWS

| Service | Utilisation |
|---------|------|
| FSx for ONTAP | Stockage persistant de l'imagerie satellite (contrôle d'accès via NTFS ACL) |
| S3 Access Points | Accès aux images depuis le serverless |
| Step Functions | Orchestration du workflow |
| Lambda | Découpage en tuiles, extraction de métadonnées, génération d'alertes |
| SageMaker (Batch Transform) | Inférence ML de détection d'objets / de changement |
| Amazon Rekognition | Détection d'étiquettes (véhicules, bâtiments, navires) |
| Amazon Bedrock | Génération de légendes d'image, synthèse de rapports |
| DynamoDB | Gestion de l'état de traitement, index des résultats de détection |
| SNS | Notification d'alerte |
| CloudWatch | Observabilité |

### Conformité Public Sector

- **DoD CC SRG** : FSx for ONTAP est certifié Impact Level 2/4/5 (GovCloud)
- **CSfC** : NetApp ONTAP est certifié Commercial Solutions for Classified
- **FedRAMP** : conforme FedRAMP High sur AWS GovCloud
- **Souveraineté des données** : les données restent dans la région (ap-northeast-1 / us-gov-west-1)

## Écrans vérifiés (captures d'écran)

Présentation centrée sur **l'UI que les agents utilisent au quotidien**, d'après une
exécution réelle vérifiée dans ap-northeast-1 le 2026-05-10. Pour les écrans de console
destinés aux techniciens (graphes Step Functions, etc.), voir
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md).

### 1. Placement de l'imagerie satellite (via FSx for ONTAP / S3 Access Point)

Écran de confirmation de placement de l'imagerie satellite à analyser, tel que vu par
l'administrateur du serveur de fichiers. Il suffit de placer de nouvelles images sous le
préfixe `satellite/YYYY/MM/`, et le workflow Step Functions périodique les récupère
automatiquement.

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     Contenu : lister satellite/2026/05/*.tif via S3 AP (nom d'objet, taille, date de modification)
     Masquer : ID de compte, ARN de l'Access Point, noms réels des images satellite -->
![UC15 : placement de l'imagerie satellite](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. Consultation des résultats d'analyse (bucket S3 de sortie)

Les résultats de détection (`detections/*.json`), les métadonnées géographiques
(`enriched/*.json`) et les informations de tuiles (`tiles/*/metadata.json`) sont
organisés et stockés.

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     Contenu : vue d'ensemble des 3 préfixes detections/, enriched/, tiles/ dans la console S3
     Masquer : ID de compte, préfixe du nom de bucket -->
![UC15 : bucket S3 de sortie](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. Alerte de détection de changement (notification par e-mail SNS)

L'e-mail d'alerte SNS reçu par les agents (opérateurs). Envoyé automatiquement lorsque la
surface de changement dépasse le seuil (1 km² par défaut).

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     Contenu : afficher alert_type=SATELLITE_CHANGE_DETECTED dans un client de messagerie (Gmail/Outlook)
     Masquer : adresse e-mail du destinataire, adresse de l'expéditeur, coordonnées réelles, tile_id -->
![UC15 : e-mail d'alerte SNS](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. Contenu du JSON de résultat de détection

Un visualiseur JSON épuré des résultats de détection (étiquette, confiance, bbox).

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     Contenu : aperçu de l'objet dans la console S3, contenu du JSON detections
     Masquer : ID de compte -->
![UC15 : résultats de détection JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
En automatisant l'analyse d'imagerie satellite (détection d'objets, détection de changement, alertes), accélérer l'analyse du renseignement.

### Metrics
| Métrique | Valeur cible (exemple) |
|-----------|------------|
| Images traitées / exécution | > 50 images |
| Précision de détection d'objets | > 80% |
| Taux de réussite de détection de changement | > 85% |
| Temps de génération d'alerte | < 5 min |
| Coût / exécution | < $15 |
| Taux obligatoire de Human Review | 100% (approbation humaine obligatoire avant l'envoi de l'alerte) |

> **Raison du 100% Human Review** : l'impact métier d'une alerte erronée ou manquée étant extrêmement important, l'approbation humaine de tous les éléments est obligatoire.

### Measurement Method
Historique d'exécution Step Functions, résultats de détection Rekognition, rapports d'analyse Bedrock, journaux de notification SNS et CloudWatch Metrics. Les enregistrements d'approbation sont stockés dans DynamoDB afin de pouvoir tracer lors d'un audit « qui a approuvé quoi et quand ».

## Déploiement

### Vérification préalable

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Déploiement en une commande

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### Déploiement manuel

```bash
# Prérequis : AWS SAM CLI requis. sam build empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Important** : `S3AccessPointName` est requis pour l'attribution des autorisations IAM au S3 AP.
Pour les détails, voir [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md).

## Structure du répertoire

```
defense-satellite/
├── template.yaml              # Modèle SAM (développement)
├── template-deploy.yaml       # Modèle CloudFormation (déploiement)
├── functions/
│   ├── discovery/handler.py   # Détection de nouvelles images satellite
│   ├── tiling/handler.py      # Découpage en tuiles + conversion COG
│   ├── object_detection/handler.py  # Détection d'objets (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # Détection de changement par série temporelle
│   ├── geo_enrichment/handler.py    # Enrichissement de métadonnées géographiques
│   └── alert_generation/handler.py  # Génération d'alerte
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## Liens vers la documentation AWS

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [Guide de l'utilisateur](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guide du développeur](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [Guide du développeur](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [Guide du développeur](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [Guide de l'utilisateur](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Alignement avec le Well-Architected Framework

| Pilier | Alignement |
|----|------|
| Excellence opérationnelle | X-Ray, EMF, génération d'alertes, 100% Human Review |
| Sécurité | DoD CC SRG, FedRAMP, IAM à moindre privilège, KMS, isolation VPC |
| Fiabilité | Step Functions Retry/Catch, tests de résilience, repli |
| Efficacité des performances | Découpage COG en tuiles, détection d'objets en parallèle, SageMaker Batch |
| Optimisation des coûts | Serverless, SageMaker Spot, traitement par tuile |
| Durabilité | Exécution à la demande, détection de changement différentielle |





---

## Estimation des coûts (approximatif mensuel)

> **Remarque** : les valeurs suivantes sont approximatives pour la région ap-northeast-1 ; les coûts réels varient selon l'usage. Consultez les tarifs les plus récents sur le [AWS Pricing Calculator](https://calculator.aws/).

### Composants serverless (paiement à l'usage)

| Service | Prix unitaire | Usage supposé | Approx. mensuel |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 fonctions × 10 scenes/jour | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/jour | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/jour | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/exécution | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/requête | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/jour | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mois | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### Coût fixe (FSx for ONTAP — environnement existant supposé)

| Composant | Mensuel |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (environnement existant partagé) |
| S3 Access Point | Aucun frais supplémentaire (uniquement les frais d'API S3) |

### Total approximatif

| Configuration | Approx. mensuel |
|------|---------|
| Configuration minimale (une fois par jour) | ~$5-15 |
| Configuration standard (horaire) | ~$15-50 |
| Configuration à grande échelle (haute fréquence + alarmes) | ~$50-150 |

> **Governance Caveat** : les estimations de coûts sont approximatives et non garanties. Le montant réellement facturé varie selon le profil d'usage, le volume de données et la région.

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

# Exécuter la Lambda Discovery en local
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

Pour les détails, voir [Démarrage rapide des tests locaux](../docs/local-testing-quick-start.md).

---

## Exemple de sortie (Output Sample)

Exemple de sortie du pipeline d'analyse d'imagerie satellite (Human Review requis) :

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **Remarque** : ce qui précède est une sortie d'exemple ; les valeurs réelles varient selon l'environnement et les données d'entrée. Les chiffres de benchmark sont une référence de dimensionnement, pas une limite de service.

---

## Governance Note

> Ce pattern fournit des recommandations d'architecture technique. Il ne constitue pas un conseil juridique, de conformité ou réglementaire. Les organisations doivent consulter des professionnels qualifiés.

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les patterns de déclenchement des S3 Access Points for FSx for ONTAP, voir [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
