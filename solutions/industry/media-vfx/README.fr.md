# UC4 : Médias — Pipeline de rendu VFX

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Schéma d'architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Aperçu

Un workflow sans serveur qui exploite les S3 Access Points de FSx for ONTAP pour automatiser la soumission des travaux de rendu VFX, les contrôles de qualité et la réécriture des sorties approuvées.

### Quand ce modèle est adapté

- Vous utilisez FSx for ONTAP comme stockage de rendu pour la production VFX / animation
- Vous souhaitez automatiser les contrôles de qualité après le rendu et réduire la charge des revues manuelles
- Vous souhaitez réécrire automatiquement vers le serveur de fichiers les ressources ayant passé les contrôles de qualité (S3 AP PutObject)
- Vous souhaitez construire un pipeline qui intègre Deadline Cloud à un stockage NAS existant

### Quand ce modèle n'est pas adapté

- Vous avez besoin d'un déclenchement immédiat des travaux de rendu (déclencheurs à l'enregistrement de fichier)
- Vous utilisez une ferme de rendu autre que Deadline Cloud (par ex. Thinkbox Deadline sur site)
- La sortie de rendu dépasse 5 Go (la limite de S3 AP PutObject)
- Les contrôles de qualité nécessitent un modèle propriétaire d'évaluation de la qualité d'image (la détection de labels de Rekognition est insuffisante)

### Fonctionnalités principales

- Détection automatique des ressources de rendu cibles via S3 AP
- Soumission automatique des travaux de rendu à AWS Deadline Cloud
- Évaluation de la qualité par Amazon Rekognition (résolution, artefacts, cohérence des couleurs)
- En cas de réussite, PutObject vers FSx for ONTAP via S3 AP ; en cas d'échec, notification SNS

## Success Metrics

### Outcome
Réduire le temps de recherche des ressources grâce à la classification automatique et à l'étiquetage de métadonnées des ressources VFX.

### Metrics
| Métrique | Valeur cible (exemple) |
|-----------|------------|
| Ressources traitées par exécution | > 200 files |
| Taux de réussite de l'étiquetage de métadonnées | > 95% |
| Réduction du temps de recherche des ressources | > 60% |
| Temps de traitement par fichier | < 60 sec |
| Coût par exécution | < $10 |
| Taux soumis à Human Review | < 10% |

### Measurement Method
Historique d'exécution Step Functions, Rekognition label count, métadonnées de sortie S3.

## Architecture

```mermaid
graph LR
    subgraph "Workflow Step Functions"
        D[Discovery Lambda<br/>Détection des ressources]
        JS[Job Submit Lambda<br/>Soumission de travail Deadline Cloud]
        QC[Quality Check Lambda<br/>Évaluation qualité Rekognition]
    end

    D -->|Manifest| JS
    JS -->|Job Result| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    JS -.->|GetObject| S3AP
    JS -.->|CreateJob| DC[AWS Deadline Cloud]
    QC -.->|DetectLabels| Rekognition[Amazon Rekognition]
    QC -.->|PutObject (en cas de réussite)| S3AP
    QC -.->|Publish (en cas d'échec)| SNS[SNS Topic]
```

### Étapes du workflow

1. **Discovery** : Détecter les ressources de rendu cibles depuis le S3 AP et générer un Manifest
2. **Job Submit** : Récupérer les ressources via le S3 AP et soumettre les travaux de rendu à AWS Deadline Cloud
3. **Quality Check** : Évaluer la qualité des résultats de rendu avec Rekognition. En cas de réussite, PutObject vers le S3 AP ; en cas d'échec, signaler pour un nouveau rendu via une notification SNS

## Prérequis

- Un compte AWS et des autorisations IAM appropriées
- Un système de fichiers FSx for ONTAP (ONTAP 9.17.1P4D3 ou version ultérieure)
- Un volume avec S3 Access Points activés
- Des identifiants ONTAP REST API enregistrés dans Secrets Manager
- Un VPC et des sous-réseaux privés
- Une Farm / Queue AWS Deadline Cloud déjà configurée
- Une région où Amazon Rekognition est disponible

## Étapes de déploiement

### 1. Préparer les paramètres

Avant le déploiement, vérifiez les valeurs suivantes :

- FSx for ONTAP S3 Access Point Alias
- Adresse IP de gestion ONTAP
- Nom du secret Secrets Manager
- AWS Deadline Cloud Farm ID / Queue ID
- VPC ID, ID de sous-réseau privé

### 2. Déploiement SAM

```bash
# Prérequis : AWS SAM CLI est requis. sam build empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-media-vfx \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    S3AccessPointOutputAlias=<your-output-volume-ext-s3alias> \
    OntapSecretName=<your-ontap-secret-name> \
    OntapManagementIp=<your-ontap-management-ip> \
    ScheduleExpression="rate(1 hour)" \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    DeadlineFarmId=<your-deadline-farm-id> \
    DeadlineQueueId=<your-deadline-queue-id> \
    QualityThreshold=80.0 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Remarque** : `template.yaml` s'utilise avec le SAM CLI (`sam build` + `sam deploy`).
> Pour déployer directement avec la commande `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (cela nécessite d'empaqueter au préalable les fichiers zip Lambda et de les téléverser sur S3).

> **Remarque** : Remplacez les espaces réservés `<...>` par les valeurs réelles de votre environnement.

### 3. Confirmer l'abonnement SNS

Après le déploiement, un e-mail de confirmation d'abonnement SNS est envoyé à l'adresse e-mail que vous avez indiquée.

> **Remarque** : Si vous omettez `S3AccessPointName`, la politique IAM devient uniquement basée sur l'Alias, ce qui peut provoquer une erreur `AccessDenied`. Il est recommandé de le spécifier dans un environnement de production. Pour plus de détails, consultez le [Guide de dépannage](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー).

## Liste des paramètres de configuration

| Paramètre | Description | Valeur par défaut | Requis |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx for ONTAP S3 AP Alias (pour l'entrée) | — | ✅ |
| `S3AccessPointName` | Nom du S3 AP (pour l'octroi d'autorisations IAM basé sur l'ARN ; basé uniquement sur l'Alias si omis) | `""` | ⚠️ Recommandé |
| `S3AccessPointOutputAlias` | FSx for ONTAP S3 AP Alias (pour la sortie) | — | ✅ |
| `OntapSecretName` | Nom du secret Secrets Manager pour les identifiants ONTAP | — | ✅ |
| `OntapManagementIp` | Adresse IP de gestion du cluster ONTAP | — | ✅ |
| `ScheduleExpression` | Expression de planification d'EventBridge Scheduler | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | Liste des ID de sous-réseaux privés | — | ✅ |
| `NotificationEmail` | Adresse e-mail de notification SNS | — | ✅ |
| `DeadlineFarmId` | AWS Deadline Cloud Farm ID | — | ✅ |
| `DeadlineQueueId` | AWS Deadline Cloud Queue ID | — | ✅ |
| `QualityThreshold` | Seuil d'évaluation de la qualité Rekognition (0.0–100.0) | `80.0` | |
| `EnableVpcEndpoints` | Activer les Interface VPC Endpoints | `false` | |
| `EnableCloudWatchAlarms` | Activer les CloudWatch Alarms | `false` | |

## Structure des coûts

### Basé sur les requêtes (paiement à l'usage)

| Service | Unité de facturation | Estimation (100 ressources/mois) |
|---------|---------|----------------------|
| Lambda | Nombre de requêtes + temps d'exécution | ~$0.01 |
| Step Functions | Nombre de transitions d'état | Dans l'offre gratuite |
| S3 API | Nombre de requêtes | ~$0.01 |
| Rekognition | Nombre d'images | ~$0.10 |
| Deadline Cloud | Temps de rendu | Estimé séparément※ |

※ Le coût d'AWS Deadline Cloud dépend de l'échelle et de la durée des travaux de rendu.

### Toujours actif (facultatif)

| Service | Paramètre | Mensuel |
|---------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints=true` | ~$28.80 |
| CloudWatch Alarms | `EnableCloudWatchAlarms=true` | ~$0.20 |

> Dans un environnement de démonstration/PoC, vous pouvez démarrer à partir de **~$0.12/mois** avec uniquement les coûts variables (hors Deadline Cloud).

## Nettoyage

```bash
# Supprimer la pile CloudFormation
aws cloudformation delete-stack \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1

# Attendre la fin de la suppression
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1
```

> **Remarque** : La suppression de la pile peut échouer si des objets subsistent dans le bucket S3. Videz le bucket au préalable.

## Supported Regions

UC4 utilise les services suivants :

| Service | Contrainte de région |
|---------|-------------|
| Amazon Rekognition | Disponible dans presque toutes les régions |
| AWS Deadline Cloud | Disponibilité limitée par région ([Régions prises en charge par Deadline Cloud](https://docs.aws.amazon.com/general/latest/gr/deadline-cloud.html)) |
| AWS X-Ray | Disponible dans presque toutes les régions |
| CloudWatch EMF | Disponible dans presque toutes les régions |

> Pour plus de détails, consultez la [Matrice de compatibilité des régions](../docs/region-compatibility.md).

## Liens de référence

### Documentation officielle AWS

- [Aperçu de FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Streaming avec CloudFront (tutoriel officiel)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html)
- [Traitement sans serveur avec Lambda (tutoriel officiel)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Référence de l'API Deadline Cloud](https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html)
- [Rekognition DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html)

### Articles de blog AWS

- [Blog d'annonce de S3 AP](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
- [Trois modèles d'architecture sans serveur](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### Exemples GitHub

- [aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing](https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing) — Traitement Rekognition à grande échelle
- [aws-samples/dotnet-serverless-imagerecognition](https://github.com/aws-samples/dotnet-serverless-imagerecognition) — Step Functions + Rekognition
- [aws-samples/serverless-patterns](https://github.com/aws-samples/serverless-patterns) — Collection de modèles sans serveur

### Guides internes au projet

- [FlexClone Serverless Patterns (japonais)](../docs/guides/flexclone-serverless-patterns.md) — Pipeline de traitement de trames séquentielles avec FlexClone + Step Functions + S3AP, montage multiprotocole, cas d'usage sectoriels
- [FlexClone Serverless Patterns (English)](../docs/guides/flexclone-serverless-patterns-en.md) — FlexClone + Step Functions + S3AP sequential frame processing pipeline

## Environnement validé

| Élément | Valeur |
|------|-----|
| Région AWS | ap-northeast-1 (Tokyo) |
| Version de FSx for ONTAP | ONTAP 9.17.1P4D3 |
| Configuration FSx | SINGLE_AZ_1 |
| Python | 3.12 |
| Méthode de déploiement | CloudFormation (standard) |

## Architecture de placement VPC des Lambda

Sur la base des enseignements tirés de la validation, les fonctions Lambda sont réparties entre l'intérieur et l'extérieur du VPC.

**Lambda à l'intérieur du VPC** (uniquement les fonctions nécessitant l'accès à l'ONTAP REST API) :
- Discovery Lambda — S3 AP + ONTAP API

**Lambda à l'extérieur du VPC** (utilisant uniquement les API de services gérés AWS) :
- Toutes les autres fonctions Lambda

> **Raison** : L'accès aux API de services gérés AWS (Athena, Bedrock, Textract, etc.) depuis une Lambda à l'intérieur du VPC nécessite un Interface VPC Endpoint (7,20 $/mois chacun). Les fonctions Lambda à l'extérieur du VPC peuvent accéder directement aux API AWS via Internet et fonctionnent sans coût supplémentaire.

> **Remarque** : Pour les UC qui utilisent l'ONTAP REST API (UC1 Juridique et conformité), `EnableVpcEndpoints=true` est obligatoire, car les identifiants ONTAP sont récupérés via le Secrets Manager VPC Endpoint.

## Extension d'accélération du rendu FlexCache

### Aperçu

Dans les workflows de rendu VFX, les render input assets (textures, géométrie, plates) sont principalement en lecture, ce qui en fait une cible idéale pour FlexCache. En créant dynamiquement un FlexCache au démarrage du travail et en le supprimant automatiquement une fois le rendu terminé, vous pouvez concilier optimisation des coûts et amélioration des performances.

### Classification des données de rendu

| Type de données | Modèle d'accès | FlexCache applicable | Utilisation S3 AP |
|-----------|---------------|:---:|:---:|
| Textures | Lecture seule | ✅ | ⚠️ Binaire |
| Geometry/Plates | Lecture seule | ✅ | ⚠️ Binaire |
| Scene Files | Lecture seule | ✅ | ❌ |
| Render Output (EXR/PNG) | Écriture | ❌ | ✅ QC/métadonnées |
| Logs | Écriture → lecture | ❌ | ✅ Analyse |
| Cache (sim/fluid) | Lecture/écriture | ❌ | ❌ |

### Dynamic FlexCache Render Workflow

Pour plus de détails sur un workflow qui crée et supprime un FlexCache par travail, consultez :

- **[Dynamic FlexCache Render/EDA Workflow](../dynamic-flexcache-render-workflow/README.md)** — Automatisation avec Step Functions
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md) — Ferme de rendu multi-région
- [Mappage secteur / charge de travail](../docs/industry-workload-mapping.md) — Pattern E: Media/VFX Render Farm

### Bénéfices attendus

| KPI | Sans FlexCache | Avec FlexCache | Amélioration |
|-----|--------------|---------------|--------|
| Attente avant le début du rendu | 10-20 min | 2-5 min | 75% |
| Temps par trame | 15 min | 10 min | 33% |
| Transfert WAN par travail | 500GB | 50GB | 90% |
| Coût par trame | $0.50 | $0.35 | 30% |

---

## Liens vers la documentation AWS

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon CloudFront | [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) |
| Amazon Bedrock | [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Alignement sur le Well-Architected Framework

| Pilier | Alignement |
|----|------|
| Excellence opérationnelle | Traçage X-Ray, métriques EMF, surveillance de l'état des travaux |
| Sécurité | IAM à moindre privilège, CloudFront OAC, chiffrement KMS |
| Fiabilité | Step Functions Retry/Catch, porte de contrôle qualité |
| Efficacité des performances | Diffusion CDN CloudFront, traitement parallèle Lambda |
| Optimisation des coûts | Sans serveur, utilisation du cache CloudFront |
| Durabilité | Exécution à la demande, réduction de la charge d'origine via le CDN |

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
# Construction
# Prérequis : AWS SAM CLI est requis. sam build empaquette automatiquement le code et la couche partagée.
sam build

# Exécuter la Discovery Lambda en local
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

Pour plus de détails, consultez le [Démarrage rapide des tests locaux](../docs/local-testing-quick-start.md).

---

## Exemple de sortie (Output Sample)

Exemple de sortie d'un contrôle de qualité de rendu VFX :

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 48,
    "prefix": "renders/shot-042/"
  },
  "quality_check": [
    {
      "key": "renders/shot-042/frame-0001.exr",
      "resolution": "4096x2160",
      "color_space": "ACEScg",
      "quality_score": 0.94,
      "issues": [],
      "cloudfront_url": "https://d1234.cloudfront.net/delivery/shot-042/frame-0001.exr"
    }
  ],
  "delivery": {
    "total_frames": 48,
    "passed_qc": 46,
    "failed_qc": 2,
    "cloudfront_distribution": "d1234.cloudfront.net"
  }
}
```

> **Note** : Ce qui précède est un exemple de sortie ; les valeurs réelles varient selon l'environnement et les données d'entrée. Les chiffres de référence sont une base de dimensionnement (sizing reference), et non une limite de service (service limit).

---

## Governance Note

> Ce modèle fournit des conseils d'architecture technique. Il ne s'agit pas de conseils juridiques, de conformité ou réglementaires. Les organisations doivent consulter des professionnels qualifiés.

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclencheurs des S3 Access Points for FSx for ONTAP, consultez [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
