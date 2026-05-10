# Traitement automatisé des contrats et factures — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de traitement automatisé pour contrats et factures. Il combine extraction OCR et extraction d entités pour générer des données structurées.

**Message clé**: Numériser automatiquement contrats et factures papier, extrayant instantanément montants, dates et fournisseurs.

**Durée prévue**: 3–5 min

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



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : Traiter 200+ factures manuellement par mois est insoutenable

### Section 2 (0:45–1:30)
> Upload : Placer les fichiers pour démarrer le traitement automatique

### Section 3 (1:30–2:30)
> OCR et extraction : OCR + IA pour classification et extraction de champs

### Section 4 (2:30–3:45)
> Sortie structurée : Données immédiatement utilisables

### Section 5 (3:45–5:00)
> Validation et rapport : Score de confiance identifiant les éléments à vérifier

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (OCR Processor) | Extraction texte via Textract |
| Lambda (Entity Extractor) | Extraction entités via Bedrock |
| Lambda (Classifier) | Classification type de document |
| Amazon Athena | Analyse agrégée des données extraites |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
