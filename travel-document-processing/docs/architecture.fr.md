# UC20 : Voyage et Hôtellerie — Architecture

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Diagramme d'architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for ONTAP"]
        DATA["Données Voyage/Hôtellerie<br/>Confirmations de réservation, avis d'annulation<br/>Photos d'inspection des installations"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda"]
        RE["2️⃣ Reservation Extractor Lambda<br/>Textract + Comprehend"]
        FI["3️⃣ Facility Inspector Lambda<br/>Rekognition + Bedrock"]
        RL["4️⃣ Report Lambda"]
    end

    DISC --> RE
    DISC --> FI
    RE --> RL
    FI --> RL
```

## Services AWS utilisés

| Service | Rôle |
|---------|------|
| FSx for ONTAP | Stockage des documents et images |
| Amazon Textract | Analyse de documents (Cross-Region us-east-1) |
| Amazon Comprehend | Extraction d'entités et détection de langue |
| Amazon Rekognition | Analyse d'images de l'état des installations |
| Amazon Bedrock | Génération de recommandations de maintenance |

## Décisions de conception clés

1. **Traitement parallèle** — Extraction des réservations et inspection des installations exécutées indépendamment
2. **Cross-Region Textract** — Utilise us-east-1 pour la disponibilité complète des fonctionnalités
3. **Détection multilingue automatique** — Comprehend détecte la langue et sélectionne les modèles appropriés
4. **Score de propreté** — Labels Rekognition interprétés par Bedrock en score 0–100
5. **Isolation des erreurs** — Les échecs individuels n'arrêtent pas le lot
