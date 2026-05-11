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

- Bucket S3 de sortie (waybills-ocr/, inventory/, reports/)
- Résultats OCR Textract des lettres de voiture (Cross-Region)
- Labels d'images d'entrepôt Rekognition
- Rapport d'agrégation des livraisons

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
