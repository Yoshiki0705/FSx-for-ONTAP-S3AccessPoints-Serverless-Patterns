# Portail de fichiers — Aide-mémoire

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | **Français** | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

Aide-mémoire d'une page pour les opérations quotidiennes du portail. Imprimez ou ajoutez aux favoris.

---

## Navigation

| Section de la barre latérale | Fonction |
|:---:|------|
| 📂 All Files | Parcourir, prévisualiser, télécharger, partager, Q&R AI |
| ⭐ Favorites | Fichiers épinglés |
| 🕐 Recent | Historique d'accès |
| 📤 Upload | Téléversement par glisser-déposer (max 50 Go/fichier) |
| ⚡ AI Processing | Déclencher des workflows AI/ML sur des dossiers |
| 📋 Job History | Résultats des tâches passées + état |
| 📊 Analytics | Requêtes SQL Athena |
| 📸 Snapshots | Copies instantanées + restauration FlexClone |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | État de la protection anti-ransomware |
| 🔧 Resources | Panneaux d'administration du stockage (admin uniquement) |
| 🔄 Version Diff | Comparer des fichiers entre snapshots |
| 🔍 Audit Trail | Qui a accédé à quoi, quand |

---

## Tâches courantes (tous les utilisateurs)

| Je souhaite... | Comment faire |
|---------------|--------------|
| Parcourir les fichiers | Barre latérale → 📂 All Files → cliquer sur les dossiers |
| Prévisualiser un PDF | Cliquer sur 📕 à côté du fichier |
| Prévisualiser un document Word | Cliquer sur 📝 à côté du fichier |
| Télécharger un fichier | Cliquer sur 📄 à côté du fichier |
| Partager un lien de fichier | Cliquer sur 🔗 → choisir le TTL → copier l'URL |
| Poser une question à l'AI sur un fichier | Sélectionner le fichier → saisir la question dans le panneau droit |
| Détecter des objets dans une image | Sélectionner l'image → "Detect Objects" dans le panneau droit |
| Téléverser des fichiers | Barre latérale → 📤 Upload → glisser-déposer |
| Lancer l'AI sur un dossier | Dans All Files, cliquer sur ⚡ au-dessus de la liste |
| Consulter les résultats d'une tâche | Barre latérale → 📋 Job History → cliquer sur une tâche |
| Restaurer depuis un snapshot | Barre latérale → 📸 Snapshots → bouton "Restore" |
| Changer de langue | Cliquer sur 🌐 dans la barre supérieure |

---

## Tâches courantes (Conformité / Sécurité)

| Je souhaite... | Comment faire |
|---------------|--------------|
| Vérifier l'état anti-ransomware | Barre latérale → 🛡️ ARP/AI |
| Vérifier les verrous WORM | Barre latérale → 🔒 Lock → onglet SnapLock |
| Vérifier le verrouillage du bucket de sortie | Barre latérale → 🔒 Lock → onglet S3 Object Lock |
| Voir les snapshots verrouillés | Barre latérale → 🔒 Lock → onglet Tamperproof |
| Consulter l'audit d'accès | Barre latérale → 🔍 Audit Trail |
| Vérifier le garde-fou PHI | All Files → naviguer vers `/dicom/` → le bouton affiche 🚫 |

---

## Tâches courantes (Administrateur de stockage)

| Je souhaite... | Comment faire |
|---------------|--------------|
| Voir le tableau de bord de santé | Barre latérale → 🔧 Resources (le tableau de bord apparaît en premier) |
| Gérer les volumes | Resources → Storage → Volumes |
| Configurer les politiques d'export | Resources → Access Control → Export Policies |
| Activer ARP sur les volumes | Resources → Protection → ARP Admin |
| Verrouiller un snapshot | Resources → Protection → Snapshot Admin → formulaire Lock |
| Bloquer un utilisateur compromis | Barre latérale → 🛡️ ARP/AI → onglet Contain → Block SMB User |
| Débloquer après résolution | Barre latérale → 🛡️ ARP/AI → onglet Unblock |
| Consulter les alertes EMS | Resources → (événements EMS dans la surveillance) |

---

## Raccourcis clavier

| Touche | Action |
|--------|--------|
| `Tab` | Se déplacer entre les éléments interactifs |
| `Enter` | Activer un bouton / ouvrir un dossier |
| `Escape` | Fermer la fenêtre modale / rejeter le panneau |

---

## Indicateurs d'état

| Icône | Signification |
|:---:|-------|
| 🟢 | Sain / Aucune menace / Résolu |
| 🔴 | Menace détectée / Erreur |
| 🟠 | Confiné (incident en cours) |
| 🟡 | En cours d'investigation |
| 🚫 | PHI — AI bloqué (garde-fou actif) |
| ⚠️ | Avertissement (capacité > 85 %, etc.) |

---

## Niveaux d'accès

| Groupe | Peut faire | Ne peut pas faire |
|--------|-----------|-------------------|
| `authenticated` | Parcourir, télécharger, téléverser, AI, voir l'état de protection | Modifier la configuration du stockage |
| `storage-admin` | Tout ce qui précède + créer/supprimer des volumes, verrouiller des snapshots, bloquer des utilisateurs, gérer les politiques | — |

---

## Dépannage rapide

| Symptôme | Solution |
|----------|----------|
| "ONTAP Connection Required" | Normal en DemoMode. Demandez à l'admin de configurer le VPC. |
| Le bouton AI affiche 🚫 | Vous êtes dans un dossier protégé PHI. Naviguez ailleurs. |
| Lien de partage expiré | Générez-en un nouveau (🔗). TTL max = 1 heure. |
| Fichier invisible après écriture NFS | Rafraîchissez la liste. Il devrait apparaître immédiatement. |
| Chargement infini | Vérifiez la connexion internet. Essayez déconnexion → reconnexion. |

---

## Plan de la documentation

| Vous êtes... | Commencez ici |
|-------------|---------------|
| Utilisateur final (tâches quotidiennes) | [Guide utilisateur](portal-user-guide.md) |
| Responsable sécurité / conformité | [Guide conformité](portal-compliance-guide.md) |
| Administrateur de stockage | [Guide de démonstration admin](admin-resource-management-demo.md) |
| Administrateur IT (déploiement) | [Guide de démarrage](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| Développeur (personnalisation) | [Guide d'implémentation](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
