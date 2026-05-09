# UC8: Énergie/Pétrole & Gaz — Traitement de données sismiques et détection d'anomalies de puits

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture de bout en bout (Entrée → Sortie)

---

## Diagramme d'architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for NetApp ONTAP"]
        DATA["Données sismiques et de puits<br/>.segy (levé sismique)<br/>.las (journaux de puits)<br/>.csv (données de capteurs)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject / Range"]
    end

    subgraph TRIGGER["⏰ Déclencheur"]
        EB["EventBridge Scheduler<br/>rate(6 hours)"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Exécution dans le VPC<br/>• Découverte de fichiers via S3 AP<br/>• Filtre .segy/.las/.csv<br/>• Génération du manifeste"]
        SM["2️⃣ Seismic Metadata Lambda<br/>• Range Request (premiers 3600B)<br/>• Analyse de l'en-tête SEG-Y<br/>• survey_name, coordinate_system<br/>• sample_interval, trace_count extraction"]
        AD["3️⃣ Anomaly Detection Lambda<br/>• Récupération LAS/CSV via S3 AP<br/>• Méthode statistique (seuil d'écart-type)<br/>• Détection d'anomalies de journaux de puits<br/>• Calcul du score d'anomalie"]
        ATH["4️⃣ Athena Analysis Lambda<br/>• Mise à jour du Glue Data Catalog<br/>• Exécution de requêtes Athena SQL<br/>• Corrélation d'anomalies inter-puits et séries temporelles<br/>• Agrégation statistique"]
        CR["5️⃣ Compliance Report Lambda<br/>• Bedrock InvokeModel<br/>• Génération du rapport de conformité<br/>• Vérification des exigences réglementaires<br/>• Notification SNS"]
    end

    subgraph OUTPUT["📤 Sortie — S3 Bucket"]
        META["metadata/*.json<br/>Métadonnées SEG-Y"]
        ANOM["anomalies/*.json<br/>Résultats de détection d'anomalies"]
        ATHOUT["athena-results/*.csv<br/>Résultats de corrélation d'anomalies"]
        REPORT["reports/*.md<br/>Rapport de conformité"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(notification de fin de rapport)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> SM
    SM --> AD
    AD --> ATH
    ATH --> CR
    SM --> META
    AD --> ANOM
    ATH --> ATHOUT
    CR --> REPORT
    CR --> SNS
```

---

## Détail du flux de données

### Entrée
| Élément | Description |
|---------|-------------|
| **Source** | Volume FSx for NetApp ONTAP |
| **Types de fichiers** | .segy (données sismiques SEG-Y), .las (journaux de puits), .csv (données de capteurs) |
| **Méthode d'accès** | S3 Access Point (ListObjectsV2 + GetObject + Range Request) |
| **Stratégie de lecture** | SEG-Y : premiers 3600 octets uniquement (Range Request), LAS/CSV : récupération complète |

### Traitement
| Étape | Service | Fonction |
|-------|---------|----------|
| Découverte | Lambda (VPC) | Découverte des fichiers SEG-Y/LAS/CSV via S3 AP, génération du manifeste |
| Métadonnées sismiques | Lambda | Range Request pour l'en-tête SEG-Y, extraction de métadonnées (survey_name, coordinate_system, sample_interval, trace_count) |
| Détection d'anomalies | Lambda | Détection statistique d'anomalies sur les journaux de puits (seuil d'écart-type), calcul du score d'anomalie |
| Analyse Athena | Lambda + Glue + Athena | Corrélation d'anomalies inter-puits et séries temporelles basée sur SQL, agrégation statistique |
| Rapport de conformité | Lambda + Bedrock | Génération du rapport de conformité, vérification des exigences réglementaires |

### Sortie
| Artefact | Format | Description |
|----------|--------|-------------|
| Métadonnées JSON | `metadata/YYYY/MM/DD/{survey}_metadata.json` | Métadonnées SEG-Y (système de coordonnées, intervalle d'échantillonnage, nombre de traces) |
| Résultats d'anomalies | `anomalies/YYYY/MM/DD/{well}_anomalies.json` | Résultats de détection d'anomalies (scores, dépassements de seuil) |
| Résultats Athena | `athena-results/{id}.csv` | Résultats de corrélation d'anomalies inter-puits et séries temporelles |
| Rapport de conformité | `reports/YYYY/MM/DD/compliance_report.md` | Rapport de conformité généré par Bedrock |
| Notification SNS | Email | Notification de fin de rapport et alerte de détection d'anomalies |

---

## Décisions de conception clés

1. **Range Request pour les en-têtes SEG-Y** — Les fichiers SEG-Y peuvent atteindre plusieurs Go, mais les métadonnées sont concentrées dans les premiers 3600 octets. Le Range Request optimise la bande passante et les coûts
2. **Détection statistique d'anomalies** — Méthode basée sur le seuil d'écart-type pour détecter les anomalies sans modèles ML. Les seuils sont paramétrés et ajustables
3. **Athena pour l'analyse de corrélation** — Analyse SQL flexible des patterns d'anomalies à travers plusieurs puits et séries temporelles
4. **Bedrock pour la génération de rapports** — Génération automatique de rapports de conformité en langage naturel conformes aux exigences réglementaires
5. **Pipeline séquentiel** — Step Functions gère les dépendances d'ordre : métadonnées → détection d'anomalies → analyse de corrélation → rapport
6. **Interrogation périodique (non événementielle)** — S3 AP ne prend pas en charge les notifications d'événements, donc une exécution planifiée périodique est utilisée

---

## Services AWS utilisés

| Service | Rôle |
|---------|------|
| FSx for NetApp ONTAP | Stockage des données sismiques et journaux de puits |
| S3 Access Points | Accès serverless aux volumes ONTAP (support Range Request) |
| EventBridge Scheduler | Déclenchement périodique |
| Step Functions | Orchestration du workflow (séquentiel) |
| Lambda | Calcul (Discovery, Seismic Metadata, Anomaly Detection, Athena Analysis, Compliance Report) |
| Glue Data Catalog | Gestion des schémas de données de détection d'anomalies |
| Amazon Athena | Corrélation d'anomalies et agrégation statistique basées sur SQL |
| Amazon Bedrock | Génération de rapports de conformité (Claude / Nova) |
| SNS | Notification de fin de rapport et alerte de détection d'anomalies |
| Secrets Manager | Gestion des identifiants de l'API REST ONTAP |
| CloudWatch + X-Ray | Observabilité |
