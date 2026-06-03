# Gestion des Actifs Créatifs — Guide de Démonstration Catalogage et Vérification de Conformité de Marque

🌐 **Language / Langue** : [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Résumé

Cette démo présente un pipeline automatisé de catalogage d'actifs créatifs et de vérification de conformité de marque. L'analyse visuelle Rekognition combinée à la vérification de conformité Bedrock automatise le contrôle qualité de la production publicitaire.

**Message principal** : L'IA analyse automatiquement les actifs créatifs, vérifie la conformité aux directives de marque et génère des catalogues d'actifs.

**Durée estimée** : 3–5 minutes

---

## Déploiement et Validation Étape par Étape

### Step 1 : Vérification des prérequis

```bash
aws --version          # AWS CLI v2 requis
sam --version          # SAM CLI 1.x ou supérieur
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2 : Cloner le dépôt

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/adtech-creative-management
```

### Step 3 : Construction et déploiement SAM

```bash
sam build

sam deploy \
  --stack-name fsxn-adtech-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    BrandGuidelinesS3Key=brand-guidelines.json \
    ModerationConfidenceThreshold=80 \
    MaxTagsPerAsset=50 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 4 : Exécution manuelle du workflow

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 5 : Vérification des résultats

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## Liste de Vérification

| Élément | Méthode | Résultat Attendu |
|---------|---------|-----------------|
| Détection des fichiers média | Journal d'exécution Step Functions | L'étape Discovery retourne le nombre de fichiers |
| Extraction d'étiquettes | `asset-catalog.json` | Jusqu'à 50 étiquettes par actif |
| Inspection de modération | `flagged-assets.json` | Contenu problématique signalé |
| Vérification de conformité | Champ compliance_status | Conforme / non-conforme correctement déterminé |
| Alerte SNS | Vérification email | Notification uniquement en cas de violation |

---

## Nettoyage

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
