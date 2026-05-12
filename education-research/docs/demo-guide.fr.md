# Analyse de classification et de réseau de citations d'articles — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline d'analyse de réseau de citations et de classification automatique d'articles académiques. Elle extrait les métadonnées de nombreux PDF d'articles et visualise les tendances de recherche.

**Message clé de la démo** : En classifiant automatiquement une collection d'articles et en analysant les relations de citation, on peut instantanément saisir la vue d'ensemble d'un domaine de recherche et identifier les articles importants.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Chercheur / Spécialiste en sciences de l'information et des bibliothèques / Administrateur de recherche |
| **Tâches quotidiennes** | Recherche documentaire, analyse des tendances de recherche, gestion d'articles |
| **Défi** | Impossible de découvrir efficacement les recherches connexes parmi un grand nombre d'articles |
| **Résultats attendus** | Cartographie du domaine de recherche et identification automatique des articles importants |

### Persona: Watanabe-san (Chercheur)

- En cours de revue de littérature sur un nouveau thème de recherche
- A collecté plus de 500 PDF d'articles, mais ne peut pas saisir la vue d'ensemble
- « Je veux classifier automatiquement par domaine et identifier les articles importants les plus cités »

---

## Demo Scenario: Analyse automatique d'une collection documentaire

### Vue d'ensemble du workflow

```
Ensemble de PDF       Extraction de         Classification        Rapport de
d'articles            métadonnées           et analyse            visualisation
(500+ articles)   →   Titre/Auteur      →   Classification    →   Génération de
                      Informations de       par sujet             carte de réseau
                      citation              Analyse de citation
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Plus de 500 PDF d'articles collectés. Je veux comprendre la distribution par domaine, les articles importants et les tendances de recherche, mais il est impossible de tout lire.

**Visuel clé** : Liste de fichiers PDF d'articles (en grand nombre)

### Section 2: Metadata Extraction (0:45–1:30)

**Résumé de la narration** :
> Extraction automatique du titre, des auteurs, du résumé et de la liste de citations de chaque PDF d'article.

**Visuel clé** : Traitement d'extraction de métadonnées, échantillon de résultats d'extraction

### Section 3: Classification (1:30–2:30)

**Résumé de la narration** :
> L'IA analyse les résumés et classifie automatiquement les sujets de recherche. Le clustering forme des groupes d'articles connexes.

**Visuel clé** : Résultats de classification par sujet, nombre d'articles par catégorie

### Section 4: Citation Analysis (2:30–3:45)

**Résumé de la narration** :
> Analyse des relations de citation et identification des articles importants avec un nombre élevé de citations. Analyse de la structure du réseau de citations.

**Visuel clé** : Statistiques du réseau de citations, classement des articles importants

### Section 5: Research Map (3:45–5:00)

**Résumé de la narration** :
> L'IA génère une vue d'ensemble du domaine de recherche sous forme de rapport récapitulatif. Présentation des tendances, des lacunes et des directions de recherche futures.

**Visuel clé** : Rapport de carte de recherche (analyse des tendances + littérature recommandée)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Collection de PDF d'articles | Section 1 |
| 2 | Résultats d'extraction de métadonnées | Section 2 |
| 3 | Résultats de classification par sujet | Section 3 |
| 4 | Statistiques du réseau de citations | Section 4 |
| 5 | Rapport de carte de recherche | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Je veux saisir la vue d'ensemble de 500 articles » |
| Extraction | 0:45–1:30 | « Extraction automatique de métadonnées à partir de PDF » |
| Classification | 1:30–2:30 | « L'IA classifie automatiquement par sujet » |
| Citation | 2:30–3:45 | « Identification des articles importants via le réseau de citations » |
| Map | 3:45–5:00 | « Visualisation de la vue d'ensemble et des tendances du domaine de recherche » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | PDF d'articles (30 articles, 3 domaines) | Objet de traitement principal |
| 2 | Données de relations de citation (avec citations croisées) | Démo d'analyse de réseau |
| 3 | Articles hautement cités (5 articles) | Démo d'identification d'articles importants |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée requise |
|--------|---------|
| Préparation des données d'articles échantillons | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Visualisation interactive du réseau de citations
- Système de recommandation d'articles
- Classification automatique périodique des nouveaux articles

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (PDF Parser) | Extraction de métadonnées de PDF d'articles |
| Lambda (Classifier) | Classification par sujet via Bedrock |
| Lambda (Citation Analyzer) | Construction et analyse du réseau de citations |
| Amazon Athena | Agrégation et recherche de métadonnées |

### Fallback

| Scénario | Réponse |
|---------|------|
| Échec d'analyse de PDF | Utiliser des données pré-extraites |
| Précision de classification insuffisante | Afficher des résultats pré-classifiés |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## Captures d'écran UI/UX vérifiées

Conformément à la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, cibler **les écrans UI/UX que les utilisateurs finaux voient réellement dans leur travail quotidien**. Les vues pour techniciens (graphe Step Functions, événements de pile CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification de ce cas d'usage

- ✅ **Exécution E2E** : Confirmée dans Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Photographié lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC13, succès d'exécution Lambda confirmés)
- 🔄 **Méthode de reproduction** : Voir « Guide de capture » à la fin de ce document

### Photographié lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### UC13 Step Functions Graph view (SUCCEEDED)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant l'état d'exécution de chaque état Lambda / Parallel / Map par couleur.

### Captures d'écran existantes (portions pertinentes de Phase 1-6)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph (vue d'ensemble complète)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph (affichage zoomé — détails de chaque étape)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (papers-ocr/, citations/, reports/)
- Résultats OCR d'articles Textract (Cross-Region)
- Détection d'entités Comprehend (auteurs, citations, mots-clés)
- Rapport d'analyse de réseau de recherche

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (présence de VPC/S3 AP communs)
   - `UC=education-research bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC13` pour déployer

2. **Placement des données échantillons** :
   - Télécharger des fichiers échantillons vers le préfixe `papers/` via S3 AP Alias
   - Démarrer Step Functions `fsxn-education-research-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-education-research-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification par e-mail SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py education-research-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC13` pour supprimer
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
