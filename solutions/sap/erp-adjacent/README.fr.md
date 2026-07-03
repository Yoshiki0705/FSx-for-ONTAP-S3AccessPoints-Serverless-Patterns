# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

Modèle serverless pour traiter les exports IDoc SAP, les fichiers déposés par HULFT, les fichiers de zone de dépôt EDI et les sorties de traitements par lots stockés sur FSx for ONTAP — accédés via S3 Access Points.

## Use Cases

> **Scope note**: Ce modèle est destiné aux zones de dépôt de fichiers adjacentes à SAP/ERP telles que les exports IDoc, les fichiers EDI, les transferts HULFT, les extractions d'audit et les sorties par lots. Il n'est pas destiné à remplacer les mécanismes d'intégration SAP certifiés ni les interfaces ERP transactionnelles. Pour l'intégration de stockage certifiée SAP, reportez-vous à la [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html).

- **Traitement des exports IDoc SAP** : analyse et synthèse des fichiers plats IDoc (ORDERS, INVOIC, DESADV)
- **Dépôt de fichiers HULFT** : traitement des fichiers transférés par HULFT/DataSpider vers FSx for ONTAP
- **Traitement EDI entrant** : gestion des documents EDI X12/EDIFACT dans les zones de dépôt
- **Sortie de traitements par lots** : analyse des sorties de traitements par lots mainframe, des sorties JCL ou des rapports planifiés
- **Extraction de données ERP** : traitement des extractions CSV/XML issues de SAP, Oracle EBS ou d'autres systèmes ERP

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions Workflow           │ │
│  │  Scheduler   │────▶│                                          │ │
│  │              │     │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Processing│─▶│ Report │ │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda   │  │ Lambda │ │ │
│                       │  └────┬─────┘  └────┬─────┘  └───┬────┘ │ │
│                       └───────┼─────────────┼─────────────┼──────┘ │
│                               │             │             │        │
│                               ▼             ▼             ▼        │
│                       ┌──────────────┐ ┌─────────┐  ┌─────────┐   │
│                       │ FSx for ONTAP│ │ Amazon  │  │  Amazon │   │
│                       │ via S3 AP    │ │ Bedrock │  │   SNS   │   │
│                       │              │ │ (Nova)  │  │         │   │
│                       │ ListObjectsV2│ │Summarize│  │ Email   │   │
│                       │ GetObject    │ │Classify │  │ Notify  │   │
│                       └──────────────┘ └─────────┘  └─────────┘   │
│                                              │                     │
│                                              ▼                     │
│                                        ┌──────────┐                │
│                                        │ S3 Output│                │
│                                        │  Bucket  │                │
│                                        └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

1. **Discovery** — Liste les fichiers sur FSx for ONTAP via S3 Access Point (`ListObjectsV2`), filtrés par préfixe
2. **Processing** — Pour chaque fichier : lit le contenu via S3 AP (`GetObject`), l'envoie à Amazon Bedrock pour synthèse/classification
3. **Report** — Génère un résumé d'exécution, l'écrit dans S3, envoie une notification SNS

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | Alias S3 AP pour le volume FSx for ONTAP | (requis) |
| `OntapSecretArn` | ARN Secrets Manager pour les identifiants ONTAP | (requis) |
| `ScheduleExpression` | Fréquence d'exécution | `rate(1 hour)` |
| `OutputBucketName` | Bucket S3 pour les résultats | (requis) |
| `NotificationEmail` | E-mail pour les alertes SNS | (requis) |
| `FilePrefix` | Préfixe de répertoire à analyser | `idoc-export/` |
| `BedrockModelId` | Modèle Bedrock pour la synthèse | `amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Nombre maximal de fichiers par exécution | `100` |

## Deployment

```bash
# Prérequis : AWS SAM CLI est requis. sam build empaquette automatiquement le code et les couches partagées.
sam build
sam deploy --guided --stack-name fsxn-s3ap-sap-erp \
  --parameter-overrides \
    S3AccessPointAlias=my-sap-s3ap-alias \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:my-secret \
    OutputBucketName=my-sap-output-bucket \
    NotificationEmail=ops-team@example.com \
    FilePrefix="idoc-export/" \
    ScheduleExpression="cron(0 */2 * * ? *)"
```

> **Remarque** : `template.yaml` s'utilise avec l'AWS SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec la commande `aws cloudformation deploy`, utilisez `template-deploy.yaml` (qui nécessite l'empaquetage préalable des fichiers zip Lambda et leur téléversement vers S3).

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc : `FilePrefix=idoc-export/`
- HULFT : `FilePrefix=hulft-landing/`
- EDI : `FilePrefix=edi-inbound/`
- Batch : `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

Modifiez `functions/processing/index.py` pour personnaliser le prompt de synthèse selon vos types de documents.

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — Liste complète des modèles d'entreprise
- [Quick Start Guide](../docs/quick-start.md) — Guide du premier déploiement
- [Deployment Profiles](../docs/deployment-profiles.md) — Options de configuration de production

---

## Estimation des coûts (approximation mensuelle)

> **Note** : Ce qui suit est une approximation pour la région ap-northeast-1 ; les coûts réels varient selon l'utilisation. Vérifiez les tarifs les plus récents avec le [AWS Pricing Calculator](https://calculator.aws/).

### Composants serverless (paiement à l'usage)

| Service | Prix unitaire | Utilisation estimée | Approximation mensuelle |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 fonctions × 100 files/jour | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/jour | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/jour | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/exécution | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/jour | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mois | ~$0.76 |

### Coût fixe (FSx for ONTAP — environnement existant supposé)

| Composant | Mensuel |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (partagé avec l'environnement existant) |
| S3 Access Point | Aucun frais supplémentaire (frais S3 API uniquement) |

### Approximation totale

| Configuration | Approximation mensuelle |
|------|---------|
| Configuration minimale (une fois par jour) | ~$5-15 |
| Configuration standard (horaire) | ~$15-50 |
| Configuration à grande échelle (haute fréquence + alarmes) | ~$50-150 |

> **Governance Caveat**: Les estimations de coûts sont des approximations, pas des valeurs garanties. Les frais réels varient selon les schémas d'utilisation, le volume de données et la région.

---

## Test local

### Vérification des Prerequisites

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
# Prérequis : AWS SAM CLI est requis. sam build empaquette automatiquement le code et les couches partagées.
sam build

# Exécuter la Discovery Lambda localement
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Avec remplacement de variables d'environnement
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

Exemple de sortie du workflow de traitement de fichiers SAP/ERP :

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 15,
    "prefix": "idoc-export/",
    "categories": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3}
  },
  "processing": [
    {
      "key": "idoc-export/ORDERS_20260523_001.idoc",
      "status": "completed",
      "category": "sap_idoc",
      "summary": "IDoc de commande client (ORDERS05). Partenaire commercial : Sample Corporation, numéro de commande : PO-2026-001, montant : 2,500,000 JPY",
      "document_type": "ORDERS05",
      "key_fields": ["BELNR", "KUNNR", "NETWR", "WAERK"]
    }
  ],
  "report": {
    "total_files": 15,
    "succeeded": 14,
    "failed": 1,
    "success_rate_pct": 93.3,
    "category_breakdown": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3},
    "report_key": "reports/sap-erp-summary-1716480000.json"
  }
}
```

> **Note** : Ce qui précède est un exemple de sortie ; les valeurs réelles varient selon l'environnement et les données d'entrée. Les chiffres de benchmark sont une sizing reference, pas une service limit.

---

## Governance Note

> Ce modèle fournit des orientations d'architecture technique. Il ne s'agit pas de conseils juridiques, de conformité ou réglementaires. Les organisations doivent consulter des professionnels qualifiés.

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement des S3 Access Points for FSx for ONTAP, consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
---

## Performance Considerations

- La capacité de débit de FSx for ONTAP est partagée entre NFS/SMB/S3AP
- La latence via le S3 Access Point entraîne une surcharge de quelques dizaines de millisecondes
- Lors du traitement d'un grand nombre de fichiers, contrôlez le degré de parallélisme avec le MaxConcurrency du Step Functions Map state
- L'augmentation de la taille mémoire Lambda améliore également la bande passante réseau

> **Note** : Les chiffres de performance de ce modèle sont une sizing reference, pas une service limit. Les performances en environnement réel varient selon la capacité de débit de FSx for ONTAP, la configuration réseau et les charges de travail concurrentes.
