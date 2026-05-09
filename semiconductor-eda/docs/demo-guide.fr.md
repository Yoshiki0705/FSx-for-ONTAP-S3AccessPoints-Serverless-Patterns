# Validation de fichiers de conception EDA — Guide de démonstration

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Ce guide définit une démonstration technique destinée aux ingénieurs de conception de semi-conducteurs. La démo présente un workflow de validation automatique de la qualité des fichiers de conception (GDS/OASIS), démontrant la valeur de la rationalisation des revues de conception avant le tapeout.

**Message clé de la démo** : Automatiser les vérifications de qualité inter-blocs IP que les ingénieurs effectuaient manuellement, les compléter en quelques minutes et permettre une action immédiate grâce aux rapports de revue de conception générés par l'IA.

**Durée estimée** : 3 à 5 minutes (vidéo de capture d'écran avec narration)

---

## Target Audience & Persona

### Public principal : Utilisateurs finaux EDA (Ingénieurs de conception)

| Élément | Détails |
|---------|---------|
| **Poste** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tâches quotidiennes** | Conception de layout, exécution DRC, intégration de blocs IP, préparation au tapeout |
| **Défis** | Obtenir une vue transversale de la qualité sur plusieurs blocs IP prend beaucoup de temps |
| **Environnement d'outils** | Outils EDA tels que Calibre, Virtuoso, IC Compiler, Innovus |
| **Résultat attendu** | Détection précoce des problèmes de qualité de conception pour respecter le calendrier de tapeout |

### Persona : Tanaka-san (Physical Design Lead)

- Gère plus de 40 blocs IP dans un projet SoC à grande échelle
- Doit effectuer des revues de qualité de tous les blocs 2 semaines avant le tapeout
- Vérifier individuellement les fichiers GDS/OASIS de chaque bloc est irréaliste
- « Je veux voir un résumé de la qualité de tous les blocs en un coup d'œil »

---

## Demo Scenario: Pre-tapeout Quality Review

### Aperçu du scénario

Pendant la phase de revue de qualité pré-tapeout, le responsable de conception exécute une validation automatique de la qualité sur plusieurs blocs IP (plus de 40 fichiers) et décide des actions à entreprendre sur la base des rapports de revue générés par l'IA.

### Workflow global

```
Fichiers de          Validation         Résultats          Revue IA
conception     →    automatique   →    d'analyse     →   Génération
(GDS/OASIS)         Workflow            Agrégation        de rapport
                    Déclenchement       (Athena SQL)      (Langage naturel)
```

### Valeur démontrée

1. **Réduction du temps** : Compléter les revues transversales en minutes au lieu de jours
2. **Exhaustivité** : Valider tous les blocs IP sans omission
3. **Jugement quantitatif** : Évaluation objective de la qualité via la détection statistique des valeurs aberrantes (méthode IQR)
4. **Actionnable** : L'IA présente des actions recommandées spécifiques

---

## Storyboard (5 sections / 3 à 5 minutes)

### Section 1 : Problem Statement (0:00–0:45)

**Écran** : Liste des fichiers du projet de conception (plus de 40 fichiers GDS/OASIS)

**Résumé de la narration** :
> Deux semaines avant le tapeout. Nous devons vérifier la qualité de conception de plus de 40 blocs IP.
> Ouvrir chaque fichier individuellement dans un outil EDA n'est pas réaliste.
> Nombre de cellules anormal, valeurs aberrantes de bounding box, violations de conventions de nommage — nous avons besoin d'un moyen de les détecter de manière transversale.

**Key Visual** :
- Structure de répertoire des fichiers de conception (.gds, .gds2, .oas, .oasis)
- Superposition de texte : « Revue manuelle : estimée à 3–5 jours »

---

### Section 2 : Workflow Trigger (0:45–1:30)

**Écran** : L'ingénieur de conception déclenche le workflow de validation de qualité

**Résumé de la narration** :
> Après avoir atteint le jalon de conception, nous lançons le workflow de validation de qualité.
> Il suffit de spécifier le répertoire cible, et la validation automatique de tous les fichiers de conception commence.

**Key Visual** :
- Écran d'exécution du workflow (console Step Functions)
- Paramètres d'entrée : chemin du volume cible, filtre de fichiers (.gds/.oasis)
- Confirmation du démarrage de l'exécution

**Action de l'ingénieur** :
```
Cible : Tous les fichiers de conception sous /vol/eda_designs/
Filtre : .gds, .gds2, .oas, .oasis
Action : Démarrer le workflow de validation de qualité
```

---

### Section 3 : Automated Analysis (1:30–2:30)

**Écran** : Affichage de la progression de l'exécution du workflow

**Résumé de la narration** :
> Le workflow exécute automatiquement les opérations suivantes :
> 1. Détection et listage des fichiers de conception
> 2. Extraction des métadonnées depuis l'en-tête de chaque fichier (library_name, cell_count, bounding_box, units)
> 3. Analyse statistique des données extraites (requêtes SQL)
> 4. Génération du rapport de revue de conception par l'IA
>
> Même pour les fichiers GDS volumineux (plusieurs Go), le traitement est rapide car seule la partie en-tête (64 Ko) est lue.

**Key Visual** :
- Les étapes du workflow se complètent séquentiellement
- Traitement parallèle (Map State) montrant plusieurs fichiers traités simultanément
- Temps de traitement : environ 2 à 3 minutes (pour 40 fichiers)

---

### Section 4 : Results Review (2:30–3:45)

**Écran** : Résultats de requête Athena SQL et résumé statistique

**Résumé de la narration** :
> Les résultats d'analyse peuvent être interrogés librement avec SQL.
> Par exemple, une analyse ad-hoc comme « afficher les cellules avec des bounding boxes anormalement grandes » est possible.

**Key Visual — Exemple de requête Athena** :
```sql
-- Détection des valeurs aberrantes de bounding box
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Résultats de la requête** :

| file_key | library_name | width | height | Verdict |
|----------|-------------|-------|--------|---------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Aberrant |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Aberrant |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Aberrant |

---

### Section 5 : Actionable Insights (3:45–5:00)

**Écran** : Rapport de revue de conception généré par l'IA

**Résumé de la narration** :
> L'IA interprète les résultats de l'analyse statistique et génère automatiquement un rapport de revue pour les ingénieurs de conception.
> Il comprend une évaluation des risques, des actions recommandées spécifiques et des éléments d'action priorisés.
> Sur la base de ce rapport, les discussions peuvent commencer immédiatement lors de la réunion de revue pré-tapeout.

**Key Visual — Rapport de revue IA (Extrait)** :

```markdown
# Rapport de revue de conception

## Évaluation des risques : Medium

## Résumé des constatations
- Valeurs aberrantes de bounding box : 3 éléments
- Violations de conventions de nommage : 2 éléments
- Fichiers invalides : 2 éléments

## Actions recommandées (par priorité)
1. [High] Investiguer la cause des 2 fichiers invalides
2. [Medium] Envisager l'optimisation du layout pour analog_frontend.oas
3. [Low] Unifier les conventions de nommage (block-a-io → block_a_io)
```

**Conclusion** :
> Les revues transversales qui prenaient des jours manuellement sont maintenant complétées en minutes.
> Les ingénieurs de conception peuvent se concentrer sur l'examen des résultats et la prise de décisions.

---

## Screen Capture Plan

### Captures d'écran requises

| # | Écran | Section | Notes |
|---|-------|---------|-------|
| 1 | Liste du répertoire des fichiers de conception | Section 1 | Structure de fichiers sur FSx ONTAP |
| 2 | Écran de démarrage de l'exécution du workflow | Section 2 | Console Step Functions |
| 3 | Workflow en cours (traitement parallèle Map State) | Section 3 | Progression visible |
| 4 | Écran de fin du workflow | Section 3 | Toutes les étapes réussies |
| 5 | Éditeur de requêtes Athena + résultats | Section 4 | Requête de détection des aberrants |
| 6 | Exemple de sortie JSON des métadonnées | Section 4 | Résultat d'extraction pour 1 fichier |
| 7 | Rapport de revue de conception IA (texte complet) | Section 5 | Affichage Markdown rendu |
| 8 | E-mail de notification SNS | Section 5 | Notification de fin de rapport |

### Procédure de capture

1. Placer les données d'exemple dans l'environnement de démo
2. Exécuter manuellement le workflow et capturer les écrans à chaque étape
3. Exécuter les requêtes dans la console Athena et capturer les résultats
4. Télécharger le rapport généré depuis S3 et l'afficher

---

## Narration Outline

### Ton et style

- **Perspective** : Première personne de l'ingénieur de conception (Tanaka-san)
- **Ton** : Pratique, orienté résolution de problèmes
- **Langue** : Japonais (sous-titres anglais en option)
- **Vitesse** : Lente et claire (pour une démo technique)

### Structure de la narration

| Section | Temps | Message clé |
|---------|-------|-------------|
| Problem | 0:00–0:45 | « Besoin de vérifier la qualité de plus de 40 blocs avant le tapeout. La revue manuelle ne suffira pas » |
| Trigger | 0:45–1:30 | « Il suffit de lancer le workflow après le jalon de conception » |
| Analysis | 1:30–2:30 | « Analyse d'en-tête → extraction de métadonnées → analyse statistique se déroule automatiquement » |
| Results | 2:30–3:45 | « Interroger librement avec SQL. Identifier les aberrants immédiatement » |
| Insights | 3:45–5:00 | « Le rapport IA présente des actions priorisées. Alimente directement les réunions de revue » |

---

## Sample Data Requirements

### Données d'exemple requises

| # | Fichier | Format | Objectif |
|---|---------|--------|----------|
| 1 | `top_chip_v3.gds` | GDSII | Puce principale (grande échelle, 1000+ cellules) |
| 2 | `block_a_io.gds2` | GDSII | Bloc I/O (données normales) |
| 3 | `memory_ctrl.oasis` | OASIS | Contrôleur mémoire (données normales) |
| 4 | `analog_frontend.oas` | OASIS | Bloc analogique (aberrant : grande BB) |
| 5 | `test_block_debug.gds` | GDSII | Bloc de débogage (aberrant : hauteur anormale) |
| 6 | `legacy_io_v1.gds2` | GDSII | Bloc legacy (aberrant : largeur et hauteur) |
| 7 | `block-a-io.gds2` | GDSII | Exemple de violation de convention de nommage |
| 8 | `TOP CHIP (copy).gds` | GDSII | Exemple de violation de convention de nommage |

### Politique de génération des données d'exemple

- **Configuration minimale** : 8 fichiers (liste ci-dessus) couvrant tous les scénarios de la démo
- **Configuration recommandée** : Plus de 40 fichiers (pour une analyse statistique plus convaincante)
- **Méthode de génération** : Script Python pour générer des fichiers de test avec des en-têtes GDSII/OASIS valides
- **Taille** : ~100 Ko par fichier suffisant car seule l'analyse d'en-tête est effectuée

### Liste de vérification de l'environnement de démo existant

- [ ] Données d'exemple placées sur le volume FSx ONTAP
- [ ] S3 Access Point configuré
- [ ] Définition de table Glue Data Catalog existante
- [ ] Groupe de travail Athena disponible

---

## Timeline

### Réalisable en 1 semaine

| # | Tâche | Temps requis | Prérequis |
|---|-------|--------------|-----------|
| 1 | Génération des données d'exemple (8 fichiers) | 2 heures | Environnement Python |
| 2 | Vérification de l'exécution du workflow dans l'environnement de démo | 2 heures | Environnement déployé |
| 3 | Acquisition des captures d'écran (8 écrans) | 3 heures | Après la tâche 2 |
| 4 | Finalisation du script de narration | 2 heures | Après la tâche 3 |
| 5 | Montage vidéo (captures + narration) | 4 heures | Après les tâches 3, 4 |
| 6 | Revue et corrections | 2 heures | Après la tâche 5 |
| **Total** | | **15 heures** | |

### Prérequis (nécessaires pour une réalisation en 1 semaine)

- Workflow Step Functions déployé et fonctionnant normalement
- Fonctions Lambda (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) vérifiées
- Tables et requêtes Athena exécutables
- Accès au modèle Bedrock activé

### Future Enhancements (Améliorations futures)

| # | Amélioration | Aperçu | Priorité |
|---|-------------|--------|----------|
| 1 | Intégration d'outils DRC | Ingestion directe des fichiers de résultats DRC de Calibre/Pegasus | High |
| 2 | Tableau de bord interactif | Tableau de bord de qualité de conception via QuickSight | Medium |
| 3 | Notifications Slack/Teams | Notification par chat à la fin du rapport | Medium |
| 4 | Revue différentielle | Détection et rapport automatiques des différences avec l'exécution précédente | High |
| 5 | Définitions de règles personnalisées | Permettre des règles de qualité spécifiques au projet | Medium |
| 6 | Rapports multilingues | Génération de rapports en anglais/japonais/chinois | Low |
| 7 | Intégration CI/CD | Intégrer comme porte de qualité automatique dans le flux de conception | High |
| 8 | Support de données à grande échelle | Optimisation du traitement parallèle pour plus de 1000 fichiers | Medium |

---

## Technical Notes (Pour les créateurs de démo)

### Composants utilisés (Implémentation existante uniquement)

| Composant | Rôle |
|-----------|------|
| Step Functions | Orchestration globale du workflow |
| Lambda (Discovery) | Détection et listage des fichiers de conception |
| Lambda (MetadataExtraction) | Analyse d'en-tête GDSII/OASIS et extraction de métadonnées |
| Lambda (DrcAggregation) | Exécution d'analyse statistique via Athena SQL |
| Lambda (ReportGeneration) | Génération de rapport de revue IA via Bedrock |
| Amazon Athena | Requêtes SQL sur les métadonnées |
| Amazon Bedrock | Génération de rapport en langage naturel (Nova Lite / Claude) |

### Solutions de repli pour l'exécution de la démo

| Scénario | Réponse |
|----------|---------|
| Échec d'exécution du workflow | Utiliser des écrans d'exécution pré-enregistrés |
| Délai de réponse Bedrock | Afficher un rapport pré-généré |
| Timeout de requête Athena | Afficher un CSV de résultats pré-récupéré |
| Panne réseau | Tous les écrans pré-capturés et compilés en vidéo |

---

*Ce document a été créé comme guide de production pour une vidéo de démonstration de présentation technique.*
