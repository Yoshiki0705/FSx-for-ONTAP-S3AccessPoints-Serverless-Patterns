# UC24 : Organisations à but non lucratif — Classification des demandes de subvention / Correspondance des résultats

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Aperçu

Un workflow serverless qui exploite les S3 Access Points de FSx for ONTAP pour classer automatiquement les demandes de subvention, extraire les informations sur les demandeurs et les budgets, et faire correspondre les indicateurs de résultats issus des rapports d'activité aux objectifs initiaux de la subvention.

## Success Metrics

### Outcome
Automatiser le traitement et l'analyse des documents afin d'améliorer l'efficacité opérationnelle et la conformité.

### Metrics
| Indicateur | Cible (exemple) |
|-----------|------------|
| Précision de la classification des demandes de subvention | ≥ 85% |
| Précision de la mesure du degré d'atteinte des résultats | ≥ 80% |
| Taux d'extraction des données des demandes | ≥ 90% |
| Temps de génération des rapports | < 5 min / lot |
| Coût / exécution quotidienne | < $1.50 |
| Taux de Human Review requis | > 25% (résultats de classification à faible confiance) |

### Measurement Method
Historique d'exécution de Step Functions, résultats d'extraction des services IA/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Les résultats à faible confiance nécessitent une vérification manuelle
- Les alertes Critical sont examinées par des experts du domaine
- Les rapports de synthèse périodiques sont examinés par la direction

## Architecture

Consultez le [document d'architecture](docs/architecture.fr.md) pour les diagrammes détaillés de flux de données.

## Prérequis

> **Remarque sur S3 AP NetworkOrigin** : la fonction Lambda Discovery est déployée à l'intérieur d'un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, il n'est pas accessible via un S3 Gateway VPC Endpoint (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP avec NetworkOrigin=VPC ou configurez un accès via NAT Gateway. Consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Un compte AWS avec les autorisations IAM appropriées
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
  --stack-name fsxn-nonprofit-grants \
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

> **Remarque** : `template.yaml` est conçu pour être utilisé avec SAM CLI (`sam build` + `sam deploy`).
> Pour déployer directement avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite un pré-empaquetage des fichiers zip Lambda et leur téléversement vers un bucket S3).

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution en parallèle avec MapConcurrency=10 peut affecter les autres charges de travail sur le même volume.
- Pour le traitement par lots de gros volumes de fichiers, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandation : commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch de FSx for ONTAP (ThroughputUtilization) et augmentez progressivement.

## Nettoyage

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## Estimation des coûts (mensuelle)

> **Remarque** : estimations pour ap-northeast-1. Les coûts réels varient selon l'utilisation.

| Configuration | Estimation mensuelle |
|------|---------|
| Minimale (1 fois par jour) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Ce modèle fournit des orientations techniques d'architecture. Il ne constitue pas un conseil juridique, de conformité ou réglementaire. Le traitement des informations personnelles et organisationnelles contenues dans les demandes de subvention doit respecter les règles de chaque organisme de financement ainsi que les lois applicables en matière de protection des données personnelles.

> **Réglementations associées** : loi japonaise sur les OBNL (loi NPO), loi sur la certification des personnes morales d'intérêt public

---

## S3AP Compatibility

Consultez les [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement de FSx for ONTAP S3 AP.
