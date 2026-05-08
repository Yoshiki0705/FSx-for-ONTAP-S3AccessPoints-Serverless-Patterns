# Guide d'évaluation de l'impact sur l'environnement existant

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## Aperçu

Ce document évalue l'impact sur les environnements existants lors de l'activation des fonctionnalités de chaque Phase, et fournit des procédures d'activation sécurisées et des méthodes de rollback.

> **Portée** : Phase 1–5 (ce document sera mis à jour lors de l'ajout de nouvelles phases)

Principes de conception :
- **Phase 1 (UC1–UC5)** : Piles CloudFormation indépendantes. Impact limité à la création d'ENI
- **Phase 2 (UC6–UC14)** : Piles indépendantes + appels API inter-régions
- **Phase 3 (Améliorations transversales)** : Extensions des UC existants. Opt-in (désactivé par défaut)
- **Phase 4 (SageMaker production, Multi-compte, Event-Driven)** : Extensions UC9 + nouveaux modèles. Opt-in
- **Phase 5 (Serverless Inference, Coûts, CI/CD, Multi-Region)** : Opt-in (désactivé par défaut)

---

## Phase 1–2 : UC de base et étendus

| Paramètre | Défaut | Impact |
|-----------|--------|--------|
| EnableS3GatewayEndpoint | "true" | ⚠️ Conflit avec S3 Gateway EP existant |
| EnableVpcEndpoints | "false" | Création d'Interface VPC Endpoints |
| CrossRegion | "us-east-1" | Appels API inter-régions (latence 50–200ms) |
| MapConcurrency | 10 | Affecte le quota de concurrence Lambda |

## Phase 3 : Améliorations transversales

| Paramètre | Défaut | Impact |
|-----------|--------|--------|
| EnableStreamingMode | "false" | Nouvelles ressources UC11 (polling non affecté) |
| EnableSageMakerTransform | "false" | ⚠️ Ajoute chemin SageMaker au workflow UC9 |
| EnableXRayTracing | "true" | ⚠️ Transmission de traces X-Ray |

## Phase 4 : Extensions production

| Paramètre | Défaut | Impact |
|-----------|--------|--------|
| EnableRealtimeEndpoint | "false" | ⚠️ Coût permanent (~$166/mois) |
| EnableDynamoDBTokenStore | "false" | Nouvelle table DynamoDB |

## Phase 5 : Serverless Inference, Coûts, CI/CD, Multi-Region

| Paramètre | Défaut | Impact |
|-----------|--------|--------|
| InferenceType | "none" | "serverless" modifie le routage |
| EnableScheduledScaling | "false" | ⚠️ Modifie le scaling des endpoints existants |
| EnableAutoStop | "false" | ⚠️ Arrête les endpoints inactifs |
| EnableMultiRegion | "false" | ⚠️ **Irréversible** — Global Table DynamoDB |

---

## Ordre d'activation recommandé

| Ordre | Fonctionnalité | Phase | Risque |
|-------|---------------|-------|--------|
| 1 | Déploiement UC1 | 1 | Faible |
| 2 | Observabilité | 3 | Faible |
| 3 | CI/CD | 5 | Aucun |
| 4–6 | Streaming / SageMaker / Serverless | 3–5 | Faible |
| 7–8 | Real-time / Scaling | 4–5 | Moyen ⚠️ |
| 9 | Multi-Region | 5 | Élevé ⚠️ **Irréversible** |

---

*Ce document est le guide d'évaluation de l'impact sur l'environnement existant pour FSxN S3AP Serverless Patterns.*
