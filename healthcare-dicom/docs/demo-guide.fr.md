# Flux de travail d'anonymisation DICOM — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un workflow d'anonymisation d'images médicales (DICOM). Elle présente le processus de suppression automatique des informations personnelles des patients pour le partage de données de recherche et la vérification de la qualité de l'anonymisation.

**Message clé de la démo** : Supprimer automatiquement les informations d'identification des patients des fichiers DICOM et générer en toute sécurité des ensembles de données anonymisées utilisables pour la recherche.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Administrateur d'informations médicales / Gestionnaire de données de recherche clinique |
| **Tâches quotidiennes** | Gestion d'images médicales, fourniture de données de recherche, protection de la vie privée |
| **Défis** | L'anonymisation manuelle de grands volumes de fichiers DICOM prend du temps et comporte des risques d'erreur |
| **Résultats attendus** | Automatisation de l'anonymisation sécurisée et fiable avec piste d'audit |

### Persona : Takahashi-san (Gestionnaire de données de recherche clinique)

- Besoin d'anonymiser plus de 10 000 fichiers DICOM pour une recherche collaborative multi-sites
- Suppression fiable requise des noms de patients, ID, dates de naissance, etc.
- « Je veux garantir zéro fuite d'anonymisation tout en maintenant la qualité d'image »

---

## Demo Scenario : Anonymisation DICOM pour le partage de données de recherche

### Vue d'ensemble du workflow

```
Fichiers DICOM     Analyse tags      Traitement          Vérification
(avec infos     →  Extraction    →   Suppression     →   Confirmation
 patients)          métadonnées       infos perso.        anonymisation
                                      Hachage             Génération rapport
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Il est nécessaire d'anonymiser 10 000 fichiers DICOM pour une recherche collaborative multi-sites. Le traitement manuel comporte des risques d'erreur et les fuites d'informations personnelles sont inacceptables.

**Visuel clé** : Liste de fichiers DICOM, mise en évidence des tags d'informations patients

### Section 2 : Workflow Trigger (0:45–1:30)

**Résumé de la narration** :
> Spécifier l'ensemble de données à anonymiser et déclencher le workflow d'anonymisation. Configurer les règles d'anonymisation (suppression, hachage, généralisation).

**Visuel clé** : Déclenchement du workflow, écran de configuration des règles d'anonymisation

### Section 3 : De-identification (1:30–2:30)

**Résumé de la narration** :
> Traitement automatique des tags d'informations personnelles de chaque fichier DICOM. Nom du patient → hachage, date de naissance → tranche d'âge, nom de l'établissement → code anonyme. Les données de pixels d'image sont conservées.

**Visuel clé** : Progression du traitement d'anonymisation, avant/après de la conversion des tags

### Section 4 : Quality Verification (2:30–3:45)

**Résumé de la narration** :
> Vérification automatique des fichiers après anonymisation. Scanner tous les tags pour détecter d'éventuelles informations personnelles résiduelles. Vérifier également l'intégrité des images.

**Visuel clé** : Résultats de vérification — taux de réussite de l'anonymisation, liste des tags à risque résiduel

### Section 5 : Audit Report (3:45–5:00)

**Résumé de la narration** :
> Génération automatique d'un rapport d'audit du traitement d'anonymisation. Enregistrement du nombre de traitements, du nombre de tags supprimés et des résultats de vérification. Utilisable comme document de soumission au comité d'éthique de la recherche.

**Visuel clé** : Rapport d'audit (résumé du traitement + piste de conformité)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste de fichiers DICOM (avant anonymisation) | Section 1 |
| 2 | Déclenchement du workflow et configuration des règles | Section 2 |
| 3 | Progression du traitement d'anonymisation | Section 3 |
| 4 | Résultats de vérification de qualité | Section 4 |
| 5 | Rapport d'audit | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Les fuites d'anonymisation de grands volumes DICOM sont inacceptables » |
| Trigger | 0:45–1:30 | « Configurer les règles d'anonymisation et déclencher le workflow » |
| Processing | 1:30–2:30 | « Suppression automatique des tags d'infos personnelles, qualité d'image maintenue » |
| Verification | 2:30–3:45 | « Scanner tous les tags pour confirmer zéro fuite d'anonymisation » |
| Report | 3:45–5:00 | « Génération automatique de piste d'audit, soumission possible au comité d'éthique » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Fichiers DICOM de test (20 fichiers) | Cible de traitement principale |
| 2 | DICOM avec structure de tags complexe (5 fichiers) | Cas limites |
| 3 | DICOM contenant des tags privés (3 fichiers) | Vérification à haut risque |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Temps requis |
|--------|---------|
| Préparation des données DICOM de test | 3 heures |
| Confirmation de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Détection et suppression automatiques du texte dans l'image (burn-in)
- Gestion du mapping d'anonymisation via intégration FHIR
- Anonymisation différentielle (traitement incrémental de données supplémentaires)

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Tag Parser) | Analyse des tags DICOM et détection d'informations personnelles |
| Lambda (De-identifier) | Traitement d'anonymisation des tags |
| Lambda (Verifier) | Vérification de la qualité de l'anonymisation |
| Lambda (Report Generator) | Génération de rapport d'audit |

### Fallback

| Scénario | Réponse |
|---------|------|
| Échec du parsing DICOM | Utiliser des données prétraitées |
| Erreur de vérification | Basculer vers un flux de confirmation manuelle |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## À propos de la destination de sortie : FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom est classé comme **Pattern A: Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : Les métadonnées DICOM, les résultats d'anonymisation et les journaux de détection PII sont tous écrits
via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les images médicales DICOM originales. Aucun bucket S3 standard n'est
créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias pour la lecture des données d'entrée
- `S3AccessPointOutputAlias` : S3 AP Alias pour l'écriture de sortie (peut être identique à l'entrée)

**Exemple de déploiement** :
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (autres paramètres requis)
```

**Vue depuis les utilisateurs SMB/NFS** :
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # DICOM original
  └── metadata/patient_001/             # Résultats d'anonymisation AI (même volume)
      └── study_A_anonymized.json
```

Pour les contraintes liées aux spécifications AWS, consultez
[la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14 : cibler **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de stack CloudFormation,
etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ⚠️ **Vérification E2E** : Fonctionnalités partielles uniquement (vérification supplémentaire recommandée en production)
- 📸 **Capture UI/UX** : ✅ SFN Graph terminé (Phase 8 Theme D, commit c66084f)

### Captures lors de la vérification de redéploiement du 2026-05-10 (centré UI/UX)

#### Vue graphique Step Functions UC5 (SUCCEEDED)

![Vue graphique Step Functions UC5 (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

La vue graphique Step Functions visualise par couleur l'état d'exécution de chaque état Lambda / Parallel / Map,
écran le plus important pour l'utilisateur final.

### Captures d'écran existantes (portions pertinentes des Phases 1-6)

![Vue graphique Step Functions UC5 (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![Graphique Step Functions UC5 (vue zoomée — détails de chaque étape)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de captures recommandées)

- Bucket de sortie S3 (dicom-metadata/, deid-reports/, diagnoses/)
- Résultats de détection d'entités Comprehend Medical (Cross-Region)
- JSON de métadonnées DICOM anonymisées

### Guide de capture

1. **Préparation** :
   - `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis (VPC/S3 AP communs)
   - `UC=healthcare-dicom bash scripts/package_generic_uc.sh` pour packager Lambda
   - `bash scripts/deploy_generic_ucs.sh UC5` pour déployer

2. **Placement des données d'exemple** :
   - Télécharger des fichiers d'exemple via S3 AP Alias vers le préfixe `dicom/`
   - Démarrer Step Functions `fsxn-healthcare-dicom-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-healthcare-dicom-demo-output-<account>`
   - Aperçu JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - `python3 scripts/mask_uc_demos.py healthcare-dicom-demo` pour masquage automatique
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - `bash scripts/cleanup_generic_ucs.sh UC5` pour supprimer
   - Libération ENI Lambda VPC en 15-30 minutes (spécification AWS)
