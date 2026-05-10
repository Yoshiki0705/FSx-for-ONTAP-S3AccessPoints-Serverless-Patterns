# Pipeline de prétraitement des données de conduite autonome -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de prétraitement et d'annotation pour les données de capteurs de conduite autonome. Les données sont automatiquement classifiées pour générer des jeux de données d'entraînement.

**Message clé**: Prétraiter automatiquement les données de capteurs pour générer des jeux de données annotés prêts pour l'entraînement IA.

**Durée prévue**: 3–5 min

---

## Destination de sortie : sélectionnable via OutputDestination (Pattern B)

Ce UC prend en charge le paramètre `OutputDestination` (mise à jour 2026-05-10,
voir `docs/output-destination-patterns.md`).

**Deux modes** :

- **STANDARD_S3** (par défaut) : les artefacts IA vont vers un nouveau bucket S3
- **FSXN_S3AP** ("no data movement") : les artefacts IA retournent sur le même
  volume FSx ONTAP via S3 Access Point, visibles pour les utilisateurs SMB/NFS
  dans la structure de répertoires existante

```bash
# Mode FSXN_S3AP
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

Pour les contraintes et solutions de contournement AWS, voir
[README.fr.md — Contraintes de spécification AWS](../../README.fr.md#contraintes-de-spécification-aws-et-solutions-de-contournement).

---
## Workflow

```
Collecte capteurs → Conversion format → Classification frames → Génération annotations → Rapport dataset
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : Le prétraitement manuel des données massives est un goulot

### Section 2 (0:45–1:30)
> Upload : Placer les fichiers de logs capteurs pour démarrer le pipeline

### Section 3 (1:30–2:30)
> Prétraitement et classification : Conversion automatique et classification IA des frames

### Section 4 (2:30–3:45)
> Résultats annotation : Vérification des labels générés et statistiques qualité

### Section 5 (3:45–5:00)
> Rapport dataset : Rapport de préparation à l'entraînement et métriques qualité

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Python 3.13) | Validation qualité des données capteurs, classification de scènes, génération de catalogue |
| Lambda SnapStart | Réduction du démarrage à froid (`EnableSnapStart=true` opt-in) |
| SageMaker (4-way routing) | Inférence (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Véritable scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Classification de scènes / suggestions d'annotation |
| Amazon Athena | Recherche et agrégation de métadonnées |
| CloudFormation Guard Hooks | Application des politiques de sécurité au déploiement |

### Test local (Phase 6A)

```bash
# Test local avec SAM CLI
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
