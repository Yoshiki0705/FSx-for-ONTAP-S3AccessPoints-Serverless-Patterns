# UC22 : Transport et Ferroviaire — Analyse d'images d'inspection / Gestion des rapports de maintenance

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation** : [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Présentation

Workflow serverless détectant les indicateurs de détérioration (fissures, rouille, déplacement) dans les images d'inspection d'infrastructure ferroviaire. **Infrastructure critique pour la sécurité : seuil de détection plus bas + révision humaine obligatoire.**

## Success Metrics

| Métrique | Objectif |
|----------|----------|
| Taux de détection (standard) | >= 85% |
| Taux de détection (critique) | >= 95% |
| Précision classification sévérité | >= 80% |
| Taux faux négatifs (critique) | < 5% |

## Note de gouvernance

> Ce modèle fournit des conseils d'architecture technique. Les résultats de détection AI ne sont pas des jugements finals — la confirmation par un ingénieur qualifié est obligatoire.

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution avec MapConcurrency=10 en parallèle peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch (ThroughputUtilization) et augmentez progressivement.

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP VPC-origin ou configurez l'accès via NAT Gateway. Voir [Notes de compatibilité S3AP](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
