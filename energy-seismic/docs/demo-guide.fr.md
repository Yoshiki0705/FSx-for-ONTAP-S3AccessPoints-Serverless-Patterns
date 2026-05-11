# Détection d'anomalies de diagraphie et rapport de conformité -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de détection d'anomalies dans les données de diagraphie et de génération de rapports de conformité.

**Message clé**: Détecter automatiquement les anomalies dans les données de diagraphie et générer instantanément les rapports de conformité.

**Durée prévue**: 3–5 min

---

## Workflow

```
Collecte diagraphie → Prétraitement signal → Détection anomalies → Matching réglementaire → Rapport conformité
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : Rechercher manuellement des anomalies dans de grandes quantités de données est inefficace

### Section 2 (0:45–1:30)
> Upload : Placer les fichiers de diagraphie pour démarrer

### Section 3 (1:30–2:30)
> Détection : Analyse IA des patterns pour détecter automatiquement les anomalies

### Section 4 (2:30–3:45)
> Résultats : Liste des anomalies détectées et classification par gravité

### Section 5 (3:45–5:00)
> Rapport conformité : Résultats de comparaison réglementaire et recommandations

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Signal Processor) | Prétraitement signal diagraphie |
| Lambda (Anomaly Detector) | Détection IA d'anomalies |
| Lambda (Compliance Checker) | Vérification conformité réglementaire |
| Amazon Athena | Analyse agrégée de l'historique des anomalies |

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
- 📸 **UI/UX**: Not yet captured

### Captures d'écran existantes (de Phase 1-6)

*(Aucune applicable. Veuillez capturer lors de la re-vérification.)*

### Écrans UI/UX cibles pour re-vérification (liste de captures recommandées)

- Bucket S3 de sortie (segy-metadata/, anomalies/, reports/)
- Résultats de requête Athena (statistiques métadonnées SEG-Y)
- Labels d'images de diagraphie Rekognition
- Rapport de détection d'anomalies

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
