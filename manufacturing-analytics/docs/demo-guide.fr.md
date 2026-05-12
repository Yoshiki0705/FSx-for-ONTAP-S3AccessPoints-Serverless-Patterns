# Détection d'anomalies de capteurs IoT et inspection de qualité — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un workflow qui détecte automatiquement les anomalies à partir des données de capteurs IoT de lignes de production et génère des rapports d'inspection qualité.

**Message clé de la démo** : Détection automatique des patterns d'anomalie dans les données de capteurs pour permettre la détection précoce des problèmes de qualité et la maintenance préventive.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Responsable du département de production / Ingénieur contrôle qualité |
| **Tâches quotidiennes** | Surveillance des lignes de production, inspection qualité, planification de la maintenance des équipements |
| **Défis** | Anomalies des données de capteurs manquées, produits défectueux passant aux processus suivants |
| **Résultats attendus** | Détection précoce des anomalies et visualisation des tendances qualité |

### Persona: Suzuki-san (Ingénieur contrôle qualité)

- Surveille 100+ capteurs sur 5 lignes de production
- Les alertes basées sur des seuils génèrent de nombreuses fausses alertes et manquent les vraies anomalies
- « Je veux détecter uniquement les anomalies statistiquement significatives »

---

## Demo Scenario: Analyse par lots de détection d'anomalies de capteurs

### Vue d'ensemble du workflow

```
Données capteurs    Collecte données    Détection anomalies    Rapport qualité
(CSV/Parquet)  →   Prétraitement   →   Analyse statistique  →  Génération IA
                   Normalisation        (Détection valeurs aberrantes)
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Résumé de la narration** :
> 100+ capteurs sur les lignes de production génèrent quotidiennement d'énormes volumes de données. Les alertes à seuil simple génèrent de nombreuses fausses alertes et comportent un risque de manquer les vraies anomalies.

**Key Visual** : Graphique de séries temporelles des données de capteurs, situation de surcharge d'alertes

### Section 2: Data Ingestion (0:45–1:30)

**Résumé de la narration** :
> Lorsque les données de capteurs s'accumulent sur le serveur de fichiers, le pipeline d'analyse démarre automatiquement.

**Key Visual** : Placement des fichiers de données → Démarrage du workflow

### Section 3: Anomaly Detection (1:30–2:30)

**Résumé de la narration** :
> Calcul du score d'anomalie pour chaque capteur par méthodes statistiques (moyenne mobile, écart-type, IQR). Analyse de corrélation entre plusieurs capteurs également exécutée.

**Key Visual** : Exécution de l'algorithme de détection d'anomalies, carte thermique des scores d'anomalie

### Section 4: Quality Inspection (2:30–3:45)

**Résumé de la narration** :
> Analyse des anomalies détectées du point de vue de l'inspection qualité. Identification de la ligne et du processus où le problème s'est produit.

**Key Visual** : Résultats de requête Athena — Distribution des anomalies par ligne et par processus

### Section 5: Report & Action (3:45–5:00)

**Résumé de la narration** :
> L'IA génère un rapport d'inspection qualité. Présentation des causes racines candidates des anomalies et des actions recommandées.

**Key Visual** : Rapport qualité généré par IA (résumé des anomalies + actions recommandées)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Liste des fichiers de données de capteurs | Section 1 |
| 2 | Écran de démarrage du workflow | Section 2 |
| 3 | Progression du traitement de détection d'anomalies | Section 3 |
| 4 | Résultats de requête de distribution des anomalies | Section 4 |
| 5 | Rapport d'inspection qualité IA | Section 5 |

---

## Narration Outline

| Section | Temps | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Les alertes à seuil manquent les vraies anomalies » |
| Ingestion | 0:45–1:30 | « L'analyse démarre automatiquement avec l'accumulation de données » |
| Detection | 1:30–2:30 | « Détection uniquement des anomalies significatives par méthodes statistiques » |
| Inspection | 2:30–3:45 | « Identification des zones problématiques au niveau ligne/processus » |
| Report | 3:45–5:00 | « L'IA présente les causes racines candidates et les contre-mesures » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Données de capteurs normales (5 lignes × 7 jours) | Baseline |
| 2 | Données d'anomalie de température (2 cas) | Démo de détection d'anomalies |
| 3 | Données d'anomalie de vibration (3 cas) | Démo d'analyse de corrélation |
| 4 | Pattern de dégradation qualité (1 cas) | Démo de génération de rapport |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Temps requis |
|--------|---------|
| Génération de données de capteurs d'exemple | 3 heures |
| Vérification de l'exécution du pipeline | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Analyse en streaming temps réel
- Génération automatique de planning de maintenance préventive
- Intégration avec jumeau numérique

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Data Preprocessor) | Normalisation et prétraitement des données de capteurs |
| Lambda (Anomaly Detector) | Détection d'anomalies statistiques |
| Lambda (Report Generator) | Génération de rapport qualité via Bedrock |
| Amazon Athena | Agrégation et analyse des données d'anomalies |

### Fallback

| Scénario | Réponse |
|---------|------|
| Volume de données insuffisant | Utiliser des données pré-générées |
| Précision de détection insuffisante | Afficher les résultats avec paramètres ajustés |

---

*Ce document est un guide de production de vidéo de démo pour présentation technique.*

---

## À propos de la destination de sortie : FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics est classé dans **Pattern A: Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : Les résultats d'analyse des données de capteurs, les rapports de détection d'anomalies et les résultats d'inspection d'images sont tous écrits via FSxN S3 Access Point dans le **même volume FSx ONTAP** que les CSV de capteurs originaux et les images d'inspection. Aucun bucket S3 standard n'est créé (pattern "no data movement").

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias pour la lecture des données d'entrée
- `S3AccessPointOutputAlias` : S3 AP Alias pour l'écriture de sortie (peut être identique à l'entrée)

**Exemple de déploiement** :
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (autres paramètres obligatoires)
```

**Vue depuis les utilisateurs SMB/NFS** :
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # Données de capteurs originales
  └── analysis/2026/05/                 # Résultats de détection d'anomalies IA (même volume)
      └── line_A_report.json
```

Pour les contraintes liées aux spécifications AWS, consultez
[la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant **les écrans UI/UX que les utilisateurs finaux voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de stack CloudFormation, etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ✅ **Exécution E2E** : Confirmée en Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Capturées lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC3, succès d'exécution Lambda confirmés)
- 🔄 **Méthode de reproduction** : Voir le « Guide de capture » à la fin de ce document

### Capturées lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC3 (SUCCEEDED)

![Vue graphique Step Functions UC3 (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant par couleur l'état d'exécution de chaque état Lambda / Parallel / Map.

### Captures d'écran existantes (portions pertinentes de Phase 1-6)

![Vue graphique Step Functions UC3 (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-succeeded.png)

![Graphe Step Functions UC3 (affichage développé)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-expanded.png)

![Graphe Step Functions UC3 (affichage zoomé — détails de chaque étape)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-zoomed.png)

### Écrans UI/UX cibles lors de la revérification (liste de captures recommandées)

- Bucket de sortie S3 (metrics/, anomalies/, reports/)
- Résultats de requête Athena (détection d'anomalies de capteurs IoT)
- Étiquettes d'images d'inspection qualité Rekognition
- Rapport de synthèse qualité de production

### Guide de capture

1. **Préparation** :
   - Vérifier les prérequis avec `bash scripts/verify_phase7_prerequisites.sh` (présence VPC/S3 AP communs)
   - Packager Lambda avec `UC=manufacturing-analytics bash scripts/package_generic_uc.sh`
   - Déployer avec `bash scripts/deploy_generic_ucs.sh UC3`

2. **Placement des données d'exemple** :
   - Uploader des fichiers d'exemple vers le préfixe `sensors/` via S3 AP Alias
   - Démarrer Step Functions `fsxn-manufacturing-analytics-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-manufacturing-analytics-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (référence au format `build/preview_*.html`)
   - Notification email SNS (le cas échéant)

4. **Traitement de masquage** :
   - Masquage automatique avec `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo`
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - Supprimer avec `bash scripts/cleanup_generic_ucs.sh UC3`
   - Libération des ENI Lambda VPC en 15-30 minutes (spécification AWS)
