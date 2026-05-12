# Détection des modifications de modèle BIM et conformité de sécurité — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline de détection de modifications de modèles BIM et de vérification de conformité en matière de sécurité. Elle détecte automatiquement les modifications de conception et vérifie la conformité aux normes de construction.

**Message clé de la démo** : Suivi automatique des modifications de modèles BIM et détection instantanée des violations des normes de sécurité. Réduction du cycle de révision de conception.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Gestionnaire BIM / Ingénieur en conception structurelle |
| **Tâches quotidiennes** | Gestion des modèles BIM, révision des modifications de conception, vérification de conformité |
| **Défis** | Difficulté à suivre les modifications de conception de plusieurs équipes et à vérifier la conformité aux normes |
| **Résultats attendus** | Efficacité accrue de la détection automatique des modifications et de la vérification des normes de sécurité |

### Persona : Kimura-san (Gestionnaire BIM)

- Travail en parallèle de plus de 20 équipes de conception sur un projet de construction à grande échelle
- Nécessité de vérifier que les modifications de conception quotidiennes n'affectent pas les normes de sécurité
- « Je veux lancer automatiquement des vérifications de sécurité lorsqu'il y a des modifications »

---

## Demo Scenario : Détection automatique des modifications de conception et vérification de sécurité

### Vue d'ensemble du workflow

```
Mise à jour modèle BIM    Détection modifications    Conformité           Rapport de révision
(IFC/RVT)            →    Analyse différentielle  →  Vérification règles → Génération IA
                          Comparaison éléments       Vérification normes sécurité
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Dans un projet à grande échelle, 20 équipes mettent à jour les modèles BIM en parallèle. La vérification manuelle ne peut pas suivre pour s'assurer que les modifications ne violent pas les normes de sécurité.

**Visuel clé** : Liste des fichiers de modèles BIM, historique des mises à jour de plusieurs équipes

### Section 2 : Change Detection (0:45–1:30)

**Résumé de la narration** :
> Détection des mises à jour de fichiers de modèles et analyse automatique des différences avec la version précédente. Identification des éléments modifiés (composants structurels, disposition des équipements, etc.).

**Visuel clé** : Déclencheur de détection de modifications, début de l'analyse différentielle

### Section 3 : Compliance Check (1:30–2:30)

**Résumé de la narration** :
> Vérification automatique des règles de normes de sécurité pour les éléments modifiés. Vérification de la conformité aux normes sismiques, aux zones coupe-feu, aux voies d'évacuation, etc.

**Visuel clé** : Traitement de vérification des règles en cours, liste des éléments de vérification

### Section 4 : Results Analysis (2:30–3:45)

**Résumé de la narration** :
> Vérification des résultats de validation. Affichage de la liste des éléments en violation, de la portée de l'impact et du niveau de gravité.

**Visuel clé** : Tableau des résultats de détection de violations, classification par niveau de gravité

### Section 5 : Review Report (3:45–5:00)

**Résumé de la narration** :
> L'IA génère un rapport de révision de conception. Présentation des détails des violations, des propositions de correction et des autres éléments de conception affectés.

**Visuel clé** : Rapport de révision généré par IA

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des fichiers de modèles BIM | Section 1 |
| 2 | Détection de modifications / Affichage des différences | Section 2 |
| 3 | Progression de la vérification de conformité | Section 3 |
| 4 | Résultats de détection de violations | Section 4 |
| 5 | Rapport de révision IA | Section 5 |

---

## Narration Outline

| Section | Temps | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Le suivi des modifications et la vérification de sécurité du travail en parallèle ne peuvent pas suivre » |
| Detection | 0:45–1:30 | « Détection automatique des mises à jour de modèles et analyse des différences » |
| Compliance | 1:30–2:30 | « Vérification automatique des règles de normes de sécurité » |
| Results | 2:30–3:45 | « Compréhension instantanée des éléments en violation et de la portée de l'impact » |
| Report | 3:45–5:00 | « L'IA présente les propositions de correction et l'analyse d'impact » |

---

## Sample Data Requirements

| # | Données | Utilisation |
|---|--------|------|
| 1 | Modèle BIM de base (format IFC) | Source de comparaison |
| 2 | Modèle après modification (avec modifications structurelles) | Démo de détection de différences |
| 3 | Modèle avec violations des normes de sécurité (3 cas) | Démo de conformité |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Temps requis |
|--------|---------|
| Préparation des données BIM d'exemple | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Intégration de visualisation 3D
- Notification de modifications en temps réel
- Vérification de cohérence avec la phase de construction

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Change Detector) | Analyse différentielle des modèles BIM |
| Lambda (Compliance Checker) | Vérification des règles de normes de sécurité |
| Lambda (Report Generator) | Génération de rapport de révision via Bedrock |
| Amazon Athena | Agrégation de l'historique des modifications et des données de violations |

### Fallback

| Scénario | Réponse |
|---------|------|
| Échec de l'analyse IFC | Utiliser des données pré-analysées |
| Retard de vérification des règles | Afficher les résultats pré-vérifiés |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## À propos de la destination de sortie : Sélectionnable avec OutputDestination (Pattern B)

UC10 construction-bim prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-10
(voir `docs/output-destination-patterns.md`).

**Charges de travail concernées** : BIM de construction / OCR de plans / Vérification de conformité en matière de sécurité

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats IA.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (autres paramètres requis)
```

### FSXN_S3AP (pattern "no data movement")
Écrit les résultats IA via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les données originales.
Les utilisateurs SMB/NFS peuvent consulter directement les résultats IA dans la structure de répertoires
qu'ils utilisent pour leur travail. Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (autres paramètres requis)
```

**Notes importantes** :

- Spécification de `S3AccessPointName` fortement recommandée (autoriser IAM pour les formats Alias et ARN)
- Les objets de plus de 5 Go ne sont pas possibles avec FSxN S3AP (spécification AWS), téléchargement multipart obligatoire
- Les contraintes de spécification AWS sont décrites dans
  [la section "Contraintes de spécification AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de pile CloudFormation,
etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ✅ **Exécution E2E** : Confirmée dans Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Photographié lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC10, succès d'exécution Lambda confirmé)
- 🔄 **Méthode de reproduction** : Voir le « Guide de prise de vue » à la fin de ce document

### Photographié lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC10 (SUCCEEDED)

![Vue graphique Step Functions UC10 (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant par couleur
l'état d'exécution de chaque état Lambda / Parallel / Map.

### Captures d'écran existantes (portions applicables de Phase 1-6)

![Vue graphique Step Functions UC10 (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![Graphe Step Functions UC10 (affichage zoomé — détails de chaque étape)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de prise de vue recommandée)

- Bucket de sortie S3 (drawings-ocr/, bim-metadata/, safety-reports/)
- Résultats OCR de plans Textract (Cross-Region)
- Rapport de différences de versions BIM
- Vérification de conformité en matière de sécurité Bedrock

### Guide de prise de vue

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC commun/S3 AP présent)
   - `UC=construction-bim bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC10` pour déployer

2. **Placement des données d'exemple** :
   - Télécharger des fichiers d'exemple via S3 AP Alias vers le préfixe `drawings/`
   - Démarrer Step Functions `fsxn-construction-bim-demo-workflow` (entrée `{}`)

3. **Prise de vue** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-construction-bim-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification par e-mail SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py construction-bim-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC10` pour supprimer
   - Libération ENI Lambda VPC en 15-30 minutes (spécification AWS)
