# GenAI RAG — Fichiers d'entreprise

🌐 **Language / Langue**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Aperçu

Un pattern qui fournit de manière sécurisée les documents confidentiels des serveurs de fichiers d'entreprise (FSx for ONTAP) aux pipelines Amazon Bedrock / RAG via S3 Access Points **sans copie vers S3**. Réalise un RAG sensible aux permissions tout en maintenant les permissions de fichiers (ACL/NTFS).

## Problèmes résolus

| Problème | Solution |
|----------|----------|
| Prolifération des données par copie de fichiers sensibles vers S3 | Lecture directe via S3 AP, pas de copie nécessaire |
| Perte des permissions de fichiers | Récupération des ACL via ONTAP REST API, filtrage au moment de la réponse RAG |
| Problèmes de fraîcheur des données | FlexCache + S3 AP fournit les données les plus récentes |
| Traitement de volume complet de grands serveurs de fichiers | EventBridge Scheduler + détection delta pour l'efficacité |
| Distance entre le traitement IA et les données | FlexCache place les données près du VPC de traitement IA |

## Concept RAG sensible aux permissions

1. **Au moment de l'indexation**: Récupérer les informations ACL/permissions pour chaque document via ONTAP REST API et stocker comme métadonnées dans le magasin vectoriel
2. **Au moment de la requête**: Filtrer la portée de recherche aux seuls documents accessibles par l'utilisateur basé sur son AD SID / appartenance au groupe
3. **Au moment de la réponse**: Passer uniquement les documents filtrés à Bedrock pour la génération de réponse

## Métriques de succès

| Métrique | Objectif |
|----------|----------|
| Fichiers traités par exécution | > 200 fichiers |
| Taux de succès d'extraction ACL | > 95% |
| Temps de génération d'embeddings | < 5 min / 100 fichiers |
| Précision du filtrage sensible aux permissions | > 99% |
| Taux de Human Review | < 10% (chunks à faible confiance) |

---

## Déploiement

Déployez avec AWS SAM CLI (remplacez les valeurs d'exemple selon votre environnement) :

```bash
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name fsxn-rag-enterprise-files \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **Remarque** : `template.yaml` est conçu pour être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3).

> **À propos de l'extraction d'ACL au niveau fichier** : par défaut, l'extraction d'ACL fonctionne en mode simulation (aucun ONTAP requis). Pour extraire des ACL réelles, définissez `OntapManagementIp` / `OntapSecretName`. Notez que ce modèle n'inclut pas de `VpcConfig` ; joindre un LIF de gestion ONTAP privé nécessite donc une configuration réseau supplémentaire.

## Note de gouvernance

> Ce pattern fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Les organisations doivent consulter des professionnels qualifiés.
