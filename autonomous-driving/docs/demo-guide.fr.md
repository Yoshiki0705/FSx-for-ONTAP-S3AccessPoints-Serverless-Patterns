# Prétraitement et annotation des données de conduite — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre le pipeline de prétraitement et d'annotation des données de conduite dans le développement de la conduite autonome. Elle permet de classifier automatiquement de grandes quantités de données de capteurs, d'effectuer des contrôles de qualité et de construire efficacement des ensembles de données d'apprentissage.

**Message clé de la démo** : Automatiser la validation de la qualité des données de conduite et l'ajout de métadonnées pour accélérer la construction d'ensembles de données pour l'apprentissage IA.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Ingénieur de données / Ingénieur ML |
| **Tâches quotidiennes** | Gestion des données de conduite, annotation, construction d'ensembles de données d'apprentissage |
| **Défis** | Impossible d'extraire efficacement des scènes utiles à partir de grandes quantités de données de conduite |
| **Résultats attendus** | Validation automatique de la qualité des données et efficacité de la classification des scènes |

### Persona : M. Ito (Ingénieur de données)

- Accumulation quotidienne de données de conduite de l'ordre du TB
- Vérification manuelle de la synchronisation caméra/LiDAR/radar
- « Je veux envoyer automatiquement uniquement les données de bonne qualité au pipeline d'apprentissage »

---

## Demo Scenario : Prétraitement par lots des données de conduite

### Vue d'ensemble du workflow

```
Données de conduite    Validation        Classification    Ensemble de données
(ROS bag, etc.)    →   Contrôle qualité  →  Métadonnées   →   Génération de
                       Vérification         Ajout (IA)        catalogue
                       synchronisation
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Des données de conduite accumulées quotidiennement de l'ordre du TB. Des données de mauvaise qualité (capteurs manquants, désynchronisation) sont mélangées, rendant la sélection manuelle irréaliste.

**Key Visual** : Structure des dossiers de données de conduite, visualisation du volume de données

### Section 2 : Pipeline Trigger (0:45–1:30)

**Résumé de la narration** :
> Lorsque de nouvelles données de conduite sont téléchargées, le pipeline de prétraitement démarre automatiquement.

**Key Visual** : Téléchargement de données → Démarrage automatique du workflow

### Section 3 : Quality Validation (1:30–2:30)

**Résumé de la narration** :
> Vérification de l'intégrité des données de capteurs : détection automatique des trames manquantes, de la synchronisation des horodatages et de la corruption des données.

**Key Visual** : Résultats du contrôle qualité — Score de santé par capteur

### Section 4 : Scene Classification (2:30–3:45)

**Résumé de la narration** :
> L'IA classifie automatiquement les scènes : intersections, autoroutes, mauvais temps, nuit, etc. Ajout en tant que métadonnées.

**Key Visual** : Tableau des résultats de classification des scènes, distribution par catégorie

### Section 5 : Dataset Catalog (3:45–5:00)

**Résumé de la narration** :
> Génération automatique d'un catalogue de données validées en qualité. Disponible comme ensemble de données interrogeable par conditions de scène.

**Key Visual** : Catalogue d'ensembles de données, interface de recherche

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Structure des dossiers de données de conduite | Section 1 |
| 2 | Écran de démarrage du pipeline | Section 2 |
| 3 | Résultats du contrôle qualité | Section 3 |
| 4 | Résultats de classification des scènes | Section 4 |
| 5 | Catalogue d'ensembles de données | Section 5 |

---

## Narration Outline

| Section | Temps | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Impossible de sélectionner manuellement des scènes utiles parmi des données de l'ordre du TB » |
| Trigger | 0:45–1:30 | « Le prétraitement démarre automatiquement lors du téléchargement » |
| Validation | 1:30–2:30 | « Détection automatique des capteurs manquants et de la désynchronisation » |
| Classification | 2:30–3:45 | « L'IA classifie automatiquement les scènes et ajoute des métadonnées » |
| Catalog | 3:45–5:00 | « Génération automatique d'un catalogue d'ensembles de données interrogeable » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Données de conduite normale (5 sessions) | Référence |
| 2 | Données avec trames manquantes (2 cas) | Démo contrôle qualité |
| 3 | Données de scènes diverses (intersection, autoroute, nuit) | Démo classification |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée |
|--------|---------|
| Préparation des données de conduite échantillons | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Génération automatique d'annotations 3D
- Sélection de données par apprentissage actif
- Intégration du versionnage des données

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Python 3.13) | Validation de la qualité des données de capteurs, classification des scènes, génération de catalogue |
| Lambda SnapStart | Réduction du démarrage à froid (opt-in avec `EnableSnapStart=true`) |
| SageMaker (4-way routing) | Inférence (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Véritable scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Classification des scènes, suggestions d'annotation |
| Amazon Athena | Recherche et agrégation de métadonnées |
| CloudFormation Guard Hooks | Application des politiques de sécurité lors du déploiement |

### Test local (Phase 6A)

```bash
# SAM CLI でローカルテスト
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### Fallback

| Scénario | Réponse |
|---------|------|
| Retard de traitement de données volumineuses | Exécution sur un sous-ensemble |
| Précision de classification insuffisante | Affichage de résultats pré-classifiés |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## À propos de la destination de sortie : Sélectionnable via OutputDestination (Pattern B)

UC9 autonomous-driving prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-10
(voir `docs/output-destination-patterns.md`).

**Charge de travail cible** : Données ADAS / conduite autonome (extraction de trames, QC de nuages de points, annotation, inférence)

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats IA.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP (pattern "no data movement")
Écrit les résultats IA via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les données originales.
Les utilisateurs SMB/NFS peuvent consulter directement les résultats IA dans la structure de répertoires
qu'ils utilisent pour leur travail. Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**Points d'attention** :

- Spécification de `S3AccessPointName` fortement recommandée (autoriser IAM pour les formats Alias et ARN)
- Objets > 5 Go non supportés par FSxN S3AP (spécification AWS), téléchargement multipart obligatoire
- Pour les contraintes de spécification AWS, voir
  [la section "Contraintes de spécification AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de pile
CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ⚠️ **Vérification E2E** : Fonctionnalités partielles uniquement (vérification supplémentaire recommandée en production)
- 📸 **Capture UI/UX** : ✅ SFN Graph terminé (Phase 8 Theme D, commit 081cc66)

### Captures d'écran existantes (issues de Phase 1-6)

![Vue graphique Step Functions UC9 (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (keyframes/, annotations/, qc/)
- Résultats de détection d'objets Rekognition sur images clés
- Résumé du contrôle qualité du nuage de points LiDAR
- JSON d'annotation compatible COCO

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC/S3 AP communs)
   - `UC=autonomous-driving bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC9` pour déployer

2. **Placement des données échantillons** :
   - Télécharger des fichiers échantillons via S3 AP Alias avec le préfixe `footage/`
   - Démarrer Step Functions `fsxn-autonomous-driving-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-autonomous-driving-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py autonomous-driving-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC9` pour supprimer
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
