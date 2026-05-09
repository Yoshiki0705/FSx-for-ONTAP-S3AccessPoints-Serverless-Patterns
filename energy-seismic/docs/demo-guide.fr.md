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
