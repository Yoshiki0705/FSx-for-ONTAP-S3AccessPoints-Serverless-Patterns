# Portail de fichiers — Guide utilisateur

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | [한국어](../ko/portal-user-guide.md) | [简体中文](../zh-CN/portal-user-guide.md) | [繁體中文](../zh-TW/portal-user-guide.md) | **Français** | [Deutsch](../de/portal-user-guide.md) | [Español](../es/portal-user-guide.md)

Guide destiné aux utilisateurs finaux invités à utiliser un File Portal déjà déployé. Ce document suppose qu'un administrateur a complété le déploiement et créé votre compte — vous n'avez besoin ni d'un accès AWS CLI ni de connaissances en déploiement.

**Ce que fait ce portail** : Parcourir les fichiers NAS depuis votre navigateur, déclencher des analyses AI/ML, visualiser les résultats et vérifier l'état de la protection des données — le tout sans VPN ni configuration de client SMB/NFS.

---

## Prise en main

### 1. Connexion

1. Ouvrez l'URL du portail fournie par votre administrateur
2. Saisissez votre e-mail et votre mot de passe (fourni ou auto-enregistré selon la configuration)
3. Si la MFA est activée, saisissez le code TOTP de votre application d'authentification
4. Lors de la première connexion, le **Welcome Modal** vous présente 3 fonctionnalités clés :
   - 📂 Navigation de fichiers — Parcourir les fichiers NAS depuis votre navigateur
   - ⚡ Traitement AI — Sélectionner des fichiers et déclencher des workflows
   - 🔒 Protection des données — Snapshots, verrouillage et état anti-ransomware

> **Astuce** : Cochez « Ne plus afficher » pour ignorer le Welcome Modal lors des connexions suivantes.

### 2. Disposition du portail

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 FR ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ Barre latérale│  Contenu principal                      │
│ (navigation)  │                                         │
│               │                   Panneau AI Assistant →│
└───────────────┴─────────────────────────────────────────┘
```

- **Barre latérale gauche** : Navigation groupée en Parcourir, AI & Traitement, Protection des données, Administration
- **Contenu principal** : Section active (change lorsque vous cliquez sur les éléments de la barre latérale)
- **Panneau droit** : AI Assistant (apparaît lorsque vous sélectionnez un fichier dans All Files)
- **Barre supérieure** : Sélecteur de langue, e-mail utilisateur, déconnexion

### 3. Langue

Cliquez sur le sélecteur de langue 🌐 dans la barre supérieure pour basculer entre 8 langues : 日本語, English, 한국어, 简体中文, 繁體中文, Français, Deutsch, Español. Le changement est instantané — pas de rechargement de page.

---

## Parcourir — Travailler avec les fichiers

### All Files

Votre navigateur de fichiers principal. Affiche le contenu du volume FSx for ONTAP via S3 Access Point.

| Action | Comment |
|--------|---------|
| Naviguer dans les dossiers | Cliquer sur un nom de dossier |
| Remonter d'un niveau | Cliquer sur `..` en haut de la liste |
| Prévisualiser les images | Cliquer sur l'icône 🖼️ à côté des fichiers image |
| Prévisualiser un PDF | Cliquer sur l'icône 📕 — ouvre dans le visualiseur intégré du navigateur |
| Prévisualiser les documents Word | Cliquer sur l'icône 📝 — rendu dans le navigateur |
| Télécharger un fichier | Cliquer sur l'icône 📄 |
| Créer un lien de partage | Cliquer sur 🔗 → sélectionner le TTL (5 min / 15 min / 1 heure) → copier l'URL |
| Poser une question AI sur un fichier | Sélectionner un fichier → saisir une question dans le panneau AI à droite |
| Détecter des objets dans les images | Sélectionner une image → cliquer sur "Detect Objects" dans le panneau AI |
| Traiter ce dossier | Cliquer sur le bouton ⚡ au-dessus de la liste de fichiers |

**Dossiers protégés PHI** : Si vous accédez à un dossier nommé `/dicom/`, `/phi/`, `/pii/` ou similaire, le bouton de traitement AI affiche `🚫 PHI — AI Blocked`. C'est un garde-fou de sécurité — les fichiers de ces dossiers ne peuvent pas être envoyés aux services AI quelles que soient vos permissions.

### Favorites

Épinglez les fichiers fréquemment consultés en cliquant sur l'icône ⭐ dans la liste de fichiers. Les fichiers épinglés apparaissent dans la section Favorites pour un accès rapide.

### Recent

Affiche vos fichiers récemment consultés, téléchargés ou interrogés par AI avec des horodatages relatifs (« il y a 3 min », « il y a 2 h »). Seul votre propre historique est visible — l'activité des autres utilisateurs n'est pas affichée.

### Upload

Upload de fichiers par glisser-déposer basé sur Storage Browser for S3. Prend également en charge :
- Création de dossiers
- Copie et suppression de fichiers
- Upload multi-fichiers (jusqu'à 50 Go par fichier)

---

## AI & Traitement

### AI Processing

Déclenchez des workflows AI/ML sur un dossier ou un ensemble de fichiers.

1. Sélectionnez un modèle de traitement dans le menu déroulant (ex. : Legal Compliance, Financial IDP, Semiconductor EDA)
2. Définissez le préfixe d'entrée (pré-rempli si vous avez cliqué ⚡ depuis All Files)
3. Cliquez sur **Start Processing**
4. Vous serez redirigé vers Job History où le statut se met à jour toutes les 5 secondes

### Job History

Consultez tous vos travaux de traitement passés avec leur statut, horodatages et données de sortie.

| Statut | Signification |
|--------|---------------|
| 🔵 RUNNING | Traitement en cours |
| 🟢 SUCCEEDED | Terminé — cliquer pour voir les résultats |
| 🔴 FAILED | Erreur survenue — consulter la sortie pour les détails |
| ⚪ TIMED_OUT | Temps d'exécution maximum dépassé |

Cliquez sur un travail pour développer sa sortie. Si les résultats ont été écrits sur le volume, un lien de navigation vous amène directement au dossier de sortie dans All Files.

### Analytics

Exécutez des requêtes SQL sur vos données via Amazon Athena. Cela nécessite des tables Glue Data Catalog pré-configurées (mises en place par votre administrateur).

---

## Protection des données

### Snapshots

Consultez les snapshots de volume — copies de vos données à un instant donné.

- **Liste** : Voir tous les snapshots disponibles avec leurs horodatages de création
- **Restauration** : Cliquez sur "Restore" pour créer un FlexClone (copie instantanée et économe en espace) à partir de n'importe quel snapshot. Le clone obtient son propre S3 Access Point et est disponible en quelques secondes.

### Lock (WORM)

Consultez l'état d'immuabilité de vos données à travers trois mécanismes :

| Onglet | Ce qu'il affiche |
|--------|-----------------|
| ONTAP SnapLock | Si le volume utilise le mode Compliance ou Enterprise, périodes de rétention |
| S3 Object Lock | Si les buckets de sortie AI ont le WORM au niveau objet activé |
| Tamperproof Snapshot | Quels snapshots sont verrouillés et quand ils expirent |

> **Remarque** : La configuration des paramètres de verrouillage nécessite le rôle `storage-admin`. Les utilisateurs réguliers ont un accès en lecture seule à cette section.

### ARP/AI (Protection anti-ransomware)

Consultez l'état de la protection autonome contre les ransomwares pour vos volumes.

| Ce que vous voyez | Signification |
|-------------------|---------------|
| 🟢 No threats | Tous les volumes sont sains |
| 🔴 Threat detected | ARP/AI a signalé une activité suspecte |
| Incident badge | Affiche l'étape de réponse actuelle (Detected → Contained → Investigating → Resolved) |

Si une menace est détectée et que vous êtes dans le groupe `storage-admin`, vous pouvez exécuter des actions de confinement directement depuis ce panneau.

---

## Administration (Nécessite le groupe `storage-admin`)

Ces sections ne sont visibles/actionnables que si votre compte est dans le groupe Cognito `storage-admin`.

### Storage Dashboard

Page d'accueil administrateur. Quatre cartes affichant :
- 💾 Nombre de volumes + utilisation moyenne de la capacité
- 🛡️ Volumes protégés par ARP + menaces actives
- 🔐 Snapshots verrouillés (inviolables)
- 📊 Ratio d'efficacité du stockage

Cliquez sur n'importe quelle carte pour accéder au panneau de détails.

### Resources

Panneau d'administration en grille de cartes avec 10 zones de gestion organisées par catégorie :

| Catégorie | Panneaux |
|-----------|----------|
| Stockage | Volumes, Qtrees, Quotas, Efficiency |
| Contrôle d'accès | Export Policies, CIFS Shares, QoS |
| Protection | ARP Admin, Snapshot Admin, SnapLock |

### Version Diff

Comparez le contenu de fichiers entre deux snapshots côte à côte.

### Audit Trail

Interrogez les événements de données CloudTrail S3 pour répondre à « qui a accédé à quoi, et quand ».

---

## Conseils & FAQ

**Q : Je vois « ONTAP Connection Required » dans certains panneaux.**
R : Le portail est en DemoMode ou l'administrateur n'a pas encore configuré la connexion VPC. La navigation de fichiers et les fonctionnalités AI fonctionnent toujours — seuls les panneaux spécifiques à ONTAP (Snapshots, ARP, Lock) nécessitent la connexion.

**Q : Mon bouton de traitement AI affiche « PHI — AI Blocked ».**
R : Vous êtes dans un dossier protégé (`/dicom/`, `/phi/`, `/pii/`, etc.). C'est intentionnel — les fichiers dans ces chemins ne peuvent pas être envoyés aux services AI. Naviguez vers un dossier non protégé pour utiliser les fonctionnalités AI.

**Q : Les liens de partage expirent rapidement.**
R : Les liens de partage utilisent des Presigned URL avec une durée de vie que vous choisissez (5 min, 15 min ou 1 heure). Pour un partage à plus long terme, consultez votre administrateur au sujet de l'intégration Nextcloud ou ajustez les options de TTL.

**Q : Les fichiers que j'ai uploadés via NFS/SMB ne s'affichent pas.**
R : Ils devraient apparaître immédiatement (ONTAP garantit une cohérence forte inter-protocoles). Essayez de rafraîchir la liste de fichiers. Si le problème persiste, le fichier peut être dans un sous-dossier — vérifiez le chemin.

**Q : Puis-je utiliser le portail sur mobile ?**
R : Oui. La barre latérale se replie sur les écrans étroits. Toutes les fonctionnalités fonctionnent sur les navigateurs mobiles, bien que l'expérience soit optimisée pour le bureau.

**Q : Comment changer mon mot de passe ?**
R : Utilisez le Cognito Hosted UI ou demandez à votre administrateur de le réinitialiser.

---

## Documents connexes

| Document | Public | Objectif |
|----------|--------|----------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | Administrateurs | Déployer le portail depuis zéro |
| [Admin Demo Guide](admin-resource-management-demo.md) | Administrateurs stockage | Démo E2E des opérations d'administration |
| [AI Features Quick Start](ai-features-quick-start.md) | Tous les utilisateurs | Essayer Bedrock, Rekognition, Athena |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | Développeurs | Architecture et personnalisation |
| [Authorization Model](portal-authorization-model.md) | Équipes sécurité | Groupes Cognito, IAM, accès au niveau fichier |
| [Compliance Guide](portal-compliance-guide.md) | Sécurité/Conformité | Vérifier les contrôles réglementaires |
| [Quick Reference](portal-quick-reference.md) | Tous les rôles | Aide-mémoire 1 page |
