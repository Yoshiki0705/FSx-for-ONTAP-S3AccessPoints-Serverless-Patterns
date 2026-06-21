# UC20 : Voyage et Hôtellerie — Traitement des documents de réservation / Analyse d'images d'inspection des installations

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation** : [Architecture](docs/architecture.fr.md) | [Guide de démonstration](docs/demo-guide.fr.md)

## Présentation

Un workflow serverless exploitant FSx for ONTAP S3 Access Points pour extraire automatiquement des données structurées des documents de réservation d'hôtels (PDF, images numérisées) et générer des analyses d'état des installations et des recommandations de maintenance à partir d'images d'inspection.

### Fonctionnalités principales

- Détection automatique des documents de réservation et images d'inspection via S3 AP
- Extraction de données structurées Textract + Comprehend (nom du client, dates, type de chambre, montant)
- Support multilingue (détection de langue → indices Textract + sélection automatique du modèle Comprehend)
- Analyse de l'état des installations Rekognition (détection de dommages, score de propreté 0–100)
- Génération de recommandations de maintenance Bedrock

## Success Metrics

| Métrique | Objectif |
|----------|----------|
| Précision d'extraction des réservations | ≥ 90% |
| Taux de détection de l'état des installations | ≥ 85% |
| Couverture multilingue | ≥ 5 langues |
| Temps de génération de rapport | < 5 min / lot |
| Taux de révision humaine | > 15% |

## Note de gouvernance

> Ce modèle fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire.

## ⚠️ Considérations de performance

- La capacité de débit de FSx for ONTAP est **partagée entre NFS/SMB/S3 AP**. L'exécution avec MapConcurrency=10 en parallèle peut impacter d'autres charges de travail sur le même volume.
- Pour le traitement par lots volumineux, vérifiez la Throughput Capacity (MBps) de FSx for ONTAP et ajustez MapConcurrency en conséquence.
- Recommandé : Commencez avec MapConcurrency=5 en production, surveillez les métriques CloudWatch (ThroughputUtilization) et augmentez progressivement.

> **Note S3 AP NetworkOrigin** : La Lambda Discovery est déployée dans un VPC. Si le NetworkOrigin du S3 Access Point est `Internet`, l'accès via S3 Gateway VPC Endpoint n'est pas possible (les requêtes ne sont pas routées vers le plan de données FSx). Utilisez un S3 AP VPC-origin ou configurez l'accès via NAT Gateway. Voir [Notes de compatibilité S3AP](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
