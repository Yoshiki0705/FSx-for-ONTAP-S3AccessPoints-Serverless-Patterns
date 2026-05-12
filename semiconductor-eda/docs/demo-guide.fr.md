# Guide de démonstration — Validation des fichiers de conception EDA

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Résumé exécutif

Ce guide définit une démonstration technique destinée aux ingénieurs de conception de semi-conducteurs. La démo illustre un workflow automatisé de validation de la qualité des fichiers de conception (GDS/OASIS) et démontre la valeur de l'efficacité des revues de conception avant le tape-out.

**Message central de la démo** : Les vérifications de qualité inter-blocs IP, auparavant effectuées manuellement par les ingénieurs de conception, sont désormais réalisées en quelques minutes grâce à un workflow automatisé, permettant une action immédiate basée sur des rapports de revue de conception générés par IA.

**Durée estimée** : 3 à 5 minutes (vidéo de capture d'écran avec narration)

---

## Public cible & Persona

### Public principal : Utilisateurs finaux EDA (ingénieurs de conception)

| Élément | Détails |
|------|------|
| **Poste** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tâches quotidiennes** | Conception de layout, exécution DRC, intégration de blocs IP, préparation du tape-out |
| **Défis** | Temps nécessaire pour obtenir une vue transversale de la qualité de plusieurs blocs IP |
| **Environnement d'outils** | Outils EDA tels que Calibre, Virtuoso, IC Compiler, Innovus, etc. |
| **Résultats attendus** | Détection précoce des problèmes de qualité de conception et respect du calendrier de tape-out |

### Persona : Tanaka-san (Physical Design Lead)

- Gère plus de 40 blocs IP dans un projet SoC à grande échelle
- Doit effectuer une revue de qualité de tous les blocs 2 semaines avant le tape-out
- La vérification individuelle des fichiers GDS/OASIS de chaque bloc est irréaliste
- « Je veux avoir une vue d'ensemble du résumé de qualité de tous les blocs en un coup d'œil »

---

## Scénario de démo : Revue de qualité pré-tape-out

### Vue d'ensemble du scénario

Lors de la phase de revue de qualité avant le tape-out, le design lead exécute une validation de qualité automatisée sur plusieurs blocs IP (plus de 40 fichiers) et prend des décisions d'action basées sur un rapport de revue généré par IA.

### Vue d'ensemble du workflow

```
Fichiers de conception    Validation          Résultats          Revue IA
(GDS/OASIS)          →   automatisée    →    d'analyse     →    Génération
                         Déclenchement       (Athena SQL)       de rapport
                         du workflow         Agrégation         (langage naturel)
                                            statistique
```

### Valeur démontrée

1. **Gain de temps** : Revue transversale complétée en quelques minutes au lieu de plusieurs jours manuellement
2. **Exhaustivité** : Validation de tous les blocs IP sans omission
3. **Jugement quantitatif** : Évaluation objective de la qualité par détection statistique des valeurs aberrantes (méthode IQR)
4. **Actionnable** : L'IA fournit des recommandations d'action concrètes

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Énoncé du problème (0:00–0:45)

**Écran** : Liste des fichiers du projet de conception (plus de 40 fichiers GDS/OASIS)

**Résumé de la narration** :
> 2 semaines avant le tape-out. Il faut vérifier la qualité de conception de plus de 40 blocs IP.
> Ouvrir et vérifier chaque fichier individuellement avec des outils EDA n'est pas réaliste.
> Anomalies du nombre de cellules, valeurs aberrantes des bounding boxes, violations des conventions de nommage — nous avons besoin d'une méthode pour détecter ces problèmes de manière transversale.

**Visuel clé** :
- Structure de répertoire des fichiers de conception (.gds, .gds2, .oas, .oasis)
- Superposition de texte « Revue manuelle : 3 à 5 jours estimés »

---

### Section 2 : Déclenchement du workflow (0:45–1:30)

**Écran** : Opération de déclenchement du workflow de validation de qualité par l'ingénieur de conception

**Résumé de la narration** :
> Après avoir atteint le jalon de conception, le workflow de validation de qualité est lancé.
> Il suffit de spécifier le répertoire cible pour démarrer la validation automatisée de tous les fichiers de conception.

**Visuel clé** :
- Écran d'exécution du workflow (console Step Functions)
- Paramètres d'entrée : chemin du volume cible, filtre de fichiers (.gds/.oasis)
- Confirmation du démarrage de l'exécution

**Action de l'ingénieur** :
```
Cible : tous les fichiers de conception sous /vol/eda_designs/
Filtre : .gds, .gds2, .oas, .oasis
Exécution : démarrage du workflow de validation de qualité
```

---

### Section 3 : Analyse automatisée (1:30–2:30)

**Écran** : Affichage de la progression pendant l'exécution du workflow

**Résumé de la narration** :
> Le workflow exécute automatiquement les étapes suivantes :
> 1. Détection et listage des fichiers de conception
> 2. Extraction des métadonnées depuis l'en-tête de chaque fichier (library_name, cell_count, bounding_box, units)
> 3. Analyse statistique des données extraites (requêtes SQL)
> 4. Génération du rapport de revue de conception par IA
>
> Même pour des fichiers GDS volumineux (plusieurs Go), le traitement est rapide car seule la partie en-tête (64 Ko) est lue.

**Visuel clé** :
- Affichage de la complétion successive de chaque étape du workflow
- Affichage du traitement parallèle (Map State) de plusieurs fichiers simultanément
- Temps de traitement : environ 2 à 3 minutes (pour 40 fichiers)

---

### Section 4 : Revue des résultats (2:30–3:45)

**Écran** : Résultats de requête Athena SQL et résumé statistique

**Résumé de la narration** :
> Les résultats d'analyse peuvent être interrogés librement avec SQL.
> Par exemple, des analyses ad hoc telles que « afficher les cellules avec des bounding boxes anormalement grandes » sont possibles.

**Visuel clé — Exemple de requête Athena** :
```sql
-- Détection des valeurs aberrantes de bounding box
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Visuel clé — Résultats de la requête** :

| file_key | library_name | width | height | Jugement |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Valeur aberrante |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Valeur aberrante |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Valeur aberrante |

---

### Section 5 : Insights actionnables (3:45–5:00)

**Écran** : Rapport de revue de conception généré par IA

**Résumé de la narration** :
> L'IA interprète les résultats de l'analyse statistique et génère automatiquement un rapport de revue pour les ingénieurs de conception.
> Il comprend une évaluation des risques, des recommandations d'action concrètes et des éléments d'action priorisés.
> Sur la base de ce rapport, les discussions peuvent commencer immédiatement lors de la réunion de revue avant le tape-out.

**Visuel clé — Rapport de revue IA (extrait)** :

```markdown
# Rapport de revue de conception

## Évaluation des risques : Medium

## Résumé des détections
- Valeurs aberrantes de bounding box : 3 cas
- Violations des conventions de nommage : 2 cas
- Fichiers invalides : 2 cas

## Actions recommandées (par ordre de priorité)
1. [High] Investigation de la cause des 2 fichiers invalides
2. [Medium] Examen de l'optimisation du layout pour analog_frontend.oas
3. [Low] Uniformisation des conventions de nommage (block-a-io → block_a_io)
```

**Conclusion** :
> La revue transversale qui prenait plusieurs jours manuellement est maintenant complétée en quelques minutes.
> Les ingénieurs de conception peuvent se concentrer sur la vérification des résultats d'analyse et la prise de décisions d'action.

---

## Plan de capture d'écran

### Liste des captures d'écran nécessaires

| # | Écran | Section | Remarques |
|---|------|-----------|------|
| 1 | Liste du répertoire des fichiers de conception | Section 1 | Structure de fichiers sur FSx ONTAP |
| 2 | Écran de démarrage de l'exécution du workflow | Section 2 | Console Step Functions |
| 3 | Workflow en cours d'exécution (traitement parallèle Map State) | Section 3 | État avec progression visible |
| 4 | Écran de complétion du workflow | Section 3 | Toutes les étapes réussies |
| 5 | Éditeur de requêtes Athena + résultats | Section 4 | Requête de détection de valeurs aberrantes |
| 6 | Exemple de sortie JSON de métadonnées | Section 4 | Résultat d'extraction pour 1 fichier |
| 7 | Rapport de revue de conception IA complet | Section 5 | Affichage rendu Markdown |
| 8 | E-mail de notification SNS | Section 5 | Notification de complétion du rapport |

### Procédure de capture

1. Placer les données d'exemple dans l'environnement de démo
2. Exécuter manuellement le workflow et capturer l'écran à chaque étape
3. Exécuter des requêtes dans la console Athena et capturer les résultats
4. Télécharger le rapport généré depuis S3 et l'afficher

---

## Captures d'écran UI/UX vérifiées (revérification du 2026-05-10)

Conformément à la même approche que Phase 7 UC15/16/17, capture des **écrans UI/UX que les ingénieurs de conception voient réellement dans leur travail quotidien**.
Les vues techniques comme les graphes Step Functions sont exclues (détails dans
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md)).

### 1. FSx for NetApp ONTAP Volumes — Volume pour fichiers de conception

Liste des volumes ONTAP vue par les ingénieurs de conception. Les fichiers GDS/OASIS sont placés dans `eda_demo_vol`
avec gestion par ACL NTFS.

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     内容: FSx コンソールで ONTAP Volumes 一覧（eda_demo_vol 等）、Status=Created、Type=ONTAP
     マスク: アカウント ID、SVM ID の実値、ファイルシステム ID -->
![UC6: Liste des volumes FSx](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. Bucket de sortie S3 — Liste des documents de conception et résultats d'analyse

Écran où les responsables de revue de conception vérifient les résultats après la complétion du workflow.
Organisé en 3 préfixes : `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容: S3 コンソールで bucket の top-level prefix を確認
     マスク: アカウント ID、バケット名プレフィックス -->
![UC6: Bucket de sortie S3](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. Bucket de sortie S3 — Liste des documents de conception et résultats d'analyse

Écran où les responsables de revue de conception vérifient les résultats après la complétion du workflow.
Organisé en 3 préfixes : `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容: S3 コンソールで bucket の top-level prefix を確認
     マスク: アカウント ID、バケット名プレフィックス -->
![UC6: Bucket de sortie S3](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Résultats de requête Athena — Analyse SQL des métadonnées EDA

Écran où le design lead explore les informations DRC de manière ad hoc.
Workgroup : `fsxn-eda-uc6-workgroup`, base de données : `fsxn-eda-uc6-db`.

<!-- SCREENSHOT: uc6-athena-query-result.png
     内容: EDA メタデータ表の SELECT 結果（file_key、library_name、cell_count、bounding_box）
     マスク: アカウント ID -->
![UC6: Résultats de requête Athena](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Rapport de revue de conception généré par Bedrock

**Fonctionnalité phare d'UC6** : Basé sur les résultats d'agrégation DRC d'Athena, Bedrock Nova Lite génère
un rapport de revue en japonais destiné au Physical Design Lead.

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     内容: エグゼクティブサマリー + セル数分析 + 命名規則違反一覧 + リスク評価 (High/Medium/Low)
     実サンプル内容:
       ## 設計レビューサマリー
       ### エグゼクティブサマリー
       今回のDRC集計結果に基づき、設計品質の全体評価を以下に示します。
       設計ファイルは合計2件で、セル数分布は安定しており、バウンディングボックス外れ値は確認されませんでした。
       しかし、命名規則違反が6件見つかりました。
       ...
       ### リスク評価
       - **High**: なし
       - **Medium**: 命名規則違反が6件確認されました。
       - **Low**: セル数分布やバウンディングボックス外れ値に問題はありません。
     マスク: アカウント ID -->
![UC6: Rapport de revue de conception Bedrock](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### Valeurs mesurées (vérification de déploiement AWS du 2026-05-10)

- **Temps d'exécution Step Functions** : ~30 secondes (Discovery + Map(2 fichiers) + DRC + Report)
- **Rapport généré par Bedrock** : 2 093 octets (format Markdown en japonais)
- **Requête Athena** : 0,02 Ko scannés, temps d'exécution 812 ms
- **Stack réelle** : `fsxn-eda-uc6` (ap-northeast-1, en fonctionnement au 2026-05-10)

---

## Plan de narration

### Ton & Style

- **Point de vue** : Première personne de l'ingénieur de conception (Tanaka-san)
- **Ton** : Pratique, orienté résolution de problèmes
- **Langue** : Japonais (option de sous-titres anglais)
- **Vitesse** : Lente et claire (pour démo technique)

### Structure de la narration

| Section | Temps | Message clé |
|-----------|------|--------------|
| Problem | 0:00–0:45 | « Vérification de qualité de plus de 40 blocs nécessaire avant le tape-out. Impossible manuellement » |
| Trigger | 0:45–1:30 | « Il suffit de lancer le workflow après le jalon de conception » |
| Analysis | 1:30–2:30 | « Analyse d'en-tête → extraction de métadonnées → analyse statistique se déroulent automatiquement » |
| Results | 2:30–3:45 | « Requêtes SQL libres. Identification immédiate des valeurs aberrantes » |
| Insights | 3:45–5:00 | « Rapport IA avec actions priorisées. Directement utilisable en réunion de revue » |

---

## Exigences de données d'exemple

### Données d'exemple nécessaires

| # | Fichier | Format | Usage |
|---|---------|------------|------|
| 1 | `top_chip_v3.gds` | GDSII | Puce principale (grande échelle, plus de 1000 cellules) |
| 2 | `block_a_io.gds2` | GDSII | Bloc I/O (données normales) |
| 3 | `memory_ctrl.oasis` | OASIS | Contrôleur mémoire (données normales) |
| 4 | `analog_frontend.oas` | OASIS | Bloc analogique (valeur aberrante : BB large) |
| 5 | `test_block_debug.gds` | GDSII | Pour débogage (valeur aberrante : hauteur anormale) |
| 6 | `legacy_io_v1.gds2` | GDSII | Bloc legacy (valeur aberrante : largeur/hauteur) |
| 7 | `block-a-io.gds2` | GDSII | Échantillon de violation de convention de nommage |
| 8 | `TOP CHIP (copy).gds` | GDSII | Échantillon de violation de convention de nommage |

### Politique de génération de données d'exemple

- **Configuration minimale** : 8 fichiers (liste ci-dessus) couvrant tous les scénarios de la démo
- **Configuration recommandée** : plus de 40 fichiers (amélioration de la crédibilité de l'analyse statistique)
- **Méthode de génération** : Script Python générant des fichiers de test avec des en-têtes GDSII/OASIS valides
- **Taille** : Environ 100 Ko par fichier suffisent car seule l'analyse d'en-tête est effectuée

### Points de vérification de l'environnement de démo existant

- [ ] Les données d'exemple sont-elles placées dans le volume FSx ONTAP
- [ ] Le S3 Access Point est-il configuré
- [ ] La définition de table Glue Data Catalog existe-t-elle
- [ ] Le workgroup Athena est-il disponible

---

## Calendrier

### Réalisable en 1 semaine

| # | Tâche | Durée | Prérequis |
|---|--------|---------|---------|
| 1 | Génération de données d'exemple (8 fichiers) | 2 heures | Environnement Python |
| 2 | Vérification de l'exécution du workflow dans l'environnement de démo | 2 heures | Environnement déployé |
| 3 | Acquisition de captures d'écran (8 écrans) | 3 heures | Après tâche 2 |
| 4 | Finalisation du script de narration | 2 heures | Après tâche 3 |
| 5 | Montage vidéo (captures + narration) | 4 heures | Après tâches 3, 4 |
| 6 | Revue & corrections | 2 heures | Après tâche 5 |
| **Total** | | **15 heures** | |

### Prérequis (nécessaires pour atteindre 1 semaine)

- Le workflow Step Functions est déployé et fonctionne normalement
- Les fonctions Lambda (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) sont vérifiées
- Les tables et requêtes Athena sont exécutables
- L'accès au modèle Bedrock est activé

### Améliorations futures

| # | Élément d'extension | Vue d'ensemble | Priorité |
|---|---------|------|--------|
| 1 | Intégration d'outils DRC | Import direct des fichiers de résultats DRC de Calibre/Pegasus | High |
| 2 | Tableau de bord interactif | Tableau de bord de qualité de conception avec QuickSight | Medium |
| 3 | Notifications Slack/Teams | Notification par chat à la complétion du rapport de revue | Medium |
| 4 | Revue différentielle | Détection et rapport automatiques des différences avec l'exécution précédente | High |
| 5 | Définition de règles personnalisées | Possibilité de définir des règles de qualité spécifiques au projet | Medium |
| 6 | Rapports multilingues | Génération de rapports en anglais/japonais/chinois | Low |
| 7 | Intégration CI/CD | Intégration comme porte de qualité automatique dans le flux de conception | High |
| 8 | Support de données à grande échelle | Optimisation du traitement parallèle pour plus de 1000 fichiers | Medium |

---

## Notes techniques (pour les créateurs de démo)

### Composants utilisés (implémentation existante uniquement)

| Composant | Rôle |
|--------------|------|
| Step Functions | Orchestration de l'ensemble du workflow |
| Lambda (Discovery) | Détection et listage des fichiers de conception |
| Lambda (MetadataExtraction) | Parsing d'en-tête GDSII/OASIS et extraction de métadonnées |
| Lambda (DrcAggregation) | Exécution d'analyse statistique via Athena SQL |
| Lambda (ReportGeneration) | Génération de rapport de revue IA via Bedrock |
| Amazon Athena | Requêtes SQL sur les métadonnées |
| Amazon Bedrock | Génération de rapport en langage naturel (Nova Lite / Claude) |

### Solutions de secours lors de l'exécution de la démo

| Scénario | Réponse |
|---------|------|
| Échec d'exécution du workflow | Utiliser l'écran d'exécution pré-enregistré |
| Latence de réponse Bedrock | Afficher un rapport pré-généré |
| Timeout de requête Athena | Afficher un CSV de résultats pré-acquis |
| Panne réseau | Vidéo avec tous les écrans pré-capturés |

---

*Ce document a été créé comme guide de production de vidéo de démo pour présentation technique.*
