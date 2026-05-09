# Évaluation des dommages par photo d'accident et rapport de réclamation -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline d'évaluation des dommages basé sur les photos d'accident et de génération automatique de rapports de réclamation.

**Message clé**: L'IA analyse automatiquement les dommages sur les photos pour générer instantanément les rapports de réclamation.

**Durée prévue**: 3–5 min

---

## Workflow

```
Upload photos → Détection zones endommagées → Évaluation gravité → Estimation coûts → Rapport réclamation
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : L'évaluation manuelle des dommages par photo est chronophage

### Section 2 (0:45–1:30)
> Upload : Placer les photos d'accident pour démarrer l'évaluation

### Section 3 (1:30–2:30)
> Analyse IA : Détection automatique des zones endommagées et classification de gravité

### Section 4 (2:30–3:45)
> Résultats : Estimation des coûts par zone et évaluation globale

### Section 5 (3:45–5:00)
> Rapport réclamation : Rapport généré automatiquement avec recommandations de traitement

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Damage Detector) | Détection IA des zones endommagées |
| Lambda (Severity Assessor) | Évaluation de la gravité |
| Lambda (Cost Estimator) | Estimation des coûts de réparation |
| Amazon Athena | Analyse agrégée de l'historique des réclamations |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
