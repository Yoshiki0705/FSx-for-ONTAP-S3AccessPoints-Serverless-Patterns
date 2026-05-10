# OCR de bordereaux de livraison et analyse des stocks -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline OCR pour bordereaux de livraison et analyse des stocks. Les documents papier sont automatiquement numérisés pour un suivi en temps réel.

**Message clé**: Traiter automatiquement les bordereaux par OCR pour mettre à jour les stocks en temps réel et améliorer l'efficacité logistique.

**Durée prévue**: 3–5 min

---

## Destination de sortie : sélectionnable via OutputDestination (Pattern B)

Ce UC prend en charge le paramètre `OutputDestination` (mise à jour 2026-05-10,
voir `docs/output-destination-patterns.md`).

**Deux modes** :

- **STANDARD_S3** (par défaut) : les artefacts IA vont vers un nouveau bucket S3
- **FSXN_S3AP** ("no data movement") : les artefacts IA retournent sur le même
  volume FSx ONTAP via S3 Access Point, visibles pour les utilisateurs SMB/NFS
  dans la structure de répertoires existante

```bash
# Mode FSXN_S3AP
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

Pour les contraintes et solutions de contournement AWS, voir
[README.fr.md — Contraintes de spécification AWS](../../README.fr.md#contraintes-de-spécification-aws-et-solutions-de-contournement).

---
## Workflow

```
Upload scan → Extraction OCR → Parsing champs → Mise à jour stocks → Rapport analyse
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : La saisie manuelle des bordereaux papier est source d erreurs et chronophage

### Section 2 (0:45–1:30)
> Upload : Placer les images scannées pour démarrer le traitement

### Section 3 (1:30–2:30)
> OCR et parsing : Extraction texte et conversion en données structurées

### Section 4 (2:30–3:45)
> Mise à jour stocks : Actualisation en temps réel basée sur les données extraites

### Section 5 (3:45–5:00)
> Rapport analyse : Tableau de bord logistique et alertes de détection d anomalies

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (OCR Engine) | Extraction texte bordereaux |
| Lambda (Field Parser) | Parsing données structurées |
| Lambda (Inventory Updater) | Mise à jour données stocks |
| Amazon Athena | Analyse statistique logistique |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
