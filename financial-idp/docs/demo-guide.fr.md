# Traitement automatique des contrats et factures — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démonstration présente un pipeline de traitement automatique de contrats et de factures. En combinant l'extraction de texte par OCR et l'extraction d'entités, il génère automatiquement des données structurées à partir de documents non structurés.

**Message clé de la démonstration** : Numériser automatiquement les contrats et factures papier, et extraire et structurer instantanément les informations importantes telles que les montants, dates et partenaires commerciaux.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Responsable du département comptable / Responsable de la gestion des contrats |
| **Tâches quotidiennes** | Traitement des factures, gestion des contrats, approbation des paiements |
| **Défis** | La saisie manuelle de grands volumes de documents papier prend du temps |
| **Résultats attendus** | Automatisation du traitement des documents et réduction des erreurs de saisie |

### Persona : Yamada-san (Responsable du département comptable)

- Traite plus de 200 factures par mois
- Les erreurs et retards dus à la saisie manuelle sont problématiques
- « Je voudrais extraire automatiquement le montant et la date d'échéance dès réception d'une facture »

---

## Demo Scenario : Traitement par lots de factures

### Vue d'ensemble du workflow

```
Numérisation       Traitement OCR    Extraction         Données
documents     →    Extraction    →   d'entités et   →   structurées
(PDF/images)       de texte          classification      (JSON)
                                     (Analyse IA)
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Plus de 200 factures reçues chaque mois. La saisie manuelle des montants, dates et partenaires commerciaux prend du temps et génère des erreurs.

**Visuel clé** : Liste de nombreux fichiers PDF de factures

### Section 2 : Document Upload (0:45–1:30)

**Résumé de la narration** :
> Il suffit de placer les documents numérisés sur le serveur de fichiers pour que le pipeline de traitement automatique démarre.

**Visuel clé** : Téléchargement de fichiers → Démarrage automatique du workflow

### Section 3 : OCR & Extraction (1:30–2:30)

**Résumé de la narration** :
> L'OCR extrait le texte et l'IA détermine le type de document. Les factures, contrats et reçus sont automatiquement classés, et les champs importants sont extraits de chaque document.

**Visuel clé** : Progression du traitement OCR, résultats de classification des documents

### Section 4 : Structured Output (2:30–3:45)

**Résumé de la narration** :
> Les résultats d'extraction sont produits sous forme de données structurées. Les montants, dates d'échéance, noms de partenaires, numéros de facture, etc. sont disponibles au format JSON.

**Visuel clé** : Tableau des résultats d'extraction (numéro de facture, montant, échéance, partenaire)

### Section 5 : Validation & Report (3:45–5:00)

**Résumé de la narration** :
> L'IA évalue la fiabilité des résultats d'extraction et signale les éléments à faible confiance. Le rapport récapitulatif du traitement permet de comprendre l'état global du traitement.

**Visuel clé** : Résultats avec scores de confiance, rapport récapitulatif du traitement

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste de fichiers PDF de factures | Section 1 |
| 2 | Démarrage automatique du workflow | Section 2 |
| 3 | Traitement OCR et résultats de classification des documents | Section 3 |
| 4 | Sortie de données structurées (JSON/tableau) | Section 4 |
| 5 | Rapport récapitulatif du traitement | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Traiter manuellement 200 factures par mois atteint ses limites » |
| Upload | 0:45–1:30 | « Le traitement automatique démarre simplement en plaçant les fichiers » |
| OCR | 1:30–2:30 | « OCR + IA pour la classification des documents et l'extraction de champs » |
| Output | 2:30–3:45 | « Immédiatement utilisable sous forme de données structurées » |
| Report | 3:45–5:00 | « L'évaluation de la confiance indique les points nécessitant une vérification humaine » |

---

## Sample Data Requirements

| # | Données | Utilisation |
|---|--------|------|
| 1 | PDF de factures (10 fichiers) | Objet de traitement principal |
| 2 | PDF de contrats (3 fichiers) | Démonstration de classification de documents |
| 3 | Images de reçus (3 fichiers) | Démonstration d'OCR d'images |
| 4 | Numérisations de faible qualité (2 fichiers) | Démonstration d'évaluation de la confiance |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Temps requis |
|--------|---------|
| Préparation des documents d'exemple | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Intégration automatique avec le système comptable
- Intégration du workflow d'approbation
- Support de documents multilingues (anglais, chinois)

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (OCR Processor) | Extraction de texte de documents via Textract |
| Lambda (Entity Extractor) | Extraction d'entités via Bedrock |
| Lambda (Classifier) | Classification du type de document |
| Amazon Athena | Analyse agrégée des données extraites |

### Fallback

| Scénario | Réponse |
|---------|------|
| Baisse de précision OCR | Utiliser du texte prétraité |
| Latence Bedrock | Afficher des résultats pré-générés |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## À propos de la destination de sortie : FSxN S3 Access Point (Pattern A)

UC2 financial-idp est classé dans **Pattern A: Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : Les résultats OCR des factures, les métadonnées structurées et les résumés BedRock sont tous
écrits via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les PDF de factures originaux.
Aucun bucket S3 standard n'est créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : Alias S3 AP pour la lecture des données d'entrée
- `S3AccessPointOutputAlias` : Alias S3 AP pour l'écriture de sortie (peut être identique à l'entrée)

**Exemple de déploiement** :
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (autres paramètres requis)
```

**Vue depuis les utilisateurs SMB/NFS** :
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # Facture originale
  └── summaries/2026/05/                # Résumé généré par IA (dans le même volume)
      └── invoice_001.json
```

Pour les contraintes liées aux spécifications AWS, consultez
[la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Captures d'écran UI/UX vérifiées

Conformément à la même approche que les démonstrations Phase 7 UC15/16/17 et UC6/11/14, cible les **écrans
UI/UX que les utilisateurs finaux voient réellement dans leurs tâches quotidiennes**. Les vues techniques
(graphe Step Functions, événements de pile CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ⚠️ **Vérification E2E** : Fonctionnalités partielles uniquement (vérification supplémentaire recommandée en production)
- 📸 **Capture UI/UX** : ✅ SFN Graph terminé (Phase 8 Theme D, commit 081cc66)

### Capturé lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC2 (SUCCEEDED)

![Vue graphique Step Functions UC2 (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant
l'état d'exécution de chaque état Lambda / Parallel / Map par couleur.

### Captures d'écran existantes (portions pertinentes des Phases 1-6)

![Vue graphique Step Functions UC2 (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### Écrans UI/UX cibles lors de la revérification (liste de captures recommandées)

- Bucket de sortie S3 (textract-results/, comprehend-entities/, reports/)
- JSON de résultats OCR Textract (champs extraits des contrats et factures)
- Résultats de détection d'entités Comprehend (noms d'organisations, dates, montants)
- Rapport de synthèse généré par Bedrock

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC/S3 AP communs)
   - `UC=financial-idp bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC2` pour déployer

2. **Placement des données d'exemple** :
   - Télécharger des fichiers d'exemple vers le préfixe `invoices/` via l'alias S3 AP
   - Démarrer Step Functions `fsxn-financial-idp-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-financial-idp-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification par e-mail SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py financial-idp-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC2` pour supprimer
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
