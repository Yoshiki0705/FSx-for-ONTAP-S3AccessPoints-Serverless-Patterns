# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

## Aperçu

Un modèle serverless qui collecte et analyse de manière non intrusive les journaux et les événements de basculement d'un cluster à haute disponibilité (HA) construit avec **SIOS LifeKeeper**, via les S3 Access Points d'**Amazon FSx for NetApp ONTAP**.

L'**analyse des causes racines (Root Cause Analysis)** et le **scoring de santé du cluster** alimentés par Amazon Bedrock (Nova Pro) permettent une identification rapide des causes de basculement et une détection précoce des signes avant-coureurs.

---

## Scénario cible

Dans les environnements d'entreprise, les applications SAP, Oracle et les applications métier critiques sont protégées en HA par SIOS LifeKeeper, et FSx for ONTAP Multi-AZ est utilisé comme stockage partagé.

**Défis** :
- L'identification de la cause racine lors d'un basculement prend du temps
- L'analyse des journaux LifeKeeper implique beaucoup de travail manuel et dépend de l'expertise individuelle
- L'ajout d'un agent de surveillance sur les nœuds du cluster HA augmente le nombre de points de défaillance
- La distinction entre les défaillances de la couche de stockage (FSx for ONTAP) et de la couche applicative (LifeKeeper) est difficile

**Solution** :
Utiliser les FSx for ONTAP S3 Access Points pour traiter les journaux écrits par LifeKeeper de manière **non intrusive** via un pipeline d'analyse serverless. L'analyse automatisée pilotée par l'IA réduit la charge opérationnelle.

---

## Combinaison SIOS LifeKeeper + FSx for ONTAP

### Positionnement dans l'architecture

| Couche | Responsabilité | Périmètre HA |
|---------|------|------------|
| Stockage | FSx for ONTAP Multi-AZ | Disponibilité des données, redondance AZ, basculement automatique |
| Application | SIOS LifeKeeper | Contrôle des VIP, surveillance des services, reprise automatique |
| Analyse (ce modèle) | S3 AP + Serverless + Bedrock | Analyse de journaux non intrusive, analyse IA des causes racines |

### Qu'est-ce que SIOS LifeKeeper

Un logiciel de clustering HA pour Linux/Windows fourni par SIOS Technology. Il assure la haute disponibilité des applications critiques sur AWS.

**Principales caractéristiques** :
- Recovery Kits sensibles aux applications (surveillance directe de SAP S/4HANA, Oracle, NFS, IP, etc.)
- Basculement inter-AZ (2 AZ au sein d'une même région)
- Gestion des VIP (Elastic IP / Secondary IP)
- Prévention du split-brain grâce à des chemins de communication redondants
- Fourni officiellement en tant qu'AWS Partner Solution

**Références** : Astro Malaysia a adopté SIOS LifeKeeper dans un environnement SAP + Oracle on AWS et a atteint une disponibilité de 99,99 %.

### Prise en charge du disque partagé FSx for ONTAP (V10 et versions ultérieures)

À partir de LifeKeeper V10.0.1, FSx for ONTAP peut être protégé directement en tant que disque partagé. Auparavant, seul DataKeeper (réplication au niveau bloc) était disponible ; l'ajout d'une configuration à disque partagé permet une configuration HA plus simple.

| Protocole | Recovery Kit requis | Remarques |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | Requis lors de l'utilisation de FSx for ONTAP sur AWS |
| NFS | NAS Recovery Kit | Configuration standard de disque partagé NFS |

> Un article de validation de SIOS bcblog (2026-05-08) confirme que le basculement (switchover) fonctionne correctement dans une configuration RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS).

### Valeur apportée par FSx for ONTAP

- **Stockage partagé Multi-AZ** : accessible depuis les deux nœuds LifeKeeper via NFS/iSCSI
- **Basculement automatique du stockage** : gère automatiquement les défaillances AZ de la couche de stockage
- **Snapshot** : préserve l'état des données avant et après le basculement
- **S3 Access Points** : chemin d'accès aux données non intrusif pour l'analyse des journaux
- **Multiprotocole** : fournit SMB + NFS + iSCSI + S3 API depuis un seul volume, évitant la duplication des données
- **Cloud-native** : peut être utilisé directement depuis l'AWS Management Console (aucune licence distincte requise)

> « Le grand avantage est que, au lieu de copier les données vers S3 pour les utiliser, on peut exploiter les données sur FSx for ONTAP directement via l'API S3 » — extrait de l'[article d'interview SIOS bcblog](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### Références publiques

| Ressource | Éditeur | URL |
|------|--------|-----|
| Solution à haute disponibilité utilisant SIOS LifeKeeper et Amazon FSx for NetApp ONTAP | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| Conception à haute disponibilité avec NetApp ONTAP et LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Utilisation d'Amazon FSx for NetApp ONTAP comme disque partagé LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## Fonctionnalités

### Discovery Lambda
- Détecte les fichiers journaux LifeKeeper via FSx for ONTAP S3 AP
- Classe les journaux : événements de basculement / vérifications de santé / changements de configuration / journaux Recovery Kit
- Évalue automatiquement la gravité (CRITICAL / HIGH / MEDIUM / LOW)

### Processing Lambda
- Détecte les transitions d'état des ressources LifeKeeper (ISP→OSF, ISS→ISP, etc.)
- Analyse des causes racines via Bedrock (Nova Pro)
- Calcule un score de santé du cluster (0-100)
- Distingue les défaillances de la couche de stockage de celles de la couche applicative

### Report Lambda
- Génère des rapports de santé au format Markdown
- Envoie des alertes de basculement SNS selon les seuils de gravité
- Inclut des actions recommandées avec des commandes LifeKeeper (`lcdstatus`, vérification des chemins de communication)

---

## Déploiement

### Prérequis

- AWS SAM CLI
- Python 3.12
- Système de fichiers FSx for ONTAP + S3 Access Point (non requis lorsque DemoMode=true)
- Accès au modèle Bedrock activé (Amazon Nova Pro)

### Déploiement rapide

```bash
# Déploiement en DemoMode (aucun FSx for ONTAP requis)
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **Remarque** : `template.yaml` s'utilise avec le SAM CLI (`sam build` + `sam deploy`).
> Pour déployer directement avec la commande `aws cloudformation deploy`, utilisez `template-deploy.yaml` (cela nécessite d'empaqueter au préalable les fichiers zip Lambda et de les téléverser vers S3).

### Déploiement en production

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### Paramètres

| Paramètre | Par défaut | Description |
|-----------|-----------|------|
| S3AccessPointAlias | (requis) | Alias FSx for ONTAP S3 AP |
| DemoMode | false | Activer le mode démo |
| ScheduleExpression | rate(5 minutes) | Intervalle de surveillance |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | apac.amazon.nova-pro-v1:0 | Modèle Bedrock pour l'analyse |
| FailoverAlertSeverity | CRITICAL | Gravité minimale pour les alertes SNS |
| ClusterName | lifekeeper-cluster | Nom du cluster LifeKeeper |
| OutputDestination | STANDARD_S3 | Destination de sortie des rapports |
| LogRetentionInDays | 90 | Durée de rétention CloudWatch Logs |

---

## Tests

```bash
# Tests unitaires
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# Test de bout en bout en DemoMode
# (placez au préalable des journaux d'exemple dans le bucket S3 de démo)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Score de santé

| Score | Niveau | Signification | Action recommandée |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | Normal | Consulter les rapports périodiques |
| 70-89 | WARNING | Attention | Vérifier les chemins de communication et les E/S de stockage |
| 50-69 | DEGRADED | Dégradé | Vérifier l'état via LifeKeeper GUI/CLI, surveiller FSx for ONTAP |
| 0-49 | CRITICAL | Critique | Action immédiate. Vérifier l'état avec `lcdstatus` + CLI de gestion ONTAP |

---

## Structure des répertoires

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # Modèle SAM
├── samconfig.toml.example     # Exemple de configuration de déploiement
├── README.md                  # Ce document (japonais)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # Détection des journaux LifeKeeper
│   ├── processing/
│   │   └── handler.py         # Analyse des causes racines Bedrock
│   └── report/
│       └── handler.py         # Génération de rapports, alertes
├── statemachine/
│   └── workflow.asl.json      # Définition Step Functions
├── docs/
│   ├── architecture.md        # Détails de l'architecture
│   └── demo-guide.md          # Guide de démonstration (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # Tests unitaires
```

---

## Modèles associés

| Modèle | Relation |
|---------|--------|
| `solutions/sap/erp-adjacent/` | Traitement IDoc/par lots des environnements SAP protégés par LifeKeeper |
| `solutions/event-driven/fpolicy/` | Détection immédiate des journaux via déclenchement événementiel FPolicy |
| `solutions/flexcache/anycast-dr/` | Référence pour les configurations DR multi-régions |

---

## Governance Note

Ce modèle est conçu pour **assister la surveillance opérationnelle** des clusters HA. Points à noter :

- Les résultats de l'analyse IA constituent des **informations de référence** pour les décisions opérationnelles ; aucun contrôle de basculement automatique ni opération de reprise n'est effectué
- Les modifications de configuration LifeKeeper doivent toujours être effectuées depuis LifeKeeper GUI/CLI
- Les décisions de basculement doivent être déléguées aux mécanismes de vérification de santé propres à LifeKeeper
- Ce modèle est conçu sur le principe d'un **Human-in-the-loop**

---

## Performance Considerations

- **Intervalle de surveillance** : un intervalle de 5 minutes entraîne jusqu'à 5 minutes de délai de détection. Lorsqu'une immédiateté est requise, combinez le déclenchement événementiel FPolicy avec `TriggerMode=HYBRID`
- **Taille des journaux** : en cas de nombreux fichiers journaux, contrôlez la taille des lots avec `MaxFilesPerExecution`
- **Coût Bedrock** : dans les environnements où les basculements sont fréquents, soyez attentif aux coûts d'invocation de Bedrock. Restreignez les cibles d'analyse avec `FailoverAlertSeverity`
- **Débit S3 AP** : FSx for ONTAP S3 AP partage la bande passante de l'ensemble du système de fichiers. Envisagez des lectures basées sur Snapshot afin que d'importants volumes de lecture de journaux n'affectent pas les E/S métier

---

## License

MIT
