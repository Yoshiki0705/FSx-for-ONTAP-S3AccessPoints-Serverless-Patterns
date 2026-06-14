# Curation en libre-service de la base de connaissances

🌐 **Language / Langue**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Aperçu

Un modèle qui permet aux utilisateurs métier de maintenir une source de données Amazon Bedrock Knowledge Base **uniquement par glisser-déposer dans l'Explorateur Windows familier**.

Un **volume/dossier dédié à l'IA** sur FSx for ONTAP est partagé via SMB pour chaque rôle/service. Les mêmes données sont connectées à une Amazon Bedrock Knowledge Base **via S3 Access Points (chemin en lecture)**, et les modifications de fichiers déclenchent l'**ingestion automatique**.

On passe ainsi d'une exploitation « ETL/copie/ingestion manuels par l'IT à chaque demande » à un **modèle démocratisé où le métier maintient lui-même ses connaissances**.

## Avant / Après

> **Note** : récit d'exploitation généralisé, avec noms de client, de personnes et d'équipes masqués.

- **Avant** : demande métier → l'IT copie manuellement depuis un Windows Server sur EC2 → téléversement S3 → ingestion manuelle dans Bedrock KB. Goulot d'étranglement par demande, double gestion des données.
- **Après** : « Déposez les données destinées à l'IA dans ce dossier Windows et maintenez-les vous-mêmes. » L'utilisateur fait un glisser-déposer habituel ; la KB se synchronise automatiquement via S3 AP.

## Deux scénarios de démonstration

La même base prend en charge deux étapes selon la maturité opérationnelle (voir le [guide de démo](docs/demo-guide.md)) :

| Scénario | Résumé | Déclencheur d'ingestion |
|---------|------|------------------------|
| **A : Pratique manuelle** | Maintenir les données IA par opérations de fichiers Windows (ajout/màj/suppression) ; ingestion déclenchée manuellement (console « Synchroniser »/CLI) | Manuel |
| **B : Automatisation** | Automatiser la synchro manuelle de A avec Lambda + Step Functions + EventBridge (détecter→ingérer→attendre→notifier) | Automatique |

> L'action de l'utilisateur métier (glisser-déposer) est identique dans les deux cas. Seules les étapes post-ingestion diffèrent : réalisées par une personne ou par le serverless.

## Problèmes résolus

| Problème | Solution |
|------|--------|
| Mises à jour en attente du travail manuel de l'IT | Le métier maintient via Windows ; ingestion automatique |
| Double gestion due aux copies S3 | Source de données directe depuis l'original FSx ONTAP via S3 AP |
| Ingestions/mises à jour manquées | Détection des changements puis Ingestion automatique |
| Compétences ETL/S3/Bedrock requises | Uniquement glisser-déposer Windows |
| Propriété des données floue | Arborescence par rôle/service |

## KB managée vs RAG personnalisé

Cet UC adopte **Bedrock Knowledge Bases managé (Pattern C)** pour minimiser la charge d'exploitation. Pour un filtrage des autorisations au niveau fichier lors de la recherche, choisissez le RAG personnalisé ([FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/), Pattern A).

> **Prérequis de déploiement** : créez la Knowledge Base et la source de données avec [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) ou la console Bedrock, puis transmettez leurs ID en paramètres du template.

## Sécurité

- Aucun déplacement de données (l'original reste sur FSx ONTAP ; S3 AP en lecture seule)
- Écriture uniquement via SMB/NFS ; le chemin d'ingestion IA (S3 AP) est en lecture
- ACL NTFS par dossier pour séparer les droits d'écriture par service
- La limite de la source de données S3 AP est au niveau volume/préfixe (le contrôle de visibilité par utilisateur est hors périmètre)

## Governance Note

> Ce modèle fournit des orientations d'architecture technique, et non des conseils juridiques ou de conformité. Consultez des professionnels qualifiés.
