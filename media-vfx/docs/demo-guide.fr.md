# Vérification de la qualité du rendu VFX — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline de contrôle qualité pour les sorties de rendu VFX. La validation automatique des frames de rendu permet la détection précoce des artefacts et des frames erronées.

**Message clé de la démo** : Validation automatique de volumes importants de frames de rendu et détection instantanée des problèmes de qualité. Accélération de la prise de décision pour le re-rendu.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Superviseur VFX / TD Rendu |
| **Tâches quotidiennes** | Gestion des jobs de rendu, vérification qualité, approbation des plans |
| **Défis** | Vérification visuelle de milliers de frames nécessitant un temps considérable |
| **Résultats attendus** | Détection automatique des frames problématiques et accélération de la décision de re-rendu |

### Persona: Nakamura-san (Superviseur VFX)

- 1 projet avec 50+ plans, chaque plan contenant 100 à 500 frames
- La vérification qualité après rendu constitue un goulot d'étranglement
- « Je veux détecter automatiquement les frames noires, le bruit excessif et les textures manquantes »

---

## Demo Scenario: Validation qualité de lot de rendu

### Vue d'ensemble du workflow

```
Sortie de rendu     Analyse frames    Évaluation qualité    Rapport QC
(EXR/PNG)     →   Extraction    →   Détection           →    Résumé
                   métadonnées       anomalies               par plan
                                     (analyse statistique)
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Des milliers de frames générées par la ferme de rendu. La vérification visuelle des problèmes tels que frames noires, bruit, textures manquantes est irréaliste.

**Visuel clé** : Dossier de sortie de rendu (grand nombre de fichiers EXR)

### Section 2: Pipeline Trigger (0:45–1:30)

**Résumé de la narration** :
> Après la fin du job de rendu, le pipeline de contrôle qualité démarre automatiquement. Traitement parallèle par plan.

**Visuel clé** : Démarrage du workflow, liste des plans

### Section 3: Frame Analysis (1:30–2:30)

**Résumé de la narration** :
> Calcul des statistiques de pixels pour chaque frame (luminance moyenne, variance, histogramme). Vérification également de la cohérence entre frames.

**Visuel clé** : Traitement d'analyse de frames en cours, graphiques de statistiques de pixels

### Section 4: Quality Assessment (2:30–3:45)

**Résumé de la narration** :
> Détection des valeurs aberrantes statistiques et identification des frames problématiques. Classification des frames noires (luminance zéro), bruit excessif (variance anormale), etc.

**Visuel clé** : Liste des frames problématiques, classification par catégorie

### Section 5: QC Report (3:45–5:00)

**Résumé de la narration** :
> Génération d'un rapport QC par plan. Présentation des plages de frames nécessitant un re-rendu et des causes estimées.

**Visuel clé** : Rapport QC généré par IA (résumé par plan + actions recommandées)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Dossier de sortie de rendu | Section 1 |
| 2 | Écran de démarrage du pipeline | Section 2 |
| 3 | Progression de l'analyse de frames | Section 3 |
| 4 | Résultats de détection de frames problématiques | Section 4 |
| 5 | Rapport QC | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « La vérification visuelle de milliers de frames est irréaliste » |
| Trigger | 0:45–1:30 | « Le QC démarre automatiquement à la fin du rendu » |
| Analysis | 1:30–2:30 | « Évaluation quantitative de la qualité des frames via statistiques de pixels » |
| Assessment | 2:30–3:45 | « Classification et identification automatiques des frames problématiques » |
| Report | 3:45–5:00 | « Support immédiat pour la décision de re-rendu » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Frames normales (100) | Référence de base |
| 2 | Frames noires (3) | Démo de détection d'anomalies |
| 3 | Frames avec bruit excessif (5) | Démo d'évaluation qualité |
| 4 | Frames avec textures manquantes (2) | Démo de classification |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée |
|--------|---------|
| Préparation des données d'échantillons de frames | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Détection d'artefacts par deep learning
- Intégration avec la ferme de rendu (re-rendu automatique)
- Intégration avec le système de suivi des plans

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Frame Analyzer) | Extraction des métadonnées de frames et statistiques de pixels |
| Lambda (Quality Checker) | Évaluation qualité statistique |
| Lambda (Report Generator) | Génération de rapport QC via Bedrock |
| Amazon Athena | Analyse agrégée des statistiques de frames |

### Fallback

| Scénario | Action |
|---------|------|
| Retard de traitement de frames volumineuses | Basculer vers l'analyse de miniatures |
| Retard Bedrock | Afficher un rapport pré-généré |

---

*Ce document est un guide de production de vidéo de démo pour présentation technique.*

---

## À propos de la destination de sortie : FSxN S3 Access Point (Pattern A)

UC4 media-vfx est classé dans **Pattern A: Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : Les métadonnées de rendu et l'évaluation de la qualité des frames sont toutes écrites via FSxN S3 Access Point
dans le **même volume FSx ONTAP** que les assets de rendu originaux. Aucun bucket S3 standard n'est
créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias pour la lecture des données d'entrée
- `S3AccessPointOutputAlias` : S3 AP Alias pour l'écriture de sortie (peut être identique à l'entrée)

**Exemple de déploiement** :
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (autres paramètres requis)
```

**Vue depuis les utilisateurs SMB/NFS** :
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # Frame de rendu originale
  └── qc/shot_001/                     # Évaluation qualité de frame (dans le même volume)
      └── frame_0001_qc.json
```

Pour les contraintes liées aux spécifications AWS, consultez
[la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
ainsi que [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Captures d'écran UI/UX vérifiées

Conformément à la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, nous ciblons **les écrans UI/UX
que les utilisateurs finaux voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements
de stack CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ⚠️ **Vérification E2E** : Fonctionnalités partielles uniquement (vérification supplémentaire recommandée en production)
- 📸 **Capture UI/UX** : ✅ SFN Graph terminé (Phase 8 Theme D, commit 3c90042)

### Captures d'écran existantes (issues des Phases 1-6 applicables)

![Vue graphique Step Functions UC4 (SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![Graphique Step Functions UC4 (vue zoomée — détails de chaque étape)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la re-vérification (liste de captures recommandées)

- (À définir lors de la re-vérification)

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC/S3 AP communs)
   - `UC=media-vfx bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC4` pour déployer

2. **Placement des données d'échantillon** :
   - Télécharger des fichiers d'échantillon via S3 AP Alias vers le préfixe `renders/`
   - Démarrer Step Functions `fsxn-media-vfx-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-media-vfx-demo-output-<account>`
   - Aperçu du JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py media-vfx-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC4` pour supprimer
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
