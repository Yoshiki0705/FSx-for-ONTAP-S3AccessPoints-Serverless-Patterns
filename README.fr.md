# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Collection de modèles d'automatisation serverless par secteur d'activité, exploitant les S3 Access Points d'Amazon FSx for NetApp ONTAP.

> **Positionnement de ce dépôt** : Il s'agit d'une « implémentation de référence pour apprendre les décisions de conception ». Certains cas d'usage ont été entièrement vérifiés E2E dans un environnement AWS, tandis que les autres ont été validés par le déploiement CloudFormation, le Lambda Discovery partagé et les tests des composants principaux. L'objectif est de démontrer les décisions de conception en matière d'optimisation des coûts, de sécurité et de gestion des erreurs à travers du code concret, avec un chemin du PoC à la production.

## Article associé

Ce dépôt est le compagnon pratique de l'article suivant :

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

L'article explique le raisonnement architectural et les compromis. Ce dépôt fournit des modèles d'implémentation concrets et réutilisables.

## Présentation

Ce dépôt fournit **5 modèles sectoriels** pour le traitement serverless des données d'entreprise stockées sur FSx for NetApp ONTAP via les **S3 Access Points**.

> Dans la suite de ce document, FSx for ONTAP S3 Access Points est abrégé en **S3 AP**.

Chaque cas d'usage est autonome sous forme de template CloudFormation indépendant, avec des modules partagés (client ONTAP REST API, helper FSx, helper S3 AP) dans `shared/` pour réutilisation.

### Caractéristiques principales

- **Architecture par interrogation** : S3 AP ne prenant pas en charge `GetBucketNotificationConfiguration`, exécution périodique via EventBridge Scheduler + Step Functions
- **Séparation des modules partagés** : OntapClient / FsxHelper / S3ApHelper réutilisés dans tous les cas d'usage
- **CloudFormation / SAM Transform** : Chaque cas d'usage est un template CloudFormation autonome utilisant SAM Transform
- **Sécurité avant tout** : Vérification TLS activée par défaut, IAM à moindre privilège, chiffrement KMS
- **Optimisation des coûts** : Les ressources permanentes coûteuses (Interface VPC Endpoints, etc.) sont optionnelles

## Architecture

```mermaid
graph TB
    subgraph "Couche de planification"
        EBS[EventBridge Scheduler<br/>expressions cron/rate]
    end

    subgraph "Couche d'orchestration"
        SFN[Step Functions<br/>State Machine]
    end

    subgraph "Couche de calcul (dans le VPC)"
        DL[Discovery Lambda<br/>Détection d'objets]
        PL[Processing Lambda<br/>Traitement AI/ML]
        RL[Report Lambda<br/>Génération de rapports et notification]
    end

    subgraph "Sources de données"
        FSXN[FSx ONTAP Volume]
        S3AP[S3 Access Point]
        ONTAP_API[ONTAP REST API]
    end

    subgraph "Services AWS"
        SM[Secrets Manager]
        S3OUT[S3 Output Bucket<br/>Chiffrement SSE-KMS]
        BEDROCK[Amazon Bedrock]
        TEXTRACT[Amazon Textract]
        COMPREHEND[Amazon Comprehend]
        REKOGNITION[Amazon Rekognition]
        ATHENA[Amazon Athena]
        SNS[SNS Topic]
    end

    subgraph "VPC Endpoints (optionnels)"
        VPCE_S3[S3 Gateway EP<br/>Gratuit]
        VPCE_IF[Interface EPs<br/>Secrets Manager / FSx /<br/>CloudWatch / SNS]
    end

    EBS -->|Trigger| SFN
    SFN -->|Step 1| DL
    SFN -->|Step 2 Map| PL
    SFN -->|Step 3| RL

    DL -->|ListObjectsV2| S3AP
    DL -->|REST API| ONTAP_API
    PL -->|GetObject| S3AP
    PL -->|PutObject| S3OUT

    S3AP -.->|Exposes| FSXN

    DL --> VPCE_S3
    DL --> VPCE_IF --> SM
    RL --> SNS
```

> Le diagramme montre une configuration Lambda dans le VPC orientée production. Pour le PoC / démo, si le network origin du S3 AP est `internet`, une configuration Lambda hors VPC peut également être choisie. Voir « Guide de choix du placement Lambda » ci-dessous pour plus de détails.

### Vue d'ensemble du workflow

```
EventBridge Scheduler (exécution périodique)
  └─→ Step Functions State Machine
       ├─→ Discovery Lambda : Récupération de la liste d'objets depuis S3 AP → Génération du Manifest
       ├─→ Map State (traitement parallèle) : Traitement de chaque objet avec les services AI/ML
       └─→ Report/Notification : Génération du rapport de résultats → Notification SNS
```

## Liste des cas d'usage

| # | Répertoire | Secteur | Modèle | Services AI/ML utilisés | Statut de vérification ap-northeast-1 |
|---|------------|---------|--------|------------------------|--------------------------------------|
| UC1 | `legal-compliance/` | Juridique et conformité | Audit de serveur de fichiers et gouvernance des données | Athena, Bedrock | ✅ E2E réussi |
| UC2 | `financial-idp/` | Finance et assurance | Traitement automatisé de contrats et factures (IDP) | Textract ⚠️, Comprehend, Bedrock | ⚠️ Non dispo. à Tokyo (utiliser région compatible) |
| UC3 | `manufacturing-analytics/` | Industrie manufacturière | Analyse de journaux de capteurs IoT et d'images de contrôle qualité | Athena, Rekognition | ✅ E2E réussi |
| UC4 | `media-vfx/` | Médias | Pipeline de rendu VFX | Rekognition, Deadline Cloud | ⚠️ Configuration Deadline Cloud requise |
| UC5 | `healthcare-dicom/` | Santé | Classification automatique et anonymisation d'images DICOM | Rekognition, Comprehend Medical ⚠️ | ⚠️ Non dispo. à Tokyo (utiliser région compatible) |

> **Contraintes régionales** : Amazon Textract et Amazon Comprehend Medical ne sont pas disponibles dans ap-northeast-1 (Tokyo). Le déploiement de UC2 dans une région prise en charge comme us-east-1 est recommandé. Il en va de même pour Comprehend Medical dans UC5. Rekognition, Comprehend, Bedrock et Athena sont disponibles dans ap-northeast-1.
> 
> Référence : [Régions prises en charge par Textract](https://docs.aws.amazon.com/general/latest/gr/textract.html) | [Régions prises en charge par Comprehend Medical](https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html)

### Captures d'écran

> Les images suivantes sont des exemples capturés dans un environnement de vérification. Les informations spécifiques à l'environnement (identifiants de compte, etc.) ont été masquées.

#### Vérification du déploiement et de l'exécution de Step Functions pour les 5 UC

![Step Functions tous les workflows](docs/screenshots/masked/step-functions-all-succeeded.png)

> UC1 et UC3 ont fait l'objet d'une vérification E2E complète, tandis que UC2, UC4 et UC5 ont fait l'objet d'un déploiement CloudFormation et d'une vérification opérationnelle des composants principaux. Lors de l'utilisation de services AI/ML avec des contraintes régionales (Textract, Comprehend Medical), un appel inter-régions vers les régions prises en charge est nécessaire. Veuillez vérifier les exigences de résidence des données et de conformité.

#### Écrans des services AI/ML

##### Amazon Bedrock — Catalogue de modèles

![Catalogue de modèles Bedrock](docs/screenshots/masked/bedrock-model-catalog.png)

##### Amazon Rekognition — Détection d'étiquettes

![Détection d'étiquettes Rekognition](docs/screenshots/masked/rekognition-label-detection.png)

##### Amazon Comprehend — Détection d'entités

![Console Comprehend](docs/screenshots/masked/comprehend-console.png)

## Stack technique

| Couche | Technologie |
|--------|------------|
| Langage | Python 3.12 |
| IaC | CloudFormation (YAML) + SAM Transform |
| Calcul | AWS Lambda (Production : dans le VPC / PoC : hors VPC possible) |
| Orchestration | AWS Step Functions |
| Planification | Amazon EventBridge Scheduler |
| Stockage | FSx for ONTAP (S3 AP) + Bucket S3 de sortie (SSE-KMS) |
| Notification | Amazon SNS |
| Analytique | Amazon Athena + AWS Glue Data Catalog |
| AI/ML | Amazon Bedrock, Textract, Comprehend, Rekognition |
| Sécurité | Secrets Manager, KMS, IAM moindre privilège |
| Tests | pytest + Hypothesis (PBT), moto, cfn-lint, ruff |

## Prérequis

- **Compte AWS** : Un compte AWS valide avec les permissions IAM appropriées
- **FSx for NetApp ONTAP** : Un système de fichiers déployé
  - Version ONTAP : Une version prenant en charge les S3 Access Points (vérifié avec 9.17.1P4D3)
  - Un volume FSx for ONTAP avec un S3 Access Point associé (network origin selon le cas d'usage ; `internet` recommandé pour Athena / Glue)
- **Réseau** : VPC, sous-réseaux privés, tables de routage
- **Secrets Manager** : Pré-enregistrer les identifiants ONTAP REST API (format : `{"username":"fsxadmin","password":"..."}`)
- **Bucket S3** : Pré-créer un bucket pour les packages de déploiement Lambda (ex. : `fsxn-s3ap-deploy-<account-id>`)
- **Python 3.12+** : Pour le développement et les tests locaux
- **AWS CLI v2** : Pour le déploiement et la gestion

### Commandes de préparation

```bash
# 1. Créer le bucket S3 de déploiement
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb "s3://fsxn-s3ap-deploy-${ACCOUNT_ID}" --region $AWS_DEFAULT_REGION

# 2. Enregistrer les identifiants ONTAP dans Secrets Manager
aws secretsmanager create-secret \
  --name fsxn-ontap-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-ontap-password>"}' \
  --region $AWS_DEFAULT_REGION

# 3. Vérifier l'existence d'un S3 Gateway Endpoint (pour éviter la duplication)
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" "Name=service-name,Values=com.amazonaws.${AWS_DEFAULT_REGION}.s3" \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,State:State}' \
  --output table
# → Si des résultats existent, déployer avec EnableS3GatewayEndpoint=false
```

### Guide de choix du placement Lambda

| Usage | Placement recommandé | Raison |
|-------|---------------------|--------|
| Démo / PoC | Lambda hors VPC | Pas de VPC Endpoint nécessaire, faible coût, configuration simple |
| Production / exigences de réseau privé | Lambda dans le VPC | Secrets Manager / FSx / SNS accessibles via PrivateLink |
| UC utilisant Athena / Glue | S3 AP network origin : `internet` | Accès depuis les services gérés AWS nécessaire |

### Notes sur l'accès au S3 AP depuis Lambda dans le VPC

> **Constatations importantes confirmées lors de la vérification du déploiement UC1 (2026-05-03)**

- **L'association de la table de routage du S3 Gateway Endpoint est obligatoire** : Si vous ne spécifiez pas les ID de table de routage des sous-réseaux privés dans `RouteTableIds`, l'accès depuis Lambda dans le VPC vers S3 / S3 AP expirera
- **Vérifier la résolution DNS du VPC** : Assurez-vous que `enableDnsSupport` / `enableDnsHostnames` sont activés sur le VPC
- **L'exécution de Lambda hors VPC est recommandée pour les environnements PoC / démo** : Si le network origin du S3 AP est `internet`, Lambda hors VPC peut y accéder sans problème. Pas de VPC Endpoint nécessaire, réduisant les coûts et simplifiant la configuration
- Voir le [Guide de dépannage](docs/guides/troubleshooting-guide.md#6-lambda-vpc-内実行時の-s3-ap-タイムアウト) pour plus de détails

### Quotas de services AWS requis

| Service | Quota | Valeur recommandée |
|---------|-------|-------------------|
| Exécutions simultanées Lambda | ConcurrentExecutions | 100 ou plus |
| Exécutions Step Functions | StartExecution/sec | Par défaut (25) |
| S3 Access Point | AP par compte | Par défaut (10 000) |

## Démarrage rapide

### 1. Cloner le dépôt

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Exécuter les tests

```bash
# Tests unitaires (avec couverture)
pytest shared/tests/ --cov=shared --cov-report=term-missing -v

# Tests basés sur les propriétés
pytest shared/tests/test_properties.py -v

# Linter
ruff check .
ruff format --check .
```

### 4. Déployer un cas d'usage (exemple : UC1 Juridique et conformité)

> ⚠️ **Notes importantes sur l'impact sur les environnements existants**
>
> Veuillez vérifier les points suivants avant le déploiement :
>
> | Paramètre | Impact sur l'environnement existant | Méthode de vérification |
> |-----------|-------------------------------------|------------------------|
> | `VpcId` / `PrivateSubnetIds` | Des ENI Lambda seront créées dans le VPC/sous-réseaux spécifiés | `aws ec2 describe-network-interfaces --filters Name=group-id,Values=<sg-id>` |
> | `EnableS3GatewayEndpoint=true` | Un S3 Gateway Endpoint sera ajouté au VPC. **Définir sur `false` si un S3 Gateway Endpoint existe déjà dans le même VPC** | `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc-id>` |
> | `PrivateRouteTableIds` | Le S3 Gateway Endpoint sera associé aux tables de routage. Pas d'impact sur le routage existant | `aws ec2 describe-route-tables --route-table-ids <rtb-id>` |
> | `ScheduleExpression` | EventBridge Scheduler exécutera périodiquement Step Functions. **La planification peut être désactivée après le déploiement pour éviter les exécutions inutiles** | Console AWS → EventBridge → Schedules |
> | `NotificationEmail` | Un e-mail de confirmation d'abonnement SNS sera envoyé | Vérifier la boîte de réception |
>
> **Notes sur la suppression de la pile** :
> - La suppression échouera si des objets restent dans le bucket S3 (Athena Results). Videz-le d'abord avec `aws s3 rm s3://<bucket> --recursive`
> - Pour les buckets avec versioning activé, toutes les versions doivent être supprimées avec `aws s3api delete-objects`
> - La suppression des VPC Endpoints peut prendre 5 à 15 minutes
> - La libération des ENI Lambda peut prendre du temps, causant l'échec de la suppression du Security Group. Attendez quelques minutes et réessayez

```bash
# Définir la région (gérée via variable d'environnement)
export AWS_DEFAULT_REGION=us-east-1  # Région prenant en charge tous les services recommandée

# Empaquetage Lambda
./scripts/deploy_uc.sh legal-compliance package

# Déploiement CloudFormation
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-volume-ext-s3alias> \
    ParameterKey=S3AccessPointOutputAlias,ParameterValue=<your-output-volume-ext-s3alias> \
    ParameterKey=OntapSecretName,ParameterValue=<your-ontap-secret-name> \
    ParameterKey=OntapManagementIp,ParameterValue=<your-ontap-management-ip> \
    ParameterKey=SvmUuid,ParameterValue=<your-svm-uuid> \
    ParameterKey=VolumeUuid,ParameterValue=<your-volume-uuid> \
    ParameterKey=VpcId,ParameterValue=<your-vpc-id> \
    'ParameterKey=PrivateSubnetIds,ParameterValue=<subnet-1>,<subnet-2>' \
    'ParameterKey=PrivateRouteTableIds,ParameterValue=<rtb-1>,<rtb-2>' \
    ParameterKey=NotificationEmail,ParameterValue=<your-email@example.com> \
    ParameterKey=EnableVpcEndpoints,ParameterValue=true \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true
```

> **Note** : Remplacez les espaces réservés `<...>` par les valeurs réelles de votre environnement.
>
> **À propos de `EnableVpcEndpoints`** : Le Quick Start spécifie `true` pour assurer la connectivité depuis Lambda dans le VPC vers Secrets Manager / CloudWatch / SNS. Si vous disposez d'Interface VPC Endpoints ou d'un NAT Gateway existants, vous pouvez spécifier `false` pour réduire les coûts.
> 
> **Sélection de la région** : `us-east-1` ou `us-west-2` est recommandé là où tous les services AI/ML sont disponibles. Textract et Comprehend Medical ne sont pas disponibles dans `ap-northeast-1` (l'appel inter-régions peut être utilisé comme solution de contournement). Voir la [Matrice de compatibilité régionale](docs/region-compatibility.md) pour plus de détails.

### Environnement vérifié

| Élément | Valeur |
|---------|--------|
| Région AWS | ap-northeast-1 (Tokyo) |
| Version FSx ONTAP | ONTAP 9.17.1P4D3 |
| Configuration FSx | SINGLE_AZ_1 |
| Python | 3.12 |
| Méthode de déploiement | CloudFormation (utilisant SAM Transform) |

Le déploiement de la pile CloudFormation et la vérification opérationnelle du Discovery Lambda ont été effectués pour les 5 cas d'usage.
Voir les [Résultats de vérification](docs/verification-results.md) pour plus de détails.

## Résumé de la structure des coûts

### Estimations de coûts par environnement

| Environnement | Coût fixe/mois | Coût variable/mois | Total/mois |
|---------------|---------------|--------------------:|------------|
| Démo/PoC | ~0 $ | ~1–3 $ | **~1–3 $** |
| Production (1 UC) | ~29 $ | ~1–3 $ | **~30–32 $** |
| Production (5 UC) | ~29 $ | ~5–15 $ | **~34–44 $** |

### Classification des coûts

- **Basé sur les requêtes (paiement à l'usage)** : Lambda, Step Functions, S3 API, Textract, Comprehend, Rekognition, Bedrock, Athena — 0 $ si non utilisé
- **Permanent (coût fixe)** : Interface VPC Endpoints (~28,80 $/mois) — **Optionnel (opt-in)**

> Le Quick Start spécifie `EnableVpcEndpoints=true` pour prioriser la connectivité de Lambda dans le VPC. Pour un PoC à faible coût, envisagez d'utiliser Lambda hors VPC ou de tirer parti des NAT / Interface VPC Endpoints existants.

> Voir [docs/cost-analysis.md](docs/cost-analysis.md) pour une analyse détaillée des coûts.

### Ressources optionnelles

Les ressources permanentes coûteuses sont rendues optionnelles via les paramètres CloudFormation.

| Ressource | Paramètre | Par défaut | Coût fixe mensuel | Description |
|-----------|-----------|------------|-------------------|-------------|
| Interface VPC Endpoints | `EnableVpcEndpoints` | `false` | ~28,80 $ | Pour Secrets Manager, FSx, CloudWatch, SNS. `true` recommandé pour la production. Le Quick Start spécifie `true` pour la connectivité |
| CloudWatch Alarms | `EnableCloudWatchAlarms` | `false` | ~0,10 $/alarme | Surveillance du taux d'échec Step Functions, taux d'erreur Lambda |

> Le **S3 Gateway VPC Endpoint** n'a pas de frais horaires supplémentaires, son activation est donc recommandée pour les configurations où Lambda dans le VPC accède au S3 AP. Cependant, spécifiez `EnableS3GatewayEndpoint=false` si un S3 Gateway Endpoint existe déjà ou si Lambda est placé hors VPC pour le PoC / démo. Les frais standard pour les requêtes API S3, le transfert de données et l'utilisation des services AWS individuels s'appliquent toujours.

## Modèle de sécurité et d'autorisation

Cette solution combine **plusieurs couches d'autorisation**, chacune ayant un rôle différent :

| Couche | Rôle | Portée du contrôle |
|--------|------|-------------------|
| **IAM** | Contrôle d'accès aux services AWS et aux S3 Access Points | Rôle d'exécution Lambda, politique S3 AP |
| **S3 Access Point** | Définit les limites d'accès via les utilisateurs du système de fichiers associés au S3 AP | Politique S3 AP, network origin, utilisateurs associés |
| **Système de fichiers ONTAP** | Applique les permissions au niveau des fichiers | Permissions UNIX / ACL NTFS |
| **ONTAP REST API** | N'expose que les métadonnées et les opérations du plan de contrôle | Authentification Secrets Manager + TLS |

**Considérations de conception importantes** :

- L'API S3 n'expose pas les ACL au niveau des fichiers. Les informations de permissions de fichiers ne peuvent être obtenues que **via l'ONTAP REST API** (la collecte ACL de UC1 utilise ce modèle)
- L'accès via S3 AP est autorisé côté ONTAP en tant qu'utilisateur du système de fichiers UNIX / Windows associé au S3 AP, après avoir été autorisé par les politiques IAM / S3 AP
- Les identifiants ONTAP REST API sont gérés dans Secrets Manager et ne sont pas stockés dans les variables d'environnement Lambda

## Matrice de compatibilité

| Élément | Valeur / Détails de vérification |
|---------|--------------------------------|
| Version ONTAP | Vérifié avec 9.17.1P4D3 (une version prenant en charge les S3 Access Points est requise) |
| Région vérifiée | ap-northeast-1 (Tokyo) |
| Région recommandée | us-east-1 / us-west-2 (lors de l'utilisation de tous les services AI/ML) |
| Version Python | 3.12+ |
| CloudFormation Transform | AWS::Serverless-2016-10-31 |
| Style de sécurité du volume vérifié | UNIX, NTFS |

### API prises en charge par FSx ONTAP S3 Access Points

Sous-ensemble d'API disponible via S3 AP :

| API | Prise en charge |
|-----|----------------|
| ListObjectsV2 | ✅ |
| GetObject | ✅ |
| PutObject | ✅ (max 5 Go) |
| HeadObject | ✅ |
| DeleteObject | ✅ |
| DeleteObjects | ✅ |
| CopyObject | ✅ (même AP, même région) |
| GetObjectAttributes | ✅ |
| GetObjectTagging / PutObjectTagging | ✅ |
| CreateMultipartUpload | ✅ |
| UploadPart / UploadPartCopy | ✅ |
| CompleteMultipartUpload | ✅ |
| AbortMultipartUpload | ✅ |
| ListParts / ListMultipartUploads | ✅ |
| HeadBucket / GetBucketLocation | ✅ |
| GetBucketNotificationConfiguration | ❌ (Non pris en charge → raison de la conception par interrogation) |
| Presign | ❌ |

### Contraintes de network origin des S3 Access Points

| Network origin | Lambda (hors VPC) | Lambda (dans le VPC) | Athena / Glue | UC recommandés |
|---------------|-------------------|---------------------|--------------|----------------|
| **internet** | ✅ | ✅ (via S3 Gateway EP) | ✅ | UC1, UC3 (utilise Athena) |
| **VPC** | ❌ | ✅ (S3 Gateway EP requis) | ❌ | UC2, UC4, UC5 (sans Athena) |

> **Important** : Athena / Glue accèdent depuis l'infrastructure gérée AWS, ils ne peuvent donc pas accéder aux S3 AP avec un origin VPC. UC1 (Juridique) et UC3 (Industrie) utilisent Athena, le S3 AP doit donc être créé avec un network origin **internet**.

### Limitations du S3 AP

- **Taille maximale PutObject** : 5 Go. Les API multipart upload sont prises en charge, mais vérifiez la faisabilité du téléchargement pour les objets dépassant 5 Go au cas par cas.
- **Chiffrement** : SSE-FSX uniquement (FSx gère de manière transparente, pas de paramètre ServerSideEncryption nécessaire)
- **ACL** : Seul `bucket-owner-full-control` est pris en charge
- **Fonctionnalités non prises en charge** : Object Versioning, Object Lock, Object Lifecycle, Static Website Hosting, Requester Pays, Presigned URL

## Documentation

Les guides détaillés et les captures d'écran sont stockés dans le répertoire `docs/`.

| Document | Description |
|----------|-------------|
| [docs/guides/deployment-guide.md](docs/guides/deployment-guide.md) | Guide de déploiement (vérification des prérequis → préparation des paramètres → déploiement → vérification) |
| [docs/guides/operations-guide.md](docs/guides/operations-guide.md) | Guide d'exploitation (modifications de planification, exécution manuelle, revue des journaux, réponse aux alarmes) |
| [docs/guides/troubleshooting-guide.md](docs/guides/troubleshooting-guide.md) | Dépannage (AccessDenied, VPC Endpoint, timeout ONTAP, Athena) |
| [docs/cost-analysis.md](docs/cost-analysis.md) | Analyse de la structure des coûts |
| [docs/references.md](docs/references.md) | Liens de référence |
| [docs/extension-patterns.md](docs/extension-patterns.md) | Guide des modèles d'extension |
| [docs/region-compatibility.md](docs/region-compatibility.md) | Disponibilité des services AI/ML par région AWS |
| [docs/article-draft.md](docs/article-draft.md) | Brouillon original de l'article dev.to (voir Articles associés en haut du README pour la version publiée) |
| [docs/verification-results.md](docs/verification-results.md) | Résultats de vérification en environnement AWS |
| [docs/screenshots/](docs/screenshots/README.md) | Captures d'écran de la console AWS (masquées) |

## Structure des répertoires

```
fsxn-s3ap-serverless-patterns/
├── README.md                          # Ce fichier
├── LICENSE                            # MIT License
├── requirements.txt                   # Dépendances de production
├── requirements-dev.txt               # Dépendances de développement
├── shared/                            # Modules partagés
│   ├── __init__.py
│   ├── ontap_client.py               # Client ONTAP REST API
│   ├── fsx_helper.py                 # Helper AWS FSx API
│   ├── s3ap_helper.py                # Helper S3 Access Point
│   ├── exceptions.py                 # Exceptions partagées et gestionnaire d'erreurs
│   ├── discovery_handler.py          # Template Lambda Discovery partagé
│   ├── cfn/                          # Extraits CloudFormation
│   └── tests/                        # Tests unitaires et tests de propriétés
├── legal-compliance/                  # UC1 : Juridique et conformité
├── financial-idp/                     # UC2 : Finance et assurance
├── manufacturing-analytics/           # UC3 : Industrie manufacturière
├── media-vfx/                         # UC4 : Médias
├── healthcare-dicom/                  # UC5 : Santé
├── scripts/                           # Scripts de vérification et déploiement
│   ├── deploy_uc.sh                  # Script de déploiement UC (générique)
│   ├── verify_shared_modules.py      # Vérification des modules partagés en environnement AWS
│   └── verify_cfn_templates.sh       # Vérification des templates CloudFormation
├── .github/workflows/                 # CI/CD (lint, test)
└── docs/                              # Documentation
    ├── guides/                        # Guides opérationnels
    │   ├── deployment-guide.md       # Guide de déploiement
    │   ├── operations-guide.md       # Guide d'exploitation
    │   └── troubleshooting-guide.md  # Dépannage
    ├── screenshots/                   # Captures d'écran de la console AWS
    ├── cost-analysis.md               # Analyse de la structure des coûts
    ├── references.md                  # Liens de référence
    ├── extension-patterns.md          # Guide des modèles d'extension
    ├── region-compatibility.md        # Matrice de compatibilité régionale
    ├── verification-results.md        # Résultats de vérification
    └── article-draft.md               # Brouillon original de l'article dev.to
```

## Modules partagés (shared/)

| Module | Description |
|--------|-------------|
| `ontap_client.py` | Client ONTAP REST API (authentification Secrets Manager, urllib3, TLS, retry) |
| `fsx_helper.py` | AWS FSx API + récupération des métriques CloudWatch |
| `s3ap_helper.py` | Helper S3 Access Point (pagination, filtre par suffixe) |
| `exceptions.py` | Classes d'exceptions partagées, décorateur `lambda_error_handler` |
| `discovery_handler.py` | Template Lambda Discovery partagé (génération de Manifest) |

## Développement

### Exécution des tests

```bash
# Tous les tests
pytest shared/tests/ -v

# Avec couverture
pytest shared/tests/ --cov=shared --cov-report=term-missing --cov-fail-under=80 -v

# Tests basés sur les propriétés uniquement
pytest shared/tests/test_properties.py -v
```

### Linter

```bash
# Linter Python
ruff check .
ruff format --check .

# Vérification des templates CloudFormation
cfn-lint */template.yaml */template-deploy.yaml
```

## Quand utiliser / Quand ne pas utiliser cette collection de modèles

### Quand utiliser

- Vous souhaitez traiter de manière serverless des données NAS existantes sur FSx for ONTAP sans les déplacer
- Vous souhaitez lister les fichiers et effectuer un prétraitement depuis Lambda sans montage NFS / SMB
- Vous souhaitez apprendre la séparation des responsabilités entre S3 Access Points et ONTAP REST API
- Vous souhaitez valider rapidement des modèles de traitement AI / ML sectoriels en tant que PoC
- La conception par interrogation avec EventBridge Scheduler + Step Functions est acceptable

### Quand ne pas utiliser

- Le traitement en temps réel des événements de modification de fichiers est requis (S3 Event Notification non pris en charge)
- Une compatibilité complète avec les buckets S3 comme les Presigned URLs est nécessaire
- Vous disposez déjà d'une infrastructure batch permanente basée sur EC2 / ECS et le montage NFS est acceptable
- Les données de fichiers existent déjà dans des buckets S3 standard et peuvent être traitées avec les notifications d'événements S3

## Considérations supplémentaires pour le déploiement en production

Ce dépôt inclut des décisions de conception visant le déploiement en production, mais veuillez considérer les points suivants pour les environnements de production réels.

- Alignement avec les IAM / SCP / Permission Boundary de l'organisation
- Revue des politiques S3 AP et des permissions utilisateur côté ONTAP
- Activation des journaux d'audit et d'exécution pour Lambda / Step Functions / Bedrock / Textract, etc. (CloudTrail / CloudWatch Logs)
- Intégration CloudWatch Alarms / SNS / Incident Management (`EnableCloudWatchAlarms=true`)
- Exigences de conformité spécifiques au secteur telles que la classification des données, les informations personnelles et les informations médicales
- Vérification de la résidence des données pour les contraintes régionales et les appels inter-régions
- Période de rétention de l'historique d'exécution Step Functions et paramètres de niveau de journalisation
- Paramètres Lambda Reserved Concurrency / Provisioned Concurrency

## Contribution

Les Issues et Pull Requests sont les bienvenues. Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour plus de détails.

## Licence

MIT License — Voir [LICENSE](LICENSE) pour plus de détails.
