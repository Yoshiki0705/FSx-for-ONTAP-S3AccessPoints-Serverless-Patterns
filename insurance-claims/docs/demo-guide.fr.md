# Rapport d'évaluation des dommages par photos d'accident et d'indemnisation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un pipeline automatisé d'évaluation des dommages et de génération de rapports de réclamation d'assurance à partir de photos d'accident. L'analyse d'images et la génération de rapports par IA rationalisent le processus d'évaluation.

**Message clé de la démo** : L'IA analyse automatiquement les photos d'accident, évalue le degré des dommages et génère instantanément des rapports de réclamation d'assurance.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Expert en évaluation des dommages / Expert en sinistres |
| **Tâches quotidiennes** | Vérification des photos d'accident, évaluation des dommages, calcul des indemnités, rédaction de rapports |
| **Défis** | Nécessité de traiter rapidement un grand volume de dossiers de réclamation |
| **Résultats attendus** | Accélération du processus d'évaluation et garantie de cohérence |

### Persona: M. Kobayashi (Expert en évaluation des dommages)

- Traite plus de 100 réclamations d'assurance par mois
- Évalue le degré des dommages à partir de photos et rédige des rapports
- « Je souhaite automatiser l'évaluation initiale pour me concentrer sur les dossiers complexes »

---

## Demo Scenario: Évaluation des dommages d'accident automobile

### Vue d'ensemble du workflow

```
Photos d'accident    Analyse d'images    Évaluation         Rapport de
(plusieurs)      →   Détection dommages → Jugement degré → réclamation
                     Identification zone  Estimation coût   Généré par IA
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Résumé de la narration** :
> Plus de 100 réclamations d'assurance par mois. Pour chaque dossier, vérifier plusieurs photos d'accident, évaluer le degré des dommages et rédiger un rapport. Le traitement manuel ne suffit plus.

**Key Visual** : Liste des dossiers de réclamation d'assurance, échantillons de photos d'accident

### Section 2: Photo Upload (0:45–1:30)

**Résumé de la narration** :
> Lorsque les photos d'accident sont téléchargées, le pipeline d'évaluation automatique se déclenche. Traitement par dossier.

**Key Visual** : Téléchargement de photos → Déclenchement automatique du workflow

### Section 3: Damage Detection (1:30–2:30)

**Résumé de la narration** :
> L'IA analyse les photos et détecte les zones endommagées. Identifie le type de dommage (bosselure, rayure, casse) et la zone (pare-chocs, portière, aile, etc.).

**Key Visual** : Résultats de détection des dommages, cartographie des zones

### Section 4: Assessment (2:30–3:45)

**Résumé de la narration** :
> Évalue le degré des dommages, détermine réparation/remplacement et calcule le montant estimé. Comparaison avec des dossiers similaires antérieurs également effectuée.

**Key Visual** : Tableau des résultats d'évaluation des dommages, estimation du montant

### Section 5: Claims Report (3:45–5:00)

**Résumé de la narration** :
> L'IA génère automatiquement le rapport de réclamation d'assurance. Inclut le résumé des dommages, le montant estimé et les actions recommandées. L'expert en évaluation n'a qu'à vérifier et approuver.

**Key Visual** : Rapport de réclamation généré par IA (résumé des dommages + estimation du montant)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des dossiers de réclamation | Section 1 |
| 2 | Téléchargement de photos · Déclenchement du pipeline | Section 2 |
| 3 | Résultats de détection des dommages | Section 3 |
| 4 | Évaluation des dommages · Estimation du montant | Section 4 |
| 5 | Rapport de réclamation d'assurance | Section 5 |

---

## Narration Outline

| Section | Durée | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Évaluer manuellement 100 réclamations par mois est impossible » |
| Upload | 0:45–1:30 | « Le téléchargement de photos lance l'évaluation automatique » |
| Detection | 1:30–2:30 | « L'IA détecte automatiquement les zones et types de dommages » |
| Assessment | 2:30–3:45 | « Estimation automatique du degré des dommages et du coût de réparation » |
| Report | 3:45–5:00 | « Génération automatique du rapport de réclamation, vérification et approbation uniquement » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Photos de dommages mineurs (5 cas) | Démo d'évaluation de base |
| 2 | Photos de dommages modérés (3 cas) | Démo de précision d'évaluation |
| 3 | Photos de dommages graves (2 cas) | Démo de jugement de perte totale |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Durée |
|--------|---------|
| Préparation des données photos échantillons | 2 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écrans | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Détection des dommages à partir de vidéos
- Rapprochement automatique avec les devis des ateliers de réparation
- Détection des réclamations frauduleuses

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Image Analyzer) | Détection des dommages via Bedrock/Rekognition |
| Lambda (Damage Assessor) | Évaluation du degré des dommages · Estimation du montant |
| Lambda (Report Generator) | Génération du rapport de réclamation via Bedrock |
| Amazon Athena | Référence · Comparaison avec les données de dossiers antérieurs |

### Fallback

| Scénario | Action |
|---------|------|
| Précision d'analyse d'images insuffisante | Utiliser des résultats pré-analysés |
| Latence Bedrock | Afficher un rapport pré-généré |

---

*Ce document est un guide de production de vidéo de démonstration pour présentation technique.*

---

## Captures d'écran UI/UX vérifiées (Validation AWS 2026-05-10)

Même approche que Phase 7 : capture des **écrans UI/UX réellement utilisés par les experts en évaluation d'assurance dans leur travail quotidien**.
Écrans techniques (graphes Step Functions, etc.) exclus.

### Choix de la destination de sortie : S3 standard vs FSxN S3AP

UC14 prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-10.
**Réécrire les résultats IA dans le même volume FSx** permet aux responsables du traitement des réclamations
de consulter les JSON d'évaluation des dommages, résultats OCR et rapports de réclamation
dans la structure de répertoires du dossier de réclamation
(pattern "no data movement", également avantageux du point de vue de la protection PII).

```bash
# Mode STANDARD_S3 (par défaut, comportement traditionnel)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# Mode FSXN_S3AP (réécriture des résultats IA dans le volume FSx ONTAP)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

Pour les contraintes de spécification AWS et solutions de contournement, voir [la section "Contraintes de spécification AWS et solutions de contournement"
du README du projet](../../README.md#aws-仕様上の制約と回避策).

### 1. Rapport de réclamation d'assurance — Résumé pour l'expert en évaluation

Rapport intégrant l'analyse Rekognition des photos d'accident + OCR Textract du devis + jugement de recommandation d'évaluation.
Jugement `MANUAL_REVIEW` + confiance 75%, l'expert examine les éléments non automatisables.

<!-- SCREENSHOT: uc14-claims-report.png
     Contenu: Rapport de réclamation d'assurance (ID réclamation, résumé dommages, corrélation devis, jugement recommandé)
            + Liste des labels détectés Rekognition + Résultats OCR Textract
     Masqué: ID compte, nom bucket -->
![UC14: Rapport de réclamation d'assurance](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. Bucket de sortie S3 — Vue d'ensemble des artefacts d'évaluation

Écran où l'expert en évaluation vérifie les artefacts par dossier de réclamation.
`assessments/` (analyse Rekognition) + `estimates/` (OCR Textract) + `reports/` (rapport intégré).

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     Contenu: Console S3 avec préfixes assessments/, estimates/, reports/
     Masqué: ID compte -->
![UC14: Bucket de sortie S3](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### Valeurs mesurées (Validation de déploiement AWS 2026-05-10)

- **Exécution Step Functions** : SUCCEEDED
- **Rekognition** : Détection sur photo d'accident `Maroon` 90.79%, `Business Card` 84.51%, etc.
- **Textract** : OCR du PDF de devis via cross-region us-east-1, extraction `Total: 1270.00 USD`, etc.
- **Artefacts générés** : assessments/*.json, estimates/*.json, reports/*.txt
- **Stack réelle** : `fsxn-insurance-claims-demo` (ap-northeast-1, validation 2026-05-10)
