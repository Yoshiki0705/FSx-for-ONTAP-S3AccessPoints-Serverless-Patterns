# Contrôle qualité du séquençage et agrégation des variants — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline de contrôle qualité et d'agrégation de variants pour les données de séquençage de nouvelle génération (NGS). Elle valide automatiquement la qualité du séquençage et agrège les résultats d'appel de variants sous forme de rapport.

**Message clé de la démo** : Automatiser le QC des données de séquençage et générer instantanément des rapports d'agrégation de variants. Garantir la fiabilité de l'analyse.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Bioinformaticien / Chercheur en analyse génomique |
| **Activités quotidiennes** | QC des données de séquençage, appel de variants, interprétation des résultats |
| **Défis** | La vérification manuelle du QC pour un grand nombre d'échantillons est chronophage |
| **Résultats attendus** | Automatisation du QC et efficacité de l'agrégation de variants |

### Persona : Kato-san (Bioinformaticien)

- Traite plus de 100 échantillons de données de séquençage par semaine
- Nécessite une détection précoce des échantillons ne répondant pas aux critères de QC
- « Je veux envoyer automatiquement uniquement les échantillons ayant passé le QC vers l'analyse en aval »

---

## Demo Scenario : QC de lot de séquençage

### Vue d'ensemble du workflow

```
Fichiers FASTQ/BAM    Analyse QC      Jugement qualité    Agrégation variants
(100+ échantillons)  →   Calcul     →   Pass/Fail      →   Génération rapport
                         métriques       Filtre
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Plus de 100 échantillons de données de séquençage par semaine. Si des échantillons de mauvaise qualité se mélangent à l'analyse en aval, la fiabilité de l'ensemble des résultats diminue.

**Visuel clé** : Liste des fichiers de données de séquençage

### Section 2 : Pipeline Trigger (0:45–1:30)

**Résumé de la narration** :
> Après la fin de l'exécution du séquençage, le pipeline QC démarre automatiquement. Tous les échantillons sont traités en parallèle.

**Visuel clé** : Démarrage du workflow, liste des échantillons

### Section 3 : QC Metrics (1:30–2:30)

**Résumé de la narration** :
> Calcul des métriques QC pour chaque échantillon : nombre de reads, taux Q30, taux de mapping, profondeur de couverture, taux de duplication.

**Visuel clé** : Traitement du calcul des métriques QC, liste des métriques

### Section 4 : Quality Filtering (2:30–3:45)

**Résumé de la narration** :
> Jugement Pass/Fail basé sur les critères QC. Classification des causes d'échec (reads de faible qualité, faible couverture, etc.).

**Visuel clé** : Résultats du jugement Pass/Fail, classification des causes d'échec

### Section 5 : Variant Summary (3:45–5:00)

**Résumé de la narration** :
> Agrégation des résultats d'appel de variants des échantillons ayant passé le QC. Comparaison inter-échantillons, distribution des variants, génération d'un rapport de synthèse IA.

**Visuel clé** : Rapport d'agrégation de variants (synthèse statistique + interprétation IA)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des données de séquençage | Section 1 |
| 2 | Écran de démarrage du pipeline | Section 2 |
| 3 | Résultats des métriques QC | Section 3 |
| 4 | Résultats du jugement Pass/Fail | Section 4 |
| 5 | Rapport d'agrégation de variants | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « La contamination par des échantillons de faible qualité nuit à la fiabilité de l'ensemble de l'analyse » |
| Trigger | 0:45–1:30 | « Le QC démarre automatiquement à la fin de l'exécution » |
| Metrics | 1:30–2:30 | « Calcul des principales métriques QC pour tous les échantillons » |
| Filtering | 2:30–3:45 | « Jugement automatique Pass/Fail basé sur les critères » |
| Summary | 3:45–5:00 | « Génération instantanée de l'agrégation de variants et de la synthèse IA » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Métriques FASTQ de haute qualité (20 échantillons) | Référence de base |
| 2 | Échantillons de faible qualité (Q30 < 80%, 3 cas) | Démo de détection d'échec |
| 3 | Échantillons à faible couverture (2 cas) | Démo de classification |
| 4 | Résultats d'appel de variants (synthèse VCF) | Démo d'agrégation |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée |
|--------|---------|
| Préparation des données QC d'échantillons | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Surveillance du séquençage en temps réel
- Génération automatique de rapports cliniques
- Analyse intégrée multi-omiques

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (QC Calculator) | Calcul des métriques QC de séquençage |
| Lambda (Quality Filter) | Jugement Pass/Fail et classification |
| Lambda (Variant Aggregator) | Agrégation de variants |
| Lambda (Report Generator) | Génération de rapport de synthèse via Bedrock |

### Fallback

| Scénario | Réponse |
|---------|------|
| Retard de traitement de données volumineuses | Exécution sur un sous-ensemble |
| Retard Bedrock | Affichage d'un rapport pré-généré |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14 : cibler **les écrans UI/UX que les utilisateurs finaux voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements CloudFormation Stack, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification de ce cas d'usage

- ✅ **Exécution E2E** : Confirmée dans Phase 1-6 (voir README racine)
- 📸 **Re-capture UI/UX** : ✅ Capturée lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC7, succès d'exécution Lambda confirmés)
- 📸 **Capture UI/UX (Phase 8 Theme D)** : ✅ Capture SUCCEEDED terminée (commit 2b958db — redéployé après correction IAM S3AP, tous les steps réussis en 3:03)
- 🔄 **Méthode de reproduction** : Voir le « Guide de capture » à la fin de ce document

### Capturé lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC7 (SUCCEEDED)

![Vue graphique Step Functions UC7 (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

La vue graphique Step Functions visualise l'état d'exécution de chaque état Lambda / Parallel / Map par couleur, écran le plus important pour l'utilisateur final.

#### Graphe Step Functions UC7 (SUCCEEDED — Re-capture Phase 8 Theme D)

![Graphe Step Functions UC7 (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

Redéployé après correction IAM S3AP. Tous les steps SUCCEEDED (3:03).

#### Graphe Step Functions UC7 (Vue zoomée — Détails de chaque step)

![Graphe Step Functions UC7 (Vue zoomée)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### Captures d'écran existantes (portions pertinentes de Phase 1-6)

#### Résultats d'analyse génomique Comprehend Medical UC7 (Cross-Region us-east-1)

![Résultats d'analyse génomique Comprehend Medical UC7 (Cross-Region us-east-1)](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### Écrans UI/UX cibles lors de la re-vérification (liste de capture recommandée)

- Bucket de sortie S3 (fastq-qc/, variant-summary/, entities/)
- Résultats de requête Athena (agrégation de fréquence de variants)
- Entités médicales Comprehend Medical (Genes, Diseases, Mutations)
- Rapport de recherche généré par Bedrock

### Guide de capture

1. **Préparation** :
   - Vérifier les prérequis avec `bash scripts/verify_phase7_prerequisites.sh` (présence VPC/S3 AP communs)
   - Packager Lambda avec `UC=genomics-pipeline bash scripts/package_generic_uc.sh`
   - Déployer avec `bash scripts/deploy_generic_ucs.sh UC7`

2. **Placement des données d'échantillon** :
   - Uploader les fichiers d'échantillon vers le préfixe `fastq/` via l'alias S3 AP
   - Démarrer Step Functions `fsxn-genomics-pipeline-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-genomics-pipeline-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (se référer au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - Masquage automatique avec `python3 scripts/mask_uc_demos.py genomics-pipeline-demo`
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - Supprimer avec `bash scripts/cleanup_generic_ucs.sh UC7`
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
