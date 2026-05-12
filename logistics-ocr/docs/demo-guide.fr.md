# Guide de démonstration — OCR des bordereaux de livraison et analyse des stocks

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline de traitement OCR de bordereaux de livraison et d'analyse des stocks. Elle numérise les bordereaux papier et agrège/analyse automatiquement les données d'entrée et de sortie de stock.

**Message clé de la démo** : Numériser automatiquement les bordereaux de livraison pour faciliter la visibilité en temps réel des stocks et la prévision de la demande.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Responsable logistique / Gestionnaire d'entrepôt |
| **Tâches quotidiennes** | Gestion des entrées/sorties, vérification des stocks, organisation des livraisons |
| **Problématique** | Retards et erreurs dus à la saisie manuelle des bordereaux papier |
| **Résultats attendus** | Automatisation du traitement des bordereaux et visualisation des stocks |

### Persona : M. Saito (Responsable logistique)

- Traite plus de 500 bordereaux de livraison par jour
- Les informations de stock sont toujours en retard en raison du décalage de la saisie manuelle
- « Je veux que les stocks soient mis à jour simplement en scannant les bordereaux »

---

## Demo Scenario : Traitement par lot des bordereaux de livraison

### Vue d'ensemble du workflow

```
Bordereaux de        Traitement OCR    Structuration      Analyse des stocks
livraison         →  Extraction de  →  des données    →   Rapports agrégés
(images scannées)    texte             Mapping des        Prévision de la
                                       champs             demande
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Plus de 500 bordereaux de livraison par jour. Avec la saisie manuelle, la mise à jour des informations de stock est retardée, augmentant les risques de rupture de stock ou de surstockage.

**Visuel clé** : Grande quantité d'images de bordereaux scannés, image illustrant les retards de saisie manuelle

### Section 2 : Scan & Upload (0:45–1:30)

**Résumé de la narration** :
> Il suffit de placer les images de bordereaux scannés dans un dossier pour que le pipeline OCR démarre automatiquement.

**Visuel clé** : Téléchargement d'images de bordereaux → Démarrage du workflow

### Section 3 : OCR Processing (1:30–2:30)

**Résumé de la narration** :
> L'OCR extrait le texte des bordereaux et l'IA mappe automatiquement les champs tels que le nom du produit, la quantité, la destination, la date, etc.

**Visuel clé** : Traitement OCR en cours, résultats d'extraction des champs

### Section 4 : Inventory Analysis (2:30–3:45)

**Résumé de la narration** :
> Les données extraites sont comparées à la base de données de stock. Les entrées et sorties sont automatiquement agrégées et l'état des stocks est mis à jour.

**Visuel clé** : Résultats d'agrégation des stocks, évolution des entrées/sorties par article

### Section 5 : Demand Report (3:45–5:00)

**Résumé de la narration** :
> L'IA génère un rapport d'analyse des stocks. Elle présente le taux de rotation des stocks, les articles à risque de rupture et les recommandations de commande.

**Visuel clé** : Rapport de stock généré par l'IA (résumé des stocks + recommandations de commande)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des images de bordereaux scannés | Section 1 |
| 2 | Téléchargement et démarrage du pipeline | Section 2 |
| 3 | Résultats d'extraction OCR | Section 3 |
| 4 | Tableau de bord d'agrégation des stocks | Section 4 |
| 5 | Rapport d'analyse des stocks par IA | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Les informations de stock sont toujours obsolètes en raison des retards de saisie manuelle » |
| Upload | 0:45–1:30 | « Le traitement automatique démarre simplement en plaçant les scans » |
| OCR | 1:30–2:30 | « L'IA reconnaît et structure automatiquement les champs des bordereaux » |
| Analysis | 2:30–3:45 | « Agrégation automatique des entrées/sorties et mise à jour instantanée des stocks » |
| Report | 3:45–5:00 | « L'IA présente les risques de rupture et les recommandations de commande » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Images de bordereaux d'entrée (10 pièces) | Démo de traitement OCR |
| 2 | Images de bordereaux de sortie (10 pièces) | Démo de déduction de stock |
| 3 | Bordereaux manuscrits (3 pièces) | Démo de précision OCR |
| 4 | Données maîtres de stock | Démo de comparaison |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée |
|--------|---------|
| Préparation des images de bordereaux échantillons | 2 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Traitement des bordereaux en temps réel (intégration caméra)
- Intégration avec système WMS
- Intégration de modèle de prévision de la demande

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (OCR Processor) | Extraction de texte des bordereaux via Textract |
| Lambda (Field Mapper) | Mapping des champs via Bedrock |
| Lambda (Inventory Updater) | Mise à jour et agrégation des données de stock |
| Lambda (Report Generator) | Génération de rapport d'analyse des stocks |

### Fallback

| Scénario | Réponse |
|---------|------|
| Baisse de précision OCR | Utiliser des données prétraitées |
| Latence Bedrock | Afficher un rapport prégénéré |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## À propos de la destination de sortie : Sélectionnable via OutputDestination (Pattern B)

UC12 logistics-ocr prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-10
(voir `docs/output-destination-patterns.md`).

**Charge de travail concernée** : OCR de bordereaux de livraison / Analyse des stocks / Rapports logistiques

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats de l'IA.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (autres paramètres obligatoires)
```

### FSXN_S3AP (pattern "no data movement")
Écrit les résultats de l'IA via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les données originales.
Les utilisateurs SMB/NFS peuvent consulter directement les résultats de l'IA dans la structure de répertoires
qu'ils utilisent pour leur travail. Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (autres paramètres obligatoires)
```

**Points d'attention** :

- Spécification de `S3AccessPointName` fortement recommandée (autoriser IAM pour les formats Alias et ARN)
- Les objets de plus de 5 Go ne sont pas possibles avec FSxN S3AP (spécification AWS), multipart upload obligatoire
- Pour les contraintes liées aux spécifications AWS, voir
  [la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Même approche que pour les démos Phase 7 UC15/16/17 et UC6/11/14 : cibler **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements CloudFormation
Stack, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ✅ **Exécution E2E** : Confirmée en Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Capturées lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC12, succès d'exécution Lambda confirmés)
- 🔄 **Méthode de reproduction** : Voir le « Guide de capture » à la fin de ce document

### Capturées lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### UC12 Step Functions Graph view (SUCCEEDED)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant par couleur
l'état d'exécution de chaque Lambda / Parallel / Map State.

### Captures d'écran existantes (issues de Phase 1-6)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph (vue zoomée — détails de chaque étape)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (waybills-ocr/, inventory/, reports/)
- Résultats OCR des bordereaux Textract (Cross-Region)
- Labels d'images d'entrepôt Rekognition
- Rapport d'agrégation des livraisons

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC/S3 AP communs existants)
   - `UC=logistics-ocr bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC12` pour déployer

2. **Placement des données échantillons** :
   - Télécharger des fichiers échantillons via S3 AP Alias vers le préfixe `waybills/`
   - Démarrer Step Functions `fsxn-logistics-ocr-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-logistics-ocr-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (se référer au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py logistics-ocr-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC12` pour supprimer
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
