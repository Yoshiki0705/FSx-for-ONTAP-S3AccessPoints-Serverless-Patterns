# UC28: Chimie et matériaux — Extraction des dangers SDS / Validation GHS

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Schéma d'architecture](docs/architecture.fr.md) | [Guide de démo](docs/demo-guide.fr.md)

## Aperçu

Un workflow serverless exploitant FSx for ONTAP S3 Access Points pour extraire les classifications de dangers et les précautions de manipulation des fiches de données de sécurité (SDS), valider l'exhaustivité des sections obligatoires du GHS et extraire les données expérimentales à partir des images de cahiers de laboratoire.

## Success Metrics

### Outcome
Automatiser le traitement et l'analyse des documents afin d'améliorer l'efficacité opérationnelle et la conformité.

### Metrics
| Métrique | Cible (exemple) |
|-----------|------------|
| Exhaustivité de la validation des sections GHS | 100 % (8 sections obligatoires vérifiées) |
| Taux de détection des SDS expirées | 100 % |
| Précision d'extraction de la classification des dangers | ≥ 90 % |
| Temps de génération du rapport | < 5 min / lot |
| Coût / exécution quotidienne | < $2.50 |
| Taux de Human Review requis | > 25 % (toutes les alertes de priorité Critical vérifiées) |

### Measurement Method
Historique d'exécution Step Functions, résultats d'extraction des services AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Les résultats à faible confiance nécessitent une vérification manuelle
- Les alertes Critical sont examinées par des experts du domaine
- Les rapports de synthèse périodiques sont examinés par la direction

## Architecture

Consultez le [document d'architecture](docs/architecture.fr.md) pour des schémas de flux de données détaillés.

## Prérequis

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP avec NetworkOrigin=VPC ou configurez l'accès via NAT Gateway. Voir [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Compte AWS avec les autorisations IAM appropriées
- Système de fichiers FSx for ONTAP (ONTAP 9.17.1P4D3 ou version ultérieure)
- S3 Access Point activé sur le volume
- VPC, sous-réseaux privés
- Accès aux modèles Amazon Bedrock activé (Claude / Nova)
- Amazon Textract — configuration d'appel Cross-Region (us-east-1)

## Déploiement

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-chemical-sds \
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

> **Remarque** : `template.yaml` est conçu pour être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3).

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution avec MapConcurrency=10 en parallèle peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch de FSx for ONTAP (ThroughputUtilization) et augmentez progressivement.

## Nettoyage

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds --region ap-northeast-1
```

## Estimation des coûts (mensuelle)

> **Remarque** : Estimation pour la région ap-northeast-1. Les coûts réels varient selon l'utilisation.

| Configuration | Estimation mensuelle |
|------|---------|
| Configuration minimale (1 fois par jour) | ~$8-20 |
| Configuration standard | ~$20-50 |

---

## Governance Note

> Ce modèle fournit des orientations d'architecture technique. Il ne constitue pas un conseil juridique, de conformité ou réglementaire. Le traitement des informations sur les substances chimiques contenues dans les SDS doit respecter les lois applicables en matière de gestion des produits chimiques et de sécurité au travail. La détermination finale de la classification GHS doit être effectuée par des professionnels qualifiés de la sécurité chimique.

> **Réglementations connexes** : Loi sur la promotion de la gestion des substances chimiques (loi PRTR), Loi sur la sécurité et la santé au travail, Loi sur les services d'incendie

---

## S3AP Compatibility

Consultez [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement de FSx for ONTAP S3 Access Points.
