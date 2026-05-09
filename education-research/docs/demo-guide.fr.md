# Classification de publications et analyse de réseau de citations -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de classification automatique de publications et d'analyse de réseau de citations. Les publications sont classifiées par thème et les relations de citation visualisées.

**Message clé**: Classifier automatiquement les publications par IA et analyser le réseau de citations pour identifier instantanément les tendances de recherche.

**Durée prévue**: 3–5 min

---

## Workflow

```
Upload publications → Extraction métadonnées → Classification IA → Construction réseau citations → Rapport analyse
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : Classifier manuellement des milliers de publications est irréaliste

### Section 2 (0:45–1:30)
> Upload : Placer les fichiers PDF pour démarrer le pipeline

### Section 3 (1:30–2:30)
> Classification IA et construction réseau : Classification thématique et extraction des citations

### Section 4 (2:30–3:45)
> Résultats : Clusters thématiques et identification des publications clés

### Section 5 (3:45–5:00)
> Rapport tendances : Analyse des tendances par domaine et liste de publications recommandées

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (PDF Parser) | Extraction métadonnées publications |
| Lambda (Topic Classifier) | Classification IA thématique |
| Lambda (Citation Analyzer) | Construction réseau de citations |
| Amazon Athena | Analyse agrégée des tendances |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
