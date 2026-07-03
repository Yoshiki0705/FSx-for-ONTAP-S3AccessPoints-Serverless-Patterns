# UC26: Immobilier — Analyse d'images de propriétés / Extraction de contrats

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.fr.md) | [Guide de démo](docs/demo-guide.fr.md)

## Vue d'ensemble

Un workflow serverless qui s'appuie sur les S3 Access Points de FSx for ONTAP pour extraire des caractéristiques des images de propriétés, générer automatiquement des descriptions d'annonces, extraire les conditions des contrats de location et détecter les PII à des fins de protection de la vie privée.

## Success Metrics

### Outcome
Automatiser le traitement et l'analyse des documents afin d'améliorer l'efficacité opérationnelle et la conformité.

### Metrics
| Métrique | Cible (exemple) |
|----------|----------------|
| Précision d'extraction des caractéristiques de propriété | ≥ 85% |
| Taux de détection des PII | ≥ 95% |
| Précision d'extraction des conditions de contrat | ≥ 90% |
| Temps de génération de rapport | < 5 min / lot |
| Coût / exécution quotidienne | < $2.50 |
| Taux de revue humaine requise | > 20% (toutes les images avec PII détectées sont vérifiées) |

### Measurement Method
Historique d'exécution Step Functions, résultats d'extraction des services AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Les résultats à faible niveau de confiance nécessitent une vérification manuelle
- Les alertes Critical sont examinées par des experts du domaine
- Les rapports de synthèse périodiques sont examinés par la direction

## Architecture

Consultez le [document d'architecture](docs/architecture.fr.md) pour les diagrammes détaillés des flux de données.

## Prérequis

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données de FSx for ONTAP). Utilisez un S3 AP avec NetworkOrigin=VPC ou configurez l'accès via NAT Gateway. Pour plus de détails, voir [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Compte AWS avec les autorisations IAM appropriées
- Système de fichiers FSx for ONTAP (ONTAP 9.17.1P4D3 ou ultérieur)
- Volume avec S3 Access Point activé
- VPC, sous-réseaux privés
- Accès aux modèles Amazon Bedrock activé (Claude / Nova)
- Amazon Textract — configuration d'appel Cross-Region (us-east-1)

## Déploiement

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-real-estate \
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

> **Remarque** : `template.yaml` est destiné à être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec la commande `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3).

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution en parallèle avec MapConcurrency=10 peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch (ThroughputUtilization) de FSx for ONTAP et augmentez progressivement.

## Nettoyage

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## Estimation des coûts (mensuelle)

> **Note** : Estimations pour la région ap-northeast-1. Les coûts réels varient selon l'utilisation.

| Configuration | Estimation mensuelle |
|---------------|---------------------|
| Minimale (1x par jour) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Ce pattern fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Les informations sur les locataires figurant dans les contrats de location doivent être gérées conformément aux lois applicables sur la protection des données personnelles. Le traitement des PII apparaissant dans les images de propriétés doit également tenir compte des réglementations sur les transactions immobilières.

> **Réglementations associées** : 宅地建物取引業法 (loi sur le courtage immobilier), 個人情報保護法 (loi sur la protection des données personnelles)

---

## S3AP Compatibility

Pour les contraintes de compatibilité, le dépannage et les modèles de déclenchement des S3 Access Points for FSx for ONTAP, consultez [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
