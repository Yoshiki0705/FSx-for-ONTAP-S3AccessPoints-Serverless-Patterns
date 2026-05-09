# UC1: Juridique / Conformité — Audit de serveur de fichiers et gouvernance des données

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture de bout en bout (Entrée → Sortie)

---

## Diagramme d'architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for NetApp ONTAP"]
        FILES["Données du serveur de fichiers<br/>Fichiers avec ACL NTFS"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / ONTAP REST API"]
    end

    subgraph TRIGGER["⏰ Déclencheur"]
        EB["EventBridge Scheduler<br/>rate(24 hours)"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Exécution dans le VPC<br/>• Listage de fichiers S3 AP<br/>• Collecte de métadonnées ONTAP<br/>• Vérification du style de sécurité"]
        ACL["2️⃣ ACL Collection Lambda<br/>• Appels ONTAP REST API<br/>• Point de terminaison file-security<br/>• Récupération ACL NTFS / ACL partage CIFS<br/>• Sortie JSON Lines vers S3"]
        ATH["3️⃣ Athena Analysis Lambda<br/>• Mise à jour du Glue Data Catalog<br/>• Exécution de requêtes Athena SQL<br/>• Détection de permissions excessives<br/>• Détection d'accès obsolètes<br/>• Détection de violations de politique"]
        RPT["4️⃣ Report Generation Lambda<br/>• Amazon Bedrock (Nova/Claude)<br/>• Génération de rapport de conformité<br/>• Évaluation des risques et suggestions de remédiation<br/>• Notification SNS"]
    end

    subgraph OUTPUT["📤 Sortie — S3 Bucket"]
        ACLDATA["acl-data/*.jsonl<br/>Informations ACL (partitionnées par date)"]
        ATHENA["athena-results/*.csv<br/>Résultats de détection de violations"]
        REPORT["reports/*.md<br/>Rapport de conformité IA"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    FILES --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> ACL
    ACL --> ATH
    ATH --> RPT
    ACL --> ACLDATA
    ATH --> ATHENA
    RPT --> REPORT
    RPT --> SNS
```

---

## Détail du flux de données

### Entrée
| Élément | Description |
|---------|-------------|
| **Source** | Volume FSx for NetApp ONTAP |
| **Types de fichiers** | Tous les fichiers (avec ACL NTFS) |
| **Méthode d'accès** | S3 Access Point (listage de fichiers) + ONTAP REST API (informations ACL) |
| **Stratégie de lecture** | Métadonnées uniquement (le contenu des fichiers n'est pas lu) |

### Traitement
| Étape | Service | Fonction |
|-------|---------|----------|
| Discovery | Lambda (VPC) | Lister les fichiers via S3 AP, collecter les métadonnées ONTAP |
| ACL Collection | Lambda (VPC) | Récupérer les ACL NTFS / ACL partage CIFS via ONTAP REST API |
| Athena Analysis | Lambda + Glue + Athena | Détection basée sur SQL des permissions excessives, accès obsolètes, violations de politique |
| Report Generation | Lambda + Bedrock | Génération de rapport de conformité en langage naturel |

### Sortie
| Artefact | Format | Description |
|----------|--------|-------------|
| Données ACL | `acl-data/YYYY/MM/DD/*.jsonl` | Informations ACL par fichier (JSON Lines) |
| Résultats Athena | `athena-results/{id}.csv` | Résultats de détection de violations (permissions excessives, fichiers orphelins, etc.) |
| Rapport de conformité | `reports/YYYY/MM/DD/compliance-report-{id}.md` | Rapport généré par Bedrock |
| Notification SNS | Email | Résumé des résultats d'audit et emplacement du rapport |

---

## Décisions de conception clés

1. **Combinaison S3 AP + ONTAP REST API** — S3 AP pour le listage de fichiers, ONTAP REST API pour la récupération détaillée des ACL (approche en deux étapes)
2. **Pas de lecture du contenu des fichiers** — À des fins d'audit, seules les métadonnées/informations de permissions sont collectées, minimisant les coûts de transfert de données
3. **JSON Lines + partitionnement par date** — Équilibre entre l'efficacité des requêtes Athena et le suivi historique
4. **Athena SQL pour la détection de violations** — Analyse flexible basée sur des règles (permissions Everyone, 90 jours sans accès, etc.)
5. **Bedrock pour les rapports en langage naturel** — Assure la lisibilité pour le personnel non technique (équipes juridiques/conformité)
6. **Interrogation périodique (non événementielle)** — S3 AP ne prend pas en charge les notifications d'événements, donc une exécution planifiée périodique est utilisée

---

## Services AWS utilisés

| Service | Rôle |
|---------|------|
| FSx for NetApp ONTAP | Stockage de fichiers d'entreprise (avec ACL NTFS) |
| S3 Access Points | Accès serverless aux volumes ONTAP |
| EventBridge Scheduler | Déclencheur périodique (audit quotidien) |
| Step Functions | Orchestration de workflow |
| Lambda | Calcul (Discovery, ACL Collection, Analysis, Report) |
| Glue Data Catalog | Gestion de schéma pour Athena |
| Amazon Athena | Analyse de permissions et détection de violations basées sur SQL |
| Amazon Bedrock | Génération de rapport de conformité IA (Nova / Claude) |
| SNS | Notification des résultats d'audit |
| Secrets Manager | Gestion des identifiants ONTAP REST API |
| CloudWatch + X-Ray | Observabilité |
