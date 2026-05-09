# Étiquetage d images produit et génération de métadonnées catalogue -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline d'étiquetage automatique d'images produit et de génération de métadonnées catalogue. L'IA analyse les photos pour générer tags et descriptions.

**Message clé**: L'IA extrait automatiquement les attributs des images pour générer instantanément les métadonnées catalogue et accélérer la mise en ligne.

**Durée prévue**: 3–5 min

---

## Workflow

```
Upload images → Analyse visuelle → Étiquetage attributs → Génération descriptions → Rapport catalogue
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : L étiquetage manuel de milliers de produits est un goulot

### Section 2 (0:45–1:30)
> Upload : Placer les photos produit pour démarrer le traitement

### Section 3 (1:30–2:30)
> Analyse IA et étiquetage : Extraction automatique couleur, matière, catégorie par vision IA

### Section 4 (2:30–3:45)
> Génération métadonnées : Descriptions produit et mots-clés de recherche automatiques

### Section 5 (3:45–5:00)
> Rapport catalogue : Statistiques de traitement et résultats de validation qualité

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Image Analyzer) | Analyse visuelle IA |
| Lambda (Tag Generator) | Génération d'étiquettes attributs |
| Lambda (Description Writer) | Rédaction automatique descriptions |
| Amazon Athena | Analyse statistique catalogue |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
