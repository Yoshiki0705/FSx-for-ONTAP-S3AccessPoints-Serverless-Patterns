# Portail de fichiers — Guide sécurité et conformité

> 🌐 Language: [English](../en/portal-compliance-guide.md) | [日本語](../ja/portal-compliance-guide.md) | [한국어](../ko/portal-compliance-guide.md) | [简体中文](../zh-CN/portal-compliance-guide.md) | [繁體中文](../zh-TW/portal-compliance-guide.md) | **Français** | [Deutsch](../de/portal-compliance-guide.md) | [Español](../es/portal-compliance-guide.md)

Guide destiné aux responsables de la sécurité, analystes conformité et équipes de protection des données qui doivent **vérifier** les contrôles réglementaires via le portail sans effectuer d'administration du stockage. Vous n'avez pas besoin des privilèges `storage-admin` — toutes les tâches ci-dessous utilisent un accès en lecture seule.

---

## Votre rôle dans le portail

| Ce que vous pouvez faire | Emplacement dans le portail |
|--------------------------|----------------------------|
| Vérifier l'état de la protection anti-ransomware | Barre latérale → 🛡️ ARP/AI |
| Confirmer le verrouillage et les périodes de rétention des snapshots | Barre latérale → 🔒 Lock |
| Consulter la piste d'audit (qui a accédé à quoi) | Barre latérale → 🔍 Audit Trail |
| Vérifier l'application du garde-fou PHI | Barre latérale → 📂 All Files (naviguer vers `/dicom/` ou `/phi/`) |
| Vérifier S3 Object Lock sur les buckets de sortie | Barre latérale → 🔒 Lock → onglet S3 Object Lock |
| Consulter les alertes EMS (événements système ONTAP) | Admin → Resources (lecture seule si non `storage-admin`) |

> **Remarque** : Vous ne pouvez pas modifier les configurations (paramètres de verrouillage, état ARP, politiques d'export). Pour toute modification, contactez un utilisateur `storage-admin`.

---

## Tâche 1 : Vérifier la protection anti-ransomware (ARP/AI)

**Contexte réglementaire** : FISC, NIST CSF DE.CM-4, ISO 27001 A.12.2

1. Cliquez sur **🛡️ ARP/AI** dans la barre latérale
2. Confirmez que chaque volume surveillé affiche un état vert (🟢 Aucune menace)
3. Si un badge de menace apparaît (🔴), notez le nom du volume et l'horodatage de détection
4. Vérifiez le **badge de cycle de vie de l'incident** pour connaître l'étape actuelle :
   - 🔴 Détecté — Menace identifiée, en attente de confinement
   - 🟠 Confiné — Accès de l'attaquant bloqué, snapshot préservé
   - 🟡 En cours d'investigation — Analyse forensique en cours
   - 🟢 Résolu — Incident clos

**Preuve pour les auditeurs** : Capturez l'écran du panneau ARP montrant l'état de protection de tous les volumes + les badges d'incidents actifs avec horodatages.

---

## Tâche 2 : Confirmer l'immuabilité des snapshots (WORM)

**Contexte réglementaire** : SEC 17a-4, FISC 7 ans de rétention, HIPAA 6 ans, SOX 5 ans, NARA

1. Cliquez sur **🔒 Lock** dans la barre latérale
2. Examinez les trois onglets :

### Onglet A : ONTAP SnapLock
- Vérifiez le type de volume : **Compliance** (personne ne peut supprimer, y compris root) ou **Enterprise** (l'administrateur peut libérer)
- Vérifiez que les périodes de rétention correspondent à votre politique :
  - Période minimale ≥ exigence réglementaire
  - Compliance Clock est initialisée et en cours d'exécution

### Onglet B : S3 Object Lock
- Vérifiez que Object Lock est activé sur le bucket de sortie
- Confirmez le mode : **Compliance** pour les archives réglementaires, **Governance** pour les sorties AI
- Vérifiez que les jours de rétention par défaut correspondent à votre exigence

### Onglet C : Tamperproof Snapshots
- Examinez le tableau des snapshots verrouillés : nom, date de création, date d'expiration
- Vérifiez que les dates d'expiration correspondent aux exigences de rétention :

| Réglementation | Rétention requise | Expiration attendue |
|---------------|-------------------|---------------------|
| FISC | 7 ans (2 557 jours) | Création + 7 ans |
| HIPAA | 6 ans (2 192 jours) | Création + 6 ans |
| SOX/J-SOX | 5 ans (1 825 jours) | Création + 5 ans |
| NARA | 3-75 ans (variable) | Selon le calendrier de conservation |

**Preuve pour les auditeurs** : Capturez chaque onglet montrant l'état de verrouillage + les périodes de rétention.

---

## Tâche 3 : Consulter la piste d'audit

**Contexte réglementaire** : FISC, SOX Section 302/404, HIPAA §164.312(b), PCI DSS 10.x

1. Cliquez sur **🔍 Audit Trail** dans la barre latérale
2. Le panneau affiche les événements de données S3 CloudTrail pour le S3 Access Point
3. Champs clés à examiner :
   - **Qui** : Principal IAM (identité utilisateur Cognito)
   - **Quand** : Horodatage de l'événement (UTC)
   - **Quoi** : Action API (`GetObject`, `PutObject`, `ListObjectsV2`)
   - **Quel fichier** : Clé S3 (chemin du fichier)
4. Filtrez par plage de dates ou par utilisateur si vous enquêtez sur un incident spécifique

**Preuve pour les auditeurs** : Exportez ou capturez la piste d'audit filtrée sur la période d'examen.

---

## Tâche 4 : Vérifier le garde-fou PHI

**Contexte réglementaire** : HIPAA §164.502 (principe du minimum nécessaire), 45 CFR 164.514

1. Cliquez sur **📂 All Files** dans la barre latérale
2. Naviguez vers un dossier nommé `/dicom/`, `/phi/`, `/pii/` ou `/hipaa/`
3. Observez que le bouton de traitement AI affiche : **🚫 PHI — AI Blocked**
4. Vérifiez que le bouton est désactivé (impossible de cliquer quel que soit le rôle)

**Signification** : Les fichiers dans ces chemins protégés sont structurellement empêchés d'être envoyés vers des services AI externes (Bedrock, Rekognition, Textract, Comprehend). Ceci est appliqué au niveau de l'interface utilisateur via la correspondance de motifs de chemins et ne peut être contourné par aucun utilisateur.

**Limitation** : Ce garde-fou dépend des conventions de nommage des dossiers. Les fichiers contenant des PHI placés dans des chemins non protégés ne sont pas bloqués. Assurez-vous que les politiques de structure de dossiers de l'organisation sont appliquées en amont.

**Preuve pour les auditeurs** : Capture d'écran montrant le bouton AI désactivé dans un dossier `/dicom/`.

---

## Tâche 5 : Vérifier S3 Object Lock sur les sorties AI

**Contexte réglementaire** : SEC 17a-4(f), CFTC 1.31, FINRA 4511

1. Cliquez sur **🔒 Lock** → onglet **S3 Object Lock**
2. Vérifiez :
   - Object Lock est **activé** sur le bucket de sortie
   - Le mode est approprié : **Compliance** (immuable) pour les archives réglementaires ou **Governance** (modifiable avec autorisation) pour les sorties AI
   - La période de rétention par défaut correspond à votre calendrier de conservation
3. Si Object Lock n'est pas configuré, escaladez vers un utilisateur `storage-admin`

**Pourquoi c'est important** : Les résultats de traitement AI (étiquettes de classification, texte extrait, rapports de conformité) stockés dans S3 peuvent eux-mêmes constituer des enregistrements réglementaires. Object Lock garantit que ces sorties ne peuvent être modifiées ou supprimées pendant la période de rétention.

---

## Tâche 6 : Vérification de la réponse aux incidents

Lorsqu'un incident ransomware est détecté :

1. Allez dans **🛡️ ARP/AI** → vérifiez l'état du badge d'incident
2. Vérifiez que le confinement a été exécuté :
   - Snapshot pris (preuve préservée)
   - Utilisateur/IP suspect bloqué
3. Allez dans **🔍 Audit Trail** → filtrez les événements autour de l'horodatage de détection
4. Documentez la chronologie : détection → confinement → début de l'investigation
5. Après résolution, vérifiez que le badge affiche 🟢 Résolu

**Référence SLA de la chronologie d'incident** :

| Phase | Durée typique | Votre SLA |
|-------|:---:|:---:|
| Détection → Confinement | < 5 minutes (automatisé) | _____ |
| Confinement → Début d'investigation | < 1 heure | _____ |
| Investigation → Résolution | Selon le cas | _____ |

---

## Correspondance réglementaire

| Fonctionnalité du portail | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|--------------------------|:---:|:---:|:---:|:---:|:---:|
| Détection ransomware ARP/AI | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (mode Compliance) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Garde-fou PHI | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| Suivi du cycle de vie des incidents | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## Ce que vous ne pouvez pas faire (et qui le peut)

| Action | Groupe requis | Qui contacter |
|--------|:---:|-------|
| Modifier l'état ARP/AI | `storage-admin` | Administrateur de stockage |
| Verrouiller/déverrouiller des snapshots | `storage-admin` | Administrateur de stockage |
| Configurer S3 Object Lock | `storage-admin` | Administrateur de stockage |
| Bloquer/débloquer des utilisateurs (confinement) | `storage-admin` | Opérations de sécurité + admin stockage |
| Créer/supprimer des volumes | `storage-admin` | Administrateur de stockage |
| Modifier les politiques d'export | `storage-admin` | Administrateur de stockage |

---

## Documents associés

| Document | Objectif |
|----------|----------|
| [Guide utilisateur](portal-user-guide.md) | Opérations quotidiennes des utilisateurs |
| [Modèle d'autorisation](portal-authorization-model.md) | Matrice complète des permissions |
| [Guide de démonstration admin](admin-resource-management-demo.md) | Opérations d'administration du stockage |
| [Playbook de réponse aux incidents](../../docs/incident-response-playbook.md) | Procédures complètes de réponse aux incidents |
| [Aide-mémoire](portal-quick-reference.md) | Résumé sur 1 page |
