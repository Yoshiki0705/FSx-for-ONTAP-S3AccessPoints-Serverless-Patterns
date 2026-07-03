🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

# Event-Driven Prototype (prototype événementiel)

## Vue d'ensemble

Ce prototype est une implémentation de référence d'un pipeline de traitement
de fichiers événementiel qui anticipe la future fonctionnalité de notification
native de FSx for ONTAP S3 Access Points (FSx for ONTAP S3 AP).

Il utilise les Event Notifications d'un compartiment S3 ordinaire pour
simuler le comportement de la future notification native de FSx for ONTAP S3 AP.

## Architecture

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge activé)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (marquage d'image + génération de métadonnées)
          → Latency Reporter Lambda (sortie des métriques EMF)
```

## Correspondance avec la future prise en charge de FSx for ONTAP S3 AP

| Prototype actuel | Futur FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| Source d'événement `aws.s3` | Source d'événement `aws.fsx` (prévue) |
| Filtrage par nom de compartiment S3 | Filtrage par alias S3 AP |
| Lecture via S3 GetObject | Lecture via S3 AP |

## Modifications requises (lors de la prise en charge des notifications natives)

Modifications requises lorsque FSx for ONTAP S3 AP prendra en charge les notifications natives:

### 1. Modifications du modèle

```yaml
# Avant (prototype)
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# Après (FSx for ONTAP S3 AP)
# Supprimer la ressource S3 Bucket et référencer le FSx for ONTAP S3 AP existant
# Mettre à jour le filtre de source de l'EventBridge Rule
```

### 2. Modifications de la règle EventBridge

```json
// Avant
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// Après (prévue)
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Modifications des variables d'environnement Lambda

```yaml
# Avant
SOURCE_BUCKET: !Ref SourceBucket

# Après
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Modifications du code Lambda

```python
# Avant (prototype)
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# Après (FSx for ONTAP S3 AP)
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## Étapes de déploiement

### Prérequis

- AWS CLI configuré
- Python 3.12
- Compartiment S3 pour le package de déploiement Lambda

### Déploiement

```bash
# 1. Compiler et téléverser le package Lambda
# (omis: automatisé par le pipeline CI/CD)

# 2. Déployer la pile SAM
# Prérequis: AWS SAM CLI est requis. sam build empaquette automatiquement le code et les couches partagées.
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. Téléverser un fichier de test
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### Exécution des tests

```bash
# Tests unitaires
pytest event-driven-prototype/tests/ -v

# Test de comparaison de latence (après le déploiement)
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## Structure des répertoires

```
event-driven-prototype/
├── template-deploy.yaml          # Modèle CloudFormation
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # Lambda de traitement d'événement (compatible UC11)
│   └── latency_reporter/
│       └── handler.py            # Lambda de mesure de latence
├── tests/
│   ├── test_event_processor.py   # Tests unitaires du traitement d'événement
│   ├── test_latency_reporter.py  # Tests unitaires de la mesure de latence
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # Ce document
```

## Métriques

Les métriques suivantes sont émises au format CloudWatch EMF:

| Nom de la métrique | Unité | Description |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | Occurrence de l'événement → début du traitement |
| `EndToEndDuration` | Milliseconds | Occurrence de l'événement → fin du traitement |
| `ProcessingDuration` | Milliseconds | Durée d'exécution du traitement |
| `EventVolumePerMinute` | Count | Nombre d'événements traités par minute |

## Documents connexes

- [Conception de l'architecture événementielle](../docs/event-driven/architecture-design.md)
- [Guide de migration](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
