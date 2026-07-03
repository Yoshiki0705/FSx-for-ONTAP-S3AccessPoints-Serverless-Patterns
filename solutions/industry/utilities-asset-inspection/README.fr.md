# UC25 : Énergie et services publics — Inspection d'images par drone / Détection d'anomalies SCADA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Aperçu

Un workflow serverless exploitant FSx for ONTAP S3 Access Points pour détecter les défauts d'équipement à partir d'images d'inspection par drone des installations de transport d'électricité, identifier les anomalies dans les journaux chronologiques SCADA et analyser les points chauds des images thermiques FLIR.

## Success Metrics

### Outcome
Automatiser le traitement et l'analyse des documents afin d'améliorer l'efficacité opérationnelle et la conformité.

### Metrics
| Métrique | Cible (exemple) |
|-----------|------------|
| Taux de détection des défauts | ≥ 85% |
| Taux de faux positifs des anomalies SCADA | < 10% |
| Précision de détection des points chauds thermiques | ≥ 90% |
| Temps de génération du rapport | < 5 min / lot |
| Coût / exécution quotidienne | < $3.00 |
| Taux de revue humaine requise | > 30% (toutes les détections de gravité Critical sont revues) |

### Measurement Method
Historique d'exécution Step Functions, résultats d'extraction des services AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Les résultats à faible confiance nécessitent une vérification manuelle
- Les alertes Critical sont examinées par des experts du domaine
- Les rapports de synthèse périodiques sont examinés par la direction

## Architecture

Consultez le [document d'architecture](docs/architecture.fr.md) pour les diagrammes de flux de données détaillés.

## Prérequis

> **Note S3 AP NetworkOrigin** : La fonction Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, il n'est pas accessible via le S3 Gateway VPC Endpoint (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP avec NetworkOrigin=VPC ou configurez un accès via NAT Gateway. Voir [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Compte AWS avec les autorisations IAM appropriées
- Système de fichiers FSx for ONTAP (ONTAP 9.17.1P4D3 ou version ultérieure)
- S3 Access Point activé sur le volume
- VPC avec sous-réseaux privés
- Accès aux modèles Amazon Bedrock activé (Claude / Nova)

## Déploiement

```bash
# Prérequis : AWS SAM CLI requis. 'sam build' empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
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

> **Note** : `template.yaml` est conçu pour être utilisé avec la SAM CLI (`sam build` + `sam deploy`).
> Pour déployer directement avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite un pré-empaquetage des fichiers zip Lambda et leur téléversement vers un bucket S3).

## ⚠️ Considérations sur les performances

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. Exécuter MapConcurrency=10 en parallèle peut affecter d'autres charges de travail sur le même volume.
- Pour le traitement par lots de volumes importants, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch de FSx for ONTAP (ThroughputUtilization) et augmentez progressivement.

## Nettoyage

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## Estimation des coûts (mensuelle)

> **Remarque** : Estimations pour ap-northeast-1. Les coûts réels varient selon l'utilisation.

| Configuration | Estimation mensuelle |
|------|---------|
| Minimale (1x par jour) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Ce pattern fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Les données SCADA sont des informations d'infrastructure critique. La gestion des droits d'accès et la conservation des journaux d'audit doivent se conformer aux réglementations applicables sur les activités électriques et aux directives de protection des infrastructures critiques.

> **Réglementations associées** : Loi sur les activités électriques (電気事業法), Normes techniques des installations électriques (電気設備技術基準)

---

## S3AP Compatibility

Consultez [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement de FSx for ONTAP S3 Access Points.
