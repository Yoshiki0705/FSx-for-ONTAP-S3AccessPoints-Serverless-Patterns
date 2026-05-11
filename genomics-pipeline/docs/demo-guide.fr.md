# QC de séquençage et agrégation de variants -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de contrôle qualité (QC) et d'agrégation de variants pour les données de séquençage génomique.

**Message clé**: Valider automatiquement la qualité des données de séquençage et agréger les variants pour que les chercheurs se concentrent sur l'analyse.

**Durée prévue**: 3–5 min

---

## Workflow

```
Upload FASTQ → Validation QC → Appel variants → Agrégation statistique → Rapport QC
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : Le QC manuel de grandes quantités de données de séquençage est chronophage

### Section 2 (0:45–1:30)
> Upload : Placer les fichiers FASTQ pour démarrer le pipeline

### Section 3 (1:30–2:30)
> QC et analyse variants : Validation qualité automatique et appel de variants

### Section 4 (2:30–3:45)
> Résultats : Métriques QC et statistiques de variants

### Section 5 (3:45–5:00)
> Rapport QC : Rapport qualité complet et recommandations pour analyses ultérieures

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (QC Validator) | Validation qualité séquençage |
| Lambda (Variant Caller) | Appel de variants |
| Lambda (Stats Aggregator) | Agrégation statistiques variants |
| Amazon Athena | Analyse métriques QC |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*

---

## Captures d'écran UI/UX vérifiées

Suivant la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant
**les écrans UI/UX que les utilisateurs finaux voient réellement dans leurs opérations quotidiennes**.
Les vues techniques (graphe Step Functions, événements de pile CloudFormation, etc.)
sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'utilisation

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **Capture UI/UX** : ✅ SUCCEEDED (Phase 8 Theme D, commit 2b958db — redéployé après correction IAM S3AP, 3:03 toutes les étapes réussies)

### Captures d'écran existantes (de Phase 1-6)

![UC7 Graphique Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

![UC7 Step Functions Graph (zoomed)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles pour re-vérification (liste de captures recommandées)

- Bucket S3 de sortie (fastq-qc/, variant-summary/, entities/)
- Résultats de requête Athena (agrégation de fréquence de variants)
- Entités Comprehend Medical (Gènes, Maladies, Mutations)
- Rapport de recherche généré par Bedrock

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
