# UC27 : Ressources humaines — Filtrage de CV / Mode strict PII

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation** : [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Aperçu

Un flux de travail serverless qui exploite les FSx for ONTAP S3 Access Points pour extraire de manière structurée les compétences et l'expérience à partir de CV et de dossiers de carrière, et qui réalise une notation en mode strict PII excluant les caractéristiques protégées.

> **Important : Avis réglementaire**
> Ce modèle est un **flux de travail de triage et de synthèse de documents**, et non un système de décision d'embauche automatisé. Les décisions finales d'embauche doivent toujours être prises par du personnel RH qualifié. Avant toute utilisation, vous devez vérifier la conformité avec les lois du travail, les réglementations sur la confidentialité (RGPD, APPI, CCPA, etc.) et les exigences de non-discrimination de chaque pays et région. Les sorties ne doivent pas inclure de classement fondé sur des caractéristiques protégées, et les explications d'évaluation doivent reposer uniquement sur les qualifications et l'expérience liées au poste.

## Success Metrics

### Outcome
Automatiser le traitement et l'analyse des documents afin d'améliorer l'efficacité opérationnelle et de renforcer la conformité.

### Metrics
| Métrique | Cible (exemple) |
|-----------|------------|
| Taux d'extraction des données de CV | ≥ 90 % |
| Équité de la notation | Aucun biais lié aux caractéristiques protégées (âge, sexe, nationalité exclus) |
| Conformité PII | 100 % (zéro PII dans les journaux) |
| Temps de génération du rapport | < 5 min / lot |
| Coût / exécution quotidienne | < 2,00 $ |
| Taux d'obligation de Human Review | > 30 % (tous les résultats de notation vérifiés par l'équipe RH) |

### Measurement Method
Historique d'exécution Step Functions, résultats d'extraction des services AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Les résultats à faible confiance nécessitent une vérification manuelle
- Les alertes Critical sont examinées par des experts du domaine
- Les rapports de synthèse périodiques sont examinés par la direction

### Output Safeguard Requirements
- Le schéma de sortie ne doit pas inclure les champs age/gender/ethnicity/nationality
- Les explications d'évaluation doivent reposer uniquement sur les qualifications et l'expérience liées au poste
- Les caractéristiques protégées détectées doivent être supprimées avant le stockage
- Tous les résultats de recommandation doivent obligatoirement faire l'objet d'une revue humaine

## Architecture

Consultez le [document d'architecture](docs/architecture.fr.md) pour les diagrammes détaillés de flux de données.

## Prérequis

> **Note sur le NetworkOrigin du S3 AP** : la fonction Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, il ne peut pas être accédé via un S3 Gateway VPC Endpoint (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP avec NetworkOrigin=VPC, ou configurez un accès via une NAT Gateway. Pour plus de détails, consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Compte AWS avec les autorisations IAM appropriées
- Système de fichiers FSx for ONTAP (ONTAP 9.17.1P4D3 ou version ultérieure)
- Volume avec S3 Access Point activé
- VPC, sous-réseaux privés
- Accès aux modèles Amazon Bedrock activé (Claude / Nova)
- Amazon Textract — configuration d'appel Cross-Region (us-east-1)

## Déploiement

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Remarque** : `template.yaml` s'utilise avec le SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec la commande `aws cloudformation deploy`, utilisez `template-deploy.yaml` (cela nécessite le pré-empaquetage des fichiers zip Lambda et leur téléversement sur S3).

## ⚠️ Considérations sur les performances

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution d'un traitement parallèle avec MapConcurrency=10 peut affecter les autres charges de travail sur le même volume.
- Pour le traitement en masse d'un grand nombre de fichiers, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : en production, commencez avec MapConcurrency=5 et augmentez progressivement tout en surveillant les métriques CloudWatch de FSx for ONTAP (ThroughputUtilization).

## Nettoyage

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## Estimation des coûts (mensuelle)

> **Note** : estimations pour la région ap-northeast-1. Les coûts réels varient selon l'utilisation.

| Configuration | Estimation mensuelle |
|------|---------|
| Configuration minimale (1x par jour) | ~8-20 $ |
| Configuration standard | ~20-50 $ |

---

## Governance Note

> Ce modèle fournit des indications d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. L'utilisation de l'IA dans le filtrage des candidatures doit respecter la loi sur la sécurité de l'emploi et la loi sur l'égalité des chances en matière d'emploi, et doit éliminer les biais fondés sur des caractéristiques protégées (âge, sexe, nationalité, etc.). La notation par l'IA n'est qu'une information de référence ; la décision finale doit être prise par le personnel RH.

> **Réglementations connexes** : loi sur la sécurité de l'emploi, loi sur la protection des informations personnelles (APPI), loi sur les normes du travail

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclencheur des FSx for ONTAP S3 Access Points, consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
