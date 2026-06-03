# UC19 : Publicité et Marketing / Gestion des Actifs Créatifs — Catalogage et Vérification de Conformité de Marque

🌐 **Language / Langue** : [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture de Bout en Bout (Entrée → Sortie)

---

## Diagramme d'Architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for ONTAP"]
        DATA["Actifs Créatifs<br/>.jpeg/.png/.tiff (Images)<br/>.mp4/.mov (Vidéo)<br/>.psd (Fichiers Design)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Déclencheur"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Quotidien 00:00 UTC"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Exécution dans VPC<br/>• Détection de fichiers média<br/>• Filtre format + taille (limite 5 Go)<br/>• Génération du Manifest"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• Récupération via S3 AP<br/>• Rekognition DetectLabels (seuil 80%)<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• Jusqu'à 50 étiquettes/actif"]
        TC["3️⃣ Text Compliance Lambda<br/>• Extraction texte Textract (us-east-1 inter-régions)<br/>• Chargement JSON directives de marque<br/>• Bedrock InvokeModel — vérification conformité<br/>• Résultat : conforme / non-conforme + termes correspondants"]
        RL["4️⃣ Report Lambda<br/>• Génération catalogue d'actifs (JSON + CSV)<br/>• Signalement violations modération (requires-review)<br/>• Émission CloudWatch EMF Metrics<br/>• Notification SNS"]
    end

    subgraph OUTPUT["📤 Sortie — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json"]
        CSV["reports/{execution-id}/asset-catalog.csv"]
        FLAGGED["reports/{execution-id}/flagged-assets.json"]
        ERROUT["errors/{execution-id}/{filename}.json"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    RL --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
```

---

## Services AWS Utilisés

| Service | Rôle |
|---------|------|
| FSx for ONTAP | Stockage des actifs créatifs |
| S3 Access Points | Accès serverless aux volumes ONTAP |
| EventBridge Scheduler | Déclenchement quotidien (00:00 UTC) |
| Step Functions | Orchestration workflow (Map State parallèle) |
| Lambda | Calcul (Discovery, Visual Analyzer, Text Compliance, Report) |
| Amazon Rekognition | Analyse visuelle (étiquettes, modération, détection de texte) |
| Amazon Textract | Extraction de texte superposé (us-east-1 inter-régions) |
| Amazon Bedrock | Inférence conformité marque (Claude / Nova) |
| SNS | Notification d'alerte violation modération |
| CloudWatch + X-Ray | Observabilité (EMF Metrics, traçage) |
