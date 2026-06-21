# Espace de travail agentique Amazon Quick sur FSx for ONTAP

🌐 **Language / Langue**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Aperçu

Un modèle qui utilise Amazon FSx for NetApp ONTAP **via S3 Access Points** comme socle de données pour **Amazon Quick Suite** (l'espace de travail IA agentique). Les données maintenues par les équipes métier via des opérations de fichiers Windows sont exploitées par les capacités de Quick (Index / Sight / Flows / Research).

Contrairement à l'UC29 (ingestion en libre-service vers une base managée Bedrock), l'UC30 se concentre sur **un espace de travail agentique unifiant recherche non structurée, BI et automatisation d'actions**.

> Amazon Quick Suite, lancé en octobre 2025. Fonctionnalités/tarifs/régions sont « time-sensitive » ; voir [aws.amazon.com/quick](https://aws.amazon.com/quick/).

## Capacités Quick et S3 AP

| Capacité Quick | Données (S3 AP) | Mise en œuvre |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/` (non structuré) | Source de données S3 AP en lecture seule |
| Quick Sight (BI) | `analytics/<role>/` (csv) | Glue/Athena (Athena Query Lambda) |
| Quick Flows | `flows/<role>/` (json) | Action API (API Gateway + Lambda + Bedrock) |

## Deux scénarios de démonstration

| Scénario | Résumé |
|---------|------|
| **A : Espace manuel** | Déposer les données via Windows ; connecter Quick Index, créer des jeux Quick Sight, exécuter Quick Flows manuellement |
| **B : Automatisation** | Automatiser préparation, requêtes BI et actions en serverless (Data Prep / Athena Query / Action API) |

## Rôles × services

Les rôles correspondent aux cibles d'Amazon Quick (sales, marketing, IT, operations, finance, legal + developers). Données d'exemple dans [`sample-data/quick-workspace/`](sample-data/). Disposition de rôles partagée avec l'UC29.

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## Sécurité

- Aucun déplacement de données (original sur FSx for ONTAP ; S3 AP en lecture seule)
- L'Action API utilise l'authentification IAM (SigV4) — pas de point de terminaison public non authentifié
- Moindre privilège, chiffrement (SSE-FSX/SSE-S3/TLS)
- Les connexions de source de données Quick se configurent dans la console Quick

## Governance Note

> Orientations d'architecture technique, et non des conseils juridiques ou de conformité. Les fonctionnalités/tarifs de Quick évoluent ; vérifiez les sources officielles.
