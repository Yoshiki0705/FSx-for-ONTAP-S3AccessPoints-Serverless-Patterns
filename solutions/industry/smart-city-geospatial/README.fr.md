# UC17 : Smart City — Analyse géospatiale et urbanisme

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation** : [Architecture](docs/architecture.md) | [Script de démonstration](docs/demo-guide.md) | [Dépannage](../docs/phase7-troubleshooting.md)

## Vue d'ensemble

Pipeline d'analyse automatisée de données géospatiales (SIG) reposant sur
FSx for ONTAP S3 Access Points. Il intègre imagerie satellite, LiDAR et
données de capteurs IoT pour l'urbanisme, la surveillance des infrastructures et la réponse aux catastrophes.

## Cas d'usage

Les collectivités locales et les agences d'urbanisme intègrent des données
géospatiales de sources multiples afin d'automatiser la surveillance de l'état
des infrastructures urbaines, la détection des changements et l'évaluation des risques de catastrophe.

### Flux de traitement

```
FSx for ONTAP (stockage de données SIG — contrôle d'accès par service)
  → S3 Access Point
    → Workflow Step Functions
      → Discovery : détection de nouvelles données (GeoTIFF, Shapefile, GeoJSON, LAS)
      → Preprocessing : conversion / normalisation du système de coordonnées (unification EPSG, EPSG:4326)
      → LandUseClassification : classification de l'usage du sol (inférence ML)
      → ChangeDetection : détection de changements en série temporelle (nouveaux bâtiments, réduction des espaces verts)
      → InfraAssessment : évaluation de la dégradation des infrastructures (routes, ponts, nuages de points LAS)
      → RiskMapping : génération de cartes de risques de catastrophe (inondation, séisme, glissement de terrain)
      → ReportGeneration : génération de rapports d'urbanisme (Bedrock Nova Lite)
```

### Données cibles

| Format de données | Description | Taille typique |
|-----------|------|-----------|
| GeoTIFF | Photos aériennes / imagerie satellite | 100 Mo – 10 Go |
| Shapefile (.shp) | Données vectorielles (routes, bâtiments, parcelles) | 1 – 500 Mo |
| GeoJSON | Données vectorielles légères | 1 Ko – 100 Mo |
| LAS / LAZ | Nuages de points LiDAR (terrain / bâtiments 3D) | 100 Mo – 5 Go |
| GeoPackage (.gpkg) | Base de données SIG au standard OGC | 10 Mo – 2 Go |

### Services AWS

| Service | Utilisation |
|---------|------|
| FSx for ONTAP | Stockage persistant des données SIG (NTFS ACL par service) |
| S3 Access Points | Accès aux données depuis les composants serverless |
| Step Functions | Orchestration des workflows |
| Lambda | Prétraitement, conversion de coordonnées, extraction de métadonnées |
| SageMaker (Batch Transform) | Classification de l'usage du sol, inférence ML de détection de changements (optionnel) |
| Amazon Rekognition | Détection d'objets à partir d'imagerie aérienne (bâtiments, véhicules) |
| Amazon Bedrock Nova Lite | Génération de rapports d'urbanisme en japonais |
| DynamoDB | Historique de l'usage du sol en série temporelle, détection de changements |
| SNS | Alertes de détection d'anomalies |
| CloudWatch | Observabilité |

### Adéquation au secteur public

- **Prise en charge de la directive INSPIRE** (infrastructure de données géospatiales de l'UE)
- **Conformité aux standards OGC** : WMS, WFS, WCS, GeoPackage
- **Données ouvertes** : les résultats de traitement peuvent être publiés sur des portails citoyens
- **Réponse aux catastrophes** : cartographie en temps réel de la situation des dommages
- **Souveraineté des données** : les données des collectivités restent dans la région

### Scénarios d'utilisation

| Scénario | Données d'entrée | Sortie |
|---------|-----------|------|
| Surveillance du verdissement urbain | Imagerie satellite (série temporelle) | Rapport de variation des espaces verts |
| Détection de dépôts illégaux | Imagerie de drone | Alerte + informations de localisation |
| Évaluation de la dégradation des routes | Imagerie de caméra embarquée | Carte de priorité des réparations |
| Évaluation du risque d'inondation | LiDAR + données de précipitations | Carte de prévision d'inondation |
| Appui à l'instruction des permis de construire | Imagerie aérienne + demande de permis | Rapport de détection des écarts |

## Écrans vérifiés (captures d'écran)

### 1. Stockage des données SIG (via S3 Access Point)

Écran de confirmation du placement des données à analyser, vu par un agent SIG de la collectivité.
GeoTIFF / Shapefile / LAS sont placés sous le préfixe `gis/YYYY/MM/`.

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     Contenu : liste du préfixe gis/ du S3 AP, formats de fichiers mixtes
     Masque : ID de compte, ARN du S3 AP, noms de fichiers dérivés de coordonnées réelles -->
![UC17 : confirmation du stockage des données SIG](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Rapport d'urbanisme généré par Bedrock (affichage Markdown)

**Fonctionnalité phare d'UC17** : en intégrant la répartition de l'usage du sol,
la détection des changements et l'évaluation des risques, Bedrock Nova Lite génère
automatiquement un rapport en japonais destiné aux agents de la collectivité.

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     Contenu : reports/*.md rendu dans la console S3
     Contenu réel de l'échantillon :
       ### Rapport d'observations pour les agents de la collectivité
       #### Points d'attention pour l'urbanisme
       D'après les données SIG, la répartition de l'usage du sol dans la ville est stable...
       #### Mesures prioritaires à envisager
       1. Renforcer les mesures anti-inondation ... 2. Renforcer les mesures antisismiques ... 3. Renforcer les mesures contre les glissements de terrain ...
     Masque : ID de compte, nom de la collectivité (seul le nom d'échantillon est affiché) -->
![UC17 : rapport généré par Bedrock](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. JSON de la carte de risques de catastrophe

Trois types de scores de risque — inondation, séisme et glissement de terrain — sont classés
en quatre niveaux : CRITICAL / HIGH / MEDIUM / LOW.

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     Contenu : vue formatée de risk-maps/*.json (niveaux flood, earthquake, landslide mis en évidence)
     Masque : ID de compte -->
![UC17 : carte de risques de catastrophe](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. Répartition de l'usage du sol (JSON)

Répartition des classes d'usage du sol dérivée des résultats d'inférence Rekognition / SageMaker.
Ratios de residential / commercial / forest / water / road, etc.

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     Contenu : contenu de landuse/*.json (residential: 0.5, forest: 0.3, etc.)
     Masque : ID de compte -->
![UC17 : répartition de l'usage du sol](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. Visualisation des changements en série temporelle (DynamoDB Explorer)

Table `fsxn-uc17-demo-landuse-history`. Pour chaque area_id, les répartitions passées
de l'usage du sol sont comparées aux valeurs actuelles pour calculer change_magnitude.

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     Contenu : éléments en série temporelle de la table landuse-history dans DynamoDB Explorer
     Masque : ID de compte, area_id -->
![UC17 : table des changements en série temporelle](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
En automatisant l'analyse géospatiale (normalisation CRS, classification de l'usage du sol, cartographie des risques de catastrophe), elle appuie la prise de décision en urbanisme.

### Metrics
| Métrique | Valeur cible (exemple) |
|-----------|------------|
| Jeux de données traités / exécution | > 100 files |
| Taux de réussite de la normalisation CRS | > 95% |
| Précision de la classification de l'usage du sol | > 80% |
| Temps de génération de la carte de risques | < 10 min |
| Coût / exécution | < $10 |
| Taux cible de Human Review | < 20 % (zones à classification incertaine) |

### Measurement Method
Historique d'exécution Step Functions, rapports d'analyse Bedrock, résultats de détection Rekognition, GeoJSON de sortie S3, CloudWatch Metrics.

## Déploiement

### Vérification préalable

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Déploiement en une commande

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### Déploiement manuel

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Important** : activez l'accès au modèle `amazon.nova-lite-v1:0` dans la console Bedrock.

## Structure des répertoires

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # normalisation CRS (EPSG:4326)
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # analyse de nuages de points LAS/LAZ
│   ├── risk_mapping/handler.py           # risque inondation/séisme/glissement de terrain
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## Liens vers la documentation AWS

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [Guide de l'utilisateur](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guide du développeur](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [Guide du développeur](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [Guide du développeur](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [Guide de l'utilisateur](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Alignement sur le Well-Architected Framework

| Pilier | Alignement |
|----|------|
| Excellence opérationnelle | X-Ray, EMF, suivi des changements d'usage du sol, tests de résilience |
| Sécurité | IAM au moindre privilège, KMS, NTFS ACL par service, conformité INSPIRE |
| Fiabilité | Step Functions Retry/Catch, normalisation CRS, tests de résilience |
| Efficacité des performances | Tuilage GeoTIFF, SageMaker Batch Transform |
| Optimisation des coûts | Serverless, SageMaker Spot, séries temporelles DynamoDB |
| Durabilité | Détection incrémentale des changements, conformité aux standards OGC |





---

## Estimation des coûts (approximation mensuelle)

> **Remarque** : ce qui suit est une estimation pour la région ap-northeast-1 ; les coûts réels varient selon l'usage. Vérifiez les tarifs les plus récents avec l'[AWS Pricing Calculator](https://calculator.aws/).

### Composants serverless (paiement à l'usage)

| Service | Prix unitaire | Usage estimé | Approx. mensuel |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 fonctions × 20 datasets/jour | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/jour | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/jour | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/exécution | ~$3-10 |
| Athena | $5/TB scanned | ~30 Mo/requête | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/jour | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 Go/mois | ~$0.76 |

### Coûts fixes (FSx for ONTAP — environnement existant supposé)

| Composant | Mensuel |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (environnement existant partagé) |
| S3 Access Point | Pas de frais supplémentaires (frais S3 API uniquement) |

### Estimation totale

| Configuration | Approx. mensuel |
|------|---------|
| Minimale (une fois par jour) | ~$5-15 |
| Standard (toutes les heures) | ~$15-50 |
| Grande échelle (haute fréquence + alarmes) | ~$50-150 |

> **Governance Caveat** : les estimations de coûts sont approximatives et non garanties. La facturation réelle varie selon les modes d'usage, le volume de données et la région.

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
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
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

Pour plus de détails, voir le [Démarrage rapide des tests locaux](../docs/local-testing-quick-start.md).

---

## Exemple de sortie (Output Sample)

Exemple de sortie du pipeline d'analyse de données géospatiales :

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **Remarque** : ce qui précède est un exemple de sortie ; les valeurs réelles varient selon l'environnement et les données d'entrée. Les chiffres de référence sont une référence de dimensionnement, pas une limite de service.

---

## Governance Note

> Ce pattern fournit des orientations d'architecture technique. Il ne constitue pas un conseil juridique, de conformité ou réglementaire. Les organisations doivent consulter des professionnels qualifiés.

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement des S3 Access Points for FSx for ONTAP, voir les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
