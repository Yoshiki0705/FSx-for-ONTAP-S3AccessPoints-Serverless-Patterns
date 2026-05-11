# Contrôle qualité du rendu VFX -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de contrôle qualité des rendus VFX. La vérification automatique des frames permet la détection précoce des artefacts.

**Message clé**: Vérifier automatiquement les frames rendues, détectant instantanément les problèmes qualité.

**Durée prévue**: 3-5 min

---

## Destination de sortie : FSxN S3 Access Point (Pattern A)

Ce UC relève du **Pattern A : Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : tous les artefacts IA/ML sont écrits via le FSxN S3 Access Point
sur le **même volume FSx ONTAP** que les données source. Aucun bucket S3 standard
séparé n'est créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias d'entrée
- `S3AccessPointOutputAlias` : S3 AP Alias de sortie (peut être identique à l'entrée)

Pour les contraintes et solutions de contournement AWS, voir
[README.fr.md — Contraintes de spécification AWS](../../README.fr.md#contraintes-de-spécification-aws-et-solutions-de-contournement).

---
## Workflow

```
Sortie rendu (EXR/PNG) -> Analyse frames / Extraction métadonnées -> Évaluation qualité -> Rapport QC (par plan)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Problématique : Inspection visuelle de milliers de frames irréaliste

### Section 2 (0:45-1:30)
> Déclenchement : Fin de rendu lance automatiquement le QC

### Section 3 (1:30-2:30)
> Analyse : Statistiques pixels évaluent quantitativement la qualité

### Section 4 (2:30-3:45)
> Évaluation : Classification automatique des frames problématiques

### Section 5 (3:45-5:00)
> Rapport QC : Support immédiat pour décisions de re-rendu

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Frame Analyzer) | Extraction métadonnées/statistiques pixels |
| Lambda (Quality Checker) | Évaluation statistique qualité |
| Lambda (Report Generator) | Génération rapport QC via Bedrock |
| Amazon Athena | Analyse agrégée statistiques frames |

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
- 📸 **Capture UI/UX** : ✅ SFN Graph terminé (Phase 8 Theme D, commit 3c90042)

### Captures d'écran existantes (de Phase 1-6)

![UC4 Vue graphique Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![UC4 Graphique Step Functions (zoom — détail par étape)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles pour re-vérification (liste de captures recommandées)

- (À définir lors de la re-vérification)

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
