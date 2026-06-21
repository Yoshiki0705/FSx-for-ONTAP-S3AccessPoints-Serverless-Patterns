# UC21 : Agriculture et Alimentation — Analyse d'imagerie aérienne / Gestion des documents de traçabilité

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation** : [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Présentation

Workflow serverless exploitant FSx for ONTAP S3 Access Points pour analyser les images aériennes de terres agricoles et automatiser l'extraction de données structurées des documents de traçabilité.

## Success Metrics

| Métrique | Objectif |
|----------|----------|
| Précision détection anomalies cultures | ≥ 70% |
| Taux de classification traçabilité | ≥ 80% |
| Taux de vérification géolocalisation | ≥ 90% |

## Note de gouvernance

> Ce modèle fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique ou réglementaire.

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution avec MapConcurrency=10 en parallèle peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch (ThroughputUtilization) et augmentez progressivement.

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP VPC-origin ou configurez l'accès via NAT Gateway. Voir [Notes de compatibilité S3AP](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
