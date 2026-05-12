# Guide de démonstration de l'audit des permissions du serveur de fichiers

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Executive Summary

Cette démo illustre un workflow d'audit automatisé pour détecter les permissions d'accès excessives sur les serveurs de fichiers. Elle analyse les ACL NTFS, identifie les entrées violant le principe du moindre privilège et génère automatiquement des rapports de conformité.

**Message clé de la démo** : Automatiser l'audit des permissions de serveur de fichiers qui prendrait manuellement plusieurs semaines, et visualiser instantanément les risques liés aux permissions excessives.

**Durée estimée** : 3 à 5 minutes

---

## Target Audience & Persona

| Élément | Détails |
|------|------|
| **Poste** | Responsable de la sécurité de l'information / Administrateur de conformité IT |
| **Tâches quotidiennes** | Révision des permissions d'accès, réponse aux audits, gestion des politiques de sécurité |
| **Défis** | Vérifier manuellement les permissions de milliers de dossiers est irréaliste |
| **Résultats attendus** | Détection précoce des permissions excessives et automatisation de la traçabilité de conformité |

### Persona : M. Sato (Administrateur de sécurité de l'information)

- Révision des permissions de tous les dossiers partagés requise pour l'audit annuel
- Souhaite détecter instantanément les configurations dangereuses telles que « Everyone Full Control »
- Souhaite créer efficacement des rapports à soumettre aux cabinets d'audit

---

## Demo Scenario : Automatisation de l'audit annuel des permissions

### Vue d'ensemble du workflow

```
Serveur de fichiers    Collecte ACL      Analyse permissions    Génération rapport
(Partage NTFS)    →   Extraction     →   Détection         →    Rapport d'audit
                      métadonnées        violations            (Résumé IA)
                                         (Vérif. règles)
```

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Résumé de la narration** :
> C'est la période de l'audit annuel. Une révision des permissions est nécessaire pour des milliers de dossiers partagés, mais la vérification manuelle prendrait plusieurs semaines. Si les permissions excessives sont laissées sans surveillance, le risque de fuite d'informations augmente.

**Visuel clé** : Structure de dossiers volumineuse avec superposition « Audit manuel : estimation 3 à 4 semaines »

### Section 2 : Workflow Trigger (0:45–1:30)

**Résumé de la narration** :
> Spécifier le volume à auditer et déclencher le workflow d'audit des permissions.

**Visuel clé** : Écran d'exécution Step Functions, spécification du chemin cible

### Section 3 : ACL Analysis (1:30–2:30)

**Résumé de la narration** :
> Collecte automatique des ACL NTFS de chaque dossier et détection des violations selon les règles suivantes :
> - Permissions excessives pour Everyone / Authenticated Users
> - Accumulation d'héritages inutiles
> - Persistance de comptes d'employés partis

**Visuel clé** : Progression du scan ACL par traitement parallèle

### Section 4 : Results Review (2:30–3:45)

**Résumé de la narration** :
> Interroger les résultats de détection avec SQL. Vérifier le nombre de violations et la distribution par niveau de risque.

**Visuel clé** : Résultats de requête Athena — tableau de liste des violations

### Section 5 : Compliance Report (3:45–5:00)

**Résumé de la narration** :
> L'IA génère automatiquement un rapport d'audit. Présente l'évaluation des risques, les réponses recommandées et les actions priorisées.

**Visuel clé** : Rapport d'audit généré (résumé des risques + recommandations de réponse)

---

## Screen Capture Plan

| # | Écran | Section |
|---|------|-----------|
| 1 | Structure de dossiers du serveur de fichiers | Section 1 |
| 2 | Démarrage de l'exécution du workflow | Section 2 |
| 3 | Traitement parallèle du scan ACL en cours | Section 3 |
| 4 | Résultats de requête de détection de violations Athena | Section 4 |
| 5 | Rapport d'audit généré par IA | Section 5 |

---

## Narration Outline

| Section | Temps | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Auditer manuellement les permissions de milliers de dossiers est irréaliste » |
| Trigger | 0:45–1:30 | « Spécifier le volume cible et démarrer l'audit » |
| Analysis | 1:30–2:30 | « Collecter automatiquement les ACL et détecter les violations de politique » |
| Results | 2:30–3:45 | « Comprendre instantanément le nombre de violations et le niveau de risque » |
| Report | 3:45–5:00 | « Générer automatiquement un rapport d'audit, présenter les priorités de réponse » |

---

## Sample Data Requirements

| # | Données | Usage |
|---|--------|------|
| 1 | Dossiers avec permissions normales (50+) | Référence de base |
| 2 | Configuration Everyone Full Control (5 cas) | Violation à haut risque |
| 3 | Persistance de comptes d'employés partis (3 cas) | Violation à risque moyen |
| 4 | Dossiers avec héritage excessif (10 cas) | Violation à faible risque |

---

## Timeline

### Réalisable en 1 semaine

| Tâche | Temps requis |
|--------|---------|
| Génération de données ACL d'exemple | 2 heures |
| Vérification de l'exécution du workflow | 2 heures |
| Capture d'écran | 2 heures |
| Rédaction du script de narration | 2 heures |
| Montage vidéo | 4 heures |

### Future Enhancements

- Détection automatique des employés partis via intégration Active Directory
- Surveillance en temps réel des changements de permissions
- Exécution automatique des actions correctives

---

## Technical Notes

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration du workflow |
| Lambda (ACL Collector) | Collecte des métadonnées ACL NTFS |
| Lambda (Policy Checker) | Vérification des règles de violation de politique |
| Lambda (Report Generator) | Génération de rapport d'audit via Bedrock |
| Amazon Athena | Analyse SQL des données de violation |

### Fallback

| Scénario | Réponse |
|---------|------|
| Échec de collecte ACL | Utiliser les données pré-collectées |
| Latence Bedrock | Afficher un rapport pré-généré |

---

*Ce document est un guide de production de vidéo de démo pour présentation technique.*

---

## À propos de la destination de sortie : FSxN S3 Access Point (Pattern A)

UC1 legal-compliance est classé comme **Pattern A: Native S3AP Output**
(voir `docs/output-destination-patterns.md`).

**Conception** : Les métadonnées de contrat, les journaux d'audit et les rapports de synthèse sont tous écrits
via FSxN S3 Access Point dans **le même volume FSx ONTAP** que les données de contrat originales. Aucun bucket S3
standard n'est créé (pattern « no data movement »).

**Paramètres CloudFormation** :
- `S3AccessPointAlias` : S3 AP Alias pour la lecture des données de contrat en entrée
- `S3AccessPointOutputAlias` : S3 AP Alias pour l'écriture en sortie (peut être identique à l'entrée)

**Exemple de déploiement** :
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (autres paramètres requis)
```

**Vue depuis les utilisateurs SMB/NFS** :
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # Contrat original
  └── summaries/2026/05/                # Résumé généré par IA (dans le même volume)
      └── contract_ABC.json
```

Pour les contraintes liées aux spécifications AWS, consultez
[la section « Contraintes des spécifications AWS et solutions de contournement » du README du projet](../../README.md#aws-仕様上の制約と回避策)
et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14 : cibler **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de pile CloudFormation,
etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'usage

- ✅ **Exécution E2E** : Confirmée en Phase 1-6 (voir README racine)
- 📸 **Reprise de photos UI/UX** : ✅ Photographié lors de la vérification de redéploiement du 2026-05-10 (graphe Step Functions UC1, succès d'exécution Lambda confirmés)
- 🔄 **Méthode de reproduction** : Voir « Guide de capture » à la fin de ce document

### Photographié lors de la vérification de redéploiement du 2026-05-10 (centré sur UI/UX)

#### Vue graphique Step Functions UC1 (SUCCEEDED)

![Vue graphique Step Functions UC1 (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

La vue graphique Step Functions est l'écran le plus important pour l'utilisateur final, visualisant par couleur
l'état d'exécution de chaque état Lambda / Parallel / Map.

#### Graphe Step Functions UC1 (SUCCEEDED — Vérification Phase 8 Theme D/E/N, 2:38:20)

![Graphe Step Functions UC1 (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-succeeded.png)

Exécuté avec Phase 8 Theme E (event-driven) + Theme N (observability) activés.
549 itérations ACL, 3871 événements, toutes les étapes SUCCEEDED en 2:38:20.

#### Graphe Step Functions UC1 (Vue zoomée — Détails de chaque étape)

![Graphe Step Functions UC1 (Vue zoomée)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-zoomed.png)

#### Points d'accès S3 UC1 pour FSx ONTAP (Affichage console)

![Points d'accès S3 UC1 pour FSx ONTAP](../../docs/screenshots/masked/uc1-demo/s3-access-points-for-fsx.png)

#### Détails du point d'accès S3 UC1 (Vue d'ensemble)

![Détails du point d'accès S3 UC1](../../docs/screenshots/masked/uc1-demo/s3ap-detail-overview.png)

### Captures d'écran existantes (parties pertinentes de Phase 1-6)

#### Déploiement de pile CloudFormation UC1 terminé (lors de la vérification du 2026-05-02)

![Déploiement de pile CloudFormation UC1 terminé (lors de la vérification du 2026-05-02)](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### Step Functions UC1 SUCCEEDED (Succès d'exécution E2E)

![Step Functions UC1 SUCCEEDED (Succès d'exécution E2E)](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (préfixes audit-reports/, acl-audits/, athena-results/)
- Résultats de requête Athena (SQL de détection de violations ACL)
- Rapport d'audit généré par Bedrock (résumé des violations de conformité)
- E-mail de notification SNS (alerte d'audit)

### Guide de capture

1. **Préparation** :
   - Vérifier les prérequis avec `bash scripts/verify_phase7_prerequisites.sh` (présence VPC/S3 AP communs)
   - Packager Lambda avec `UC=legal-compliance bash scripts/package_generic_uc.sh`
   - Déployer avec `bash scripts/deploy_generic_ucs.sh UC1`

2. **Placement des données d'exemple** :
   - Télécharger des fichiers d'exemple vers le préfixe `contracts/` via S3 AP Alias
   - Démarrer Step Functions `fsxn-legal-compliance-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-legal-compliance-demo-output-<account>`
   - Aperçu du JSON de sortie AI/ML (se référer au format `build/preview_*.html`)
   - Notification e-mail SNS (le cas échéant)

4. **Traitement de masquage** :
   - Masquage automatique avec `python3 scripts/mask_uc_demos.py legal-compliance-demo`
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - Supprimer avec `bash scripts/cleanup_generic_ucs.sh UC1`
   - Libération ENI Lambda VPC en 15-30 min (spécification AWS)

---

## Estimation du temps d'exécution (résultats de vérification Phase 8)

Le temps de traitement UC1 est proportionnel au nombre de fichiers sur le volume ONTAP.

| Étape | Contenu du traitement | Valeur mesurée (549 fichiers) |
|---------|---------|---------------------|
| Discovery | Obtention de la liste de fichiers via API REST ONTAP | 8 min |
| AclCollection (Map) | Collecte ACL NTFS de chaque fichier | 2 heures 20 min |
| AthenaAnalysis | Glue Data Catalog + requête Athena | 5 min |
| ReportGeneration | Génération de rapport avec Bedrock Nova Lite | 5 min |
| **Total** | | **2 heures 38 min** |

### Temps de traitement estimé par nombre de fichiers

| Nombre de fichiers | Temps total estimé | Usage recommandé |
|-----------|------------|---------|
| 10 | ~5 min | Démo rapide |
| 50 | ~15 min | Démo standard |
| 100 | ~30 min | Vérification détaillée |
| 500+ | ~2,5 heures | Test équivalent production |

### Conseils d'optimisation des performances

- **Map state MaxConcurrency** : Augmenter de 40 (par défaut) à 100 peut réduire le temps AclCollection
- **Mémoire Lambda** : 512 MB ou plus recommandé pour Discovery Lambda (accélération de l'attachement ENI VPC)
- **Timeout Lambda** : 900s recommandé pour les environnements avec beaucoup de fichiers (300s par défaut insuffisant)
- **SnapStart** : Python 3.13 + SnapStart peut réduire le démarrage à froid de 50-80%

### Nouvelles fonctionnalités Phase 8

- **Déclencheur event-driven** (`EnableEventDriven=true`) : Démarrage automatique lors de l'ajout de fichiers à S3AP
- **Alarmes CloudWatch** (`EnableCloudWatchAlarms=true`) : Notification automatique des échecs SFN + erreurs Lambda
- **Notification d'échec EventBridge** : Notification push vers SNS Topic en cas d'échec d'exécution
