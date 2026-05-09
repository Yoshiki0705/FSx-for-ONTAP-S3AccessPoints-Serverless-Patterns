# Pipeline de prétraitement des données de conduite autonome -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de prétraitement et d'annotation pour les données de capteurs de conduite autonome. Les données sont automatiquement classifiées pour générer des jeux de données d'entraînement.

**Message clé**: Prétraiter automatiquement les données de capteurs pour générer des jeux de données annotés prêts pour l'entraînement IA.

**Durée prévue**: 3–5 min

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
| Lambda (Format Converter) | Conversion format données capteurs |
| Lambda (Frame Classifier) | Classification IA des frames |
| Lambda (Annotation Generator) | Génération automatique d'annotations |
| Amazon Athena | Analyse statistique du dataset |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
