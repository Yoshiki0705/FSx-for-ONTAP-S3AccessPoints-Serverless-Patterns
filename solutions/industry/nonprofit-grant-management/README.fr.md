# UC24: Organisations à but non lucratif — Classification des demandes de subvention / Correspondance des résultats

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.fr.md) | [Guide de démo](docs/demo-guide.fr.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to automatically classify grant applications, extract applicant information and budgets, and match outcome metrics from activity reports against original grant objectives.

## Success Metrics

| Metric | Target |
|--------|--------|
| Grant application classification accuracy | ≥ 85% |
| Outcome achievement measurement accuracy | ≥ 80% |
| Application data extraction rate | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $1.50 |
| Human review required rate | > 25% (low-confidence classifications) |

## Architecture

See [Architecture Document](docs/architecture.fr.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled
- Amazon Textract — Cross-Region (us-east-1)

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP VPC-origin ou configurez l'accès via NAT Gateway. Voir [Notes de compatibilité S3AP](../docs/s3ap-compatibility-notes.md).

## Deployment

```bash
aws cloudformation deploy \
  --template-file nonprofit-grant-management/template.yaml \
  --stack-name fsxn-nonprofit-grants \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```


## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution avec MapConcurrency=10 en parallèle peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch (ThroughputUtilization) et augmentez progressivement.

## Cleanup

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. Handling of personal and organizational information in grant applications must comply with each funding agency's regulations and applicable privacy laws.

> **Related Regulations**: NPO 法, 公益法人認定法 (Public Interest Corporation Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
