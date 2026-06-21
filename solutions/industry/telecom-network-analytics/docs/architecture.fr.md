# UC18 : Télécommunications / Analyse Réseau — Détection d'anomalies CDR/journaux réseau et rapports de conformité

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture de bout en bout (Entrée → Sortie)

---

## Diagramme d'architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for ONTAP"]
        DATA["Données Télécom<br/>.csv/.asn1/.parquet (Fichiers CDR)<br/>syslog / SNMP trap (Journaux équipements réseau)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Déclencheur"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Quotidien 00:00 UTC"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Exécution VPC<br/>• Détection fichiers CDR/syslog<br/>• Application filtre suffixes<br/>• Génération manifeste"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• Récupération CDR via S3 AP<br/>• Extraction métadonnées d'appels<br/>(ID appelant, ID appelé, durée, horodatage, ID tour cellulaire)<br/>• Requêtes statistiques trafic Athena<br/>(volume horaire, durée moyenne, appels simultanés pic)"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Analyse Syslog RFC 5424<br/>• Analyse SNMP trap<br/>• Détection pannes équipement<br/>(link-down, erreur matérielle, crash processus)<br/>• Détection dépassement seuil capacité (défaut 80%)"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• Comparaison baseline glissante 7 jours<br/>• Marquage anomalies seuil 3σ<br/>• Notation anomalies"]
        RL["5️⃣ Report Lambda<br/>• Résumé quotidien santé réseau<br/>• Génération rapport alertes anomalies<br/>• Sortie S3 (reports/daily/{YYYY-MM-DD}/)<br/>• Notification SNS<br/>• Métriques CloudWatch EMF"]
    end

    subgraph OUTPUT["📤 Sortie — S3 Bucket"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>Statistiques trafic CDR"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>Analyse pannes équipement"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>Résultats détection anomalies"]
        ERROUT["errors/cdr/{filename}.json<br/>Erreurs analyse CDR"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Alertes anomalies critiques et pannes)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## Décisions de conception clés

1. **Traitement parallèle CDR et syslog** — Parallélisation via Step Functions Map State pour améliorer le débit
2. **Athena pour l'agrégation CDR à grande échelle** — SQL serverless pour agréger efficacement des volumes massifs de CDR
3. **Baseline glissante de 7 jours** — Détection d'anomalies statistique tenant compte des caractéristiques jour de la semaine
4. **Seuil 3σ pour le marquage d'anomalies** — Détecte uniquement les anomalies statistiquement significatives
5. **Isolation des erreurs** — Les échecs d'analyse CDR sont enregistrés sans interrompre le lot entier
6. **Basé sur le polling** — S3 AP ne supporte pas les notifications d'événements

---

## Services AWS utilisés

| Service | Rôle |
|---------|------|
| FSx for ONTAP | Stockage CDR/journaux réseau |
| S3 Access Points | Accès serverless aux volumes ONTAP |
| EventBridge Scheduler | Déclencheur quotidien (00:00 UTC) |
| Step Functions | Orchestration workflow (Map State parallèle) |
| Lambda | Calcul (Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report) |
| Amazon Athena | Requêtes SQL statistiques trafic CDR |
| Amazon Bedrock | Inférence détection anomalies (Claude / Nova) |
| SNS | Notifications alertes anomalies critiques et pannes |
| Secrets Manager | Gestion identifiants ONTAP REST API |
| CloudWatch + X-Ray | Observabilité (Métriques EMF, traçage) |
