# Détection anomalies capteurs IoT et inspection qualité -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un workflow détectant automatiquement les anomalies des capteurs IoT de ligne de production et générant des rapports de qualité.

**Message clé**: Détecter automatiquement les anomalies dans les données capteurs pour la détection précoce des problèmes qualité.

**Durée prévue**: 3-5 min

---

## Workflow

```
Données capteurs (CSV/Parquet) -> Prétraitement -> Détection anomalies / Analyse statistique -> Rapport qualité (IA)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Problématique : Les alertes par seuil manquent les vraies anomalies

### Section 2 (0:45-1:30)
> Ingestion : Accumulation de données déclenche automatiquement analyse

### Section 3 (1:30-2:30)
> Détection : Méthodes statistiques détectent uniquement anomalies significatives

### Section 4 (2:30-3:45)
> Inspection : Identifier zones problématiques au niveau ligne/processus

### Section 5 (3:45-5:00)
> Rapport : IA présente causes racines candidates et contre-mesures

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Data Preprocessor) | Normalisation données capteurs |
| Lambda (Anomaly Detector) | Détection statistique anomalies |
| Lambda (Report Generator) | Génération rapport via Bedrock |
| Amazon Athena | Analyse agrégée anomalies |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
