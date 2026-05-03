# FSxN S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Collection de modèles d'automatisation serverless par secteur d'activité, exploitant les S3 Access Points d'Amazon FSx for NetApp ONTAP.

## Présentation

Ce dépôt fournit **5 modèles sectoriels** pour le traitement serverless des données d'entreprise stockées sur FSx for NetApp ONTAP via les **S3 Access Points**.

Chaque cas d'usage est autonome sous forme de template CloudFormation indépendant, avec des modules partagés (client ONTAP REST API, helper FSx, helper S3 AP) dans `shared/`.

### Caractéristiques principales

- **Architecture par interrogation** : EventBridge Scheduler + Step Functions (FSx ONTAP S3 AP ne prend pas en charge `GetBucketNotificationConfiguration`)
- **Séparation des modules partagés** : OntapClient / FsxHelper / S3ApHelper réutilisés dans tous les cas d'usage
- **CloudFormation natif** : Chaque cas d'usage est un template CloudFormation autonome
- **Sécurité avant tout** : Vérification TLS activée par défaut, IAM à moindre privilège, chiffrement KMS
- **Optimisation des coûts** : Les ressources permanentes coûteuses (VPC Endpoints, etc.) sont optionnelles

## Cas d'usage

| # | Répertoire | Secteur | Modèle | Services AI/ML | Compatibilité régionale |
|---|------------|---------|--------|----------------|------------------------|
| UC1 | `legal-compliance/` | Juridique et conformité | Audit de serveur de fichiers et gouvernance des données | Athena, Bedrock | Toutes les régions |
| UC2 | `financial-idp/` | Services financiers | Traitement de contrats/factures (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract : inter-régions |
| UC3 | `manufacturing-analytics/` | Industrie manufacturière | Journaux de capteurs IoT et contrôle qualité | Athena, Rekognition | Toutes les régions |
| UC4 | `media-vfx/` | Médias et divertissement | Pipeline de rendu VFX | Rekognition, Deadline Cloud | Régions Deadline Cloud |
| UC5 | `healthcare-dicom/` | Santé | Classification d'images DICOM et anonymisation | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical : inter-régions |

> **Contraintes régionales** : Amazon Textract et Amazon Comprehend Medical ne sont pas disponibles dans toutes les régions (ex. : ap-northeast-1). L'appel inter-régions est pris en charge via les paramètres `TEXTRACT_REGION` et `COMPREHEND_MEDICAL_REGION`. Voir la [Matrice de compatibilité régionale](docs/region-compatibility.md).

## Démarrage rapide

### Prérequis

- AWS CLI v2
- Python 3.12+
- FSx for NetApp ONTAP avec S3 Access Points activés
- Identifiants ONTAP dans AWS Secrets Manager

### Déploiement

```bash
# Définir la région
export AWS_DEFAULT_REGION=us-east-1

# Empaqueter les fonctions Lambda
./scripts/deploy_uc.sh legal-compliance package

# Déployer la pile CloudFormation
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ...
```

## Documentation

| Document | Description |
|----------|-------------|
| [Guide de déploiement](docs/guides/deployment-guide.md) | Instructions de déploiement étape par étape |
| [Guide d'exploitation](docs/guides/operations-guide.md) | Procédures de surveillance et d'exploitation |
| [Guide de dépannage](docs/guides/troubleshooting-guide.md) | Problèmes courants et solutions |
| [Analyse des coûts](docs/cost-analysis.md) | Structure des coûts et optimisation |
| [Compatibilité régionale](docs/region-compatibility.md) | Disponibilité des services par région |
| [Modèles d'extension](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [Résultats de vérification](docs/verification-results.md) | Résultats des tests en environnement AWS |

## Stack technique

| Couche | Technologie |
|--------|------------|
| Langage | Python 3.12 |
| IaC | CloudFormation (YAML) |
| Calcul | AWS Lambda |
| Orchestration | AWS Step Functions |
| Planification | Amazon EventBridge Scheduler |
| Stockage | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| Sécurité | Secrets Manager, KMS, IAM moindre privilège |
| Tests | pytest + Hypothesis (PBT) |

## Licence

MIT License. Voir [LICENSE](LICENSE) pour plus de détails.
