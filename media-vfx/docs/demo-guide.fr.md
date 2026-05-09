# Contrôle qualité du rendu VFX -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de contrôle qualité des rendus VFX. La vérification automatique des frames permet la détection précoce des artefacts.

**Message clé**: Vérifier automatiquement les frames rendues, détectant instantanément les problèmes qualité.

**Durée prévue**: 3-5 min

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
