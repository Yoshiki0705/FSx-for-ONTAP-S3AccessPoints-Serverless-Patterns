# Rapport de détection d'anomalies et de conformité des données de journalisation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline de détection d'anomalies dans les données de diagraphie de puits et de génération de rapports de conformité. Elle détecte automatiquement les problèmes de qualité des données de diagraphie et crée efficacement des rapports réglementaires.

**Message clé de la démo** : Détection automatique des anomalies dans les données de diagraphie et génération instantanée de rapports de conformité conformes aux exigences réglementaires.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Ingénieur géologue / Analyste de données / Responsable de la conformité |
| **Activités quotidiennes** | Analyse des données de diagraphie, évaluation des puits, création de rapports réglementaires |
| **Défis** | La détection manuelle d'anomalies dans de grandes quantités de données de diagraphie est chronophage |
| **Résultats attendus** | Vérification automatique de la qualité des données et efficacité accrue des rapports réglementaires |

### Persona : Matsumoto-san (Ingénieur géologue)

- Gère les données de diagraphie de plus de 50 puits
- Doit soumettre des rapports périodiques aux autorités réglementaires
- « Je souhaite détecter automatiquement les anomalies de données et rationaliser la création de rapports »

---

## Demo Scenario : Analyse par lots des données de diagraphie

### Vue d'ensemble du workflow

```
Données de diagraphie    Validation des données    Détection d'anomalies    Conformité
(LAS/DLIS)           →   Contrôle qualité      →   Analyse statistique  →   Génération de rapports
                         Format                    Détection de valeurs aberrantes
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Il est nécessaire de vérifier périodiquement la qualité des données de diagraphie de 50 puits et de les rapporter aux autorités réglementaires. L'analyse manuelle présente un risque élevé d'omissions.

**Visuel clé** : Liste des fichiers de données de diagraphie (format LAS/DLIS)

### Section 2 : Data Ingestion (0:45–1:30)

**Résumé de la narration** :
> Téléchargement des fichiers de données de diagraphie et lancement du pipeline de validation de la qualité. Début par la validation du format.

**Visuel clé** : Lancement du workflow, validation du format de données

### Section 3 : Anomaly Detection (1:30–2:30)

**Résumé de la narration** :
> Exécution de la détection d'anomalies statistiques pour chaque courbe de diagraphie (GR, SP, Resistivity, etc.). Détection des valeurs aberrantes par intervalle de profondeur.

**Visuel clé** : Traitement de détection d'anomalies en cours, mise en évidence des anomalies sur les courbes de diagraphie

### Section 4 : Results Review (2:30–3:45)

**Résumé de la narration** :
> Vérification des anomalies détectées par puits et par courbe. Classification des types d'anomalies (pics, lacunes, dépassements de plage).

**Visuel clé** : Tableau des résultats de détection d'anomalies, résumé par puits

### Section 5 : Compliance Report (3:45–5:00)

**Résumé de la narration** :
> L'IA génère automatiquement un rapport de conformité conforme aux exigences réglementaires. Comprend un résumé de la qualité des données, un enregistrement des réponses aux anomalies et des actions recommandées.

**Visuel clé** : Rapport de conformité (conforme au format réglementaire)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des fichiers de données de diagraphie | Section 1 |
| 2 | Lancement du pipeline et validation du format | Section 2 |
| 3 | Résultats du traitement de détection d'anomalies | Section 3 |
| 4 | Résumé des anomalies par puits | Section 4 |
| 5 | Rapport de conformité | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « La vérification manuelle de la qualité des données de diagraphie de 50 puits atteint ses limites » |
| Ingestion | 0:45–1:30 | « Le téléchargement des données lance automatiquement la validation » |
| Detection | 1:30–2:30 | « Détection des anomalies de chaque courbe par méthodes statistiques » |
| Results | 2:30–3:45 | « Classification et vérification des anomalies par puits et par courbe » |
| Report | 3:45–5:00 | « L'IA génère automatiquement un rapport conforme à la réglementation » |

---

## Sample Data Requirements

| # | Données | Utilisation |
|---|--------|------|
| 1 | Données de diagraphie normales (format LAS, 10 puits) | Référence de base |
| 2 | Données avec anomalies de pics (3 cas) | Démo de détection d'anomalies |
| 3 | Données avec intervalles manquants (2 cas) | Démo de contrôle qualité |
| 4 | Données avec dépassements de plage (2 cas) | Démo de classification |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée requise |
|--------|---------|
| Préparation des données de diagraphie d'exemple | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Surveillance en temps réel des données de forage
- Automatisation de la corrélation stratigraphique
- Intégration avec modèles géologiques 3D

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (LAS Parser) | Analyse du format des données de diagraphie |
| Lambda (Anomaly Detector) | Détection d'anomalies statistiques |
| Lambda (Report Generator) | Génération de rapports de conformité via Bedrock |
| Amazon Athena | Analyse agrégée des données de diagraphie |

### Fallback

| Scénario | Réponse |
|---------|------|
| Échec de l'analyse LAS | Utiliser des données pré-analysées |
| Latence Bedrock | Afficher un rapport pré-généré |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## Captures d'écran UI/UX vérifiées

Conformément à la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, **cible les écrans UI/UX que les utilisateurs finaux voient réellement dans leurs activités quotidiennes**. Les vues techniques (graphe Step Functions, événements de pile CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification de ce cas d'usage

- ✅ **Exécution E2E** : Confirmée dans Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Photographié lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC8, succès d'exécution Lambda confirmés)
- 🔄 **Méthode de reproduction** : Voir « Guide de capture » à la fin de ce document

### Photographié lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC8 (SUCCEEDED)

![Vue graphique Step Functions UC8 (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/uc8-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant l'état d'exécution de chaque état Lambda / Parallel / Map par couleur.

### Captures d'écran existantes (portions applicables de Phase 1-6)

#### Graphe Step Functions UC8 (SUCCEEDED — Rephotographié après correction IAM Phase 8)

![Graphe Step Functions UC8 (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

Redéployé après correction IAM S3AP. Tous les états SUCCEEDED (2:59).

#### Graphe Step Functions UC8 (Vue zoomée — Détails de chaque étape)

![Graphe Step Functions UC8 (Vue zoomée)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (segy-metadata/, anomalies/, reports/)
- Résultats de requête Athena (statistiques de métadonnées SEG-Y)
- Étiquettes d'image de log de puits Rekognition
- Rapport de détection d'anomalies

### Guide de capture

1. **Préparation** :
   - Vérifier les prérequis avec `bash scripts/verify_phase7_prerequisites.sh` (présence VPC/S3 AP communs)
   - Packager Lambda avec `UC=energy-seismic bash scripts/package_generic_uc.sh`
   - Déployer avec `bash scripts/deploy_generic_ucs.sh UC8`

2. **Placement des données d'exemple** :
   - Télécharger des fichiers d'exemple vers le préfixe `seismic/` via l'alias S3 AP
   - Lancer Step Functions `fsxn-energy-seismic-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-energy-seismic-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (se référer au format `build/preview_*.html`)
   - Notification par e-mail SNS (le cas échéant)

4. **Traitement de masquage** :
   - Masquage automatique avec `python3 scripts/mask_uc_demos.py energy-seismic-demo`
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - Supprimer avec `bash scripts/cleanup_generic_ucs.sh UC8`
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
