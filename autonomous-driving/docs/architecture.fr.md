# UC9: Conduite autonome / ADAS — Prétraitement vidéo et LiDAR, contrôle qualité et annotation

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | Français | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture de bout en bout (Entrée → Sortie)

---

## Diagramme d'architecture

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrée — FSx for NetApp ONTAP"]
        DATA["Données vidéo / LiDAR<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Déclencheur"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Workflow Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Exécution dans le VPC<br/>• Découverte de fichiers via S3 AP<br/>• Filtre .bag/.pcd/.mp4/.h264<br/>• Génération du manifeste"]
        FE["2️⃣ Frame Extraction Lambda<br/>• Extraction d'images clés depuis la vidéo<br/>• Rekognition DetectLabels<br/>  (véhicules, piétons, panneaux de signalisation)<br/>• Sortie d'images de trames vers S3"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• Récupération du nuage de points LiDAR<br/>• Contrôles qualité<br/>  (densité de points, intégrité des coordonnées, validation NaN)<br/>• Génération du rapport QC"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Suggestions d'annotation Bedrock<br/>• Génération JSON compatible COCO<br/>• Gestion des tâches d'annotation"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Exécution Batch Transform<br/>• Inférence de segmentation du nuage de points<br/>• Sortie des résultats de détection d'objets"]
    end

    subgraph OUTPUT["📤 Sortie — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>Images clés extraites"]
        QCR["qc-reports/*.json<br/>Rapports qualité du nuage de points"]
        ANNOT["annotations/*.json<br/>Annotations COCO"]
        INFER["inference/*.json<br/>Résultats d'inférence ML"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Notification de fin de traitement"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> FE
    DISC --> PC
    FE --> AM
    PC --> AM
    AM --> SM
    FE --> FRAMES
    PC --> QCR
    AM --> ANNOT
    SM --> INFER
    SM --> SNS
```

---

## Détail du flux de données

### Entrée
| Élément | Description |
|---------|-------------|
| **Source** | Volume FSx for NetApp ONTAP |
| **Types de fichiers** | .bag, .pcd, .mp4, .h264 (ROS bag, nuage de points LiDAR, vidéo dashcam) |
| **Méthode d'accès** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Stratégie de lecture** | Récupération complète du fichier (nécessaire pour l'extraction de trames et l'analyse du nuage de points) |

### Traitement
| Étape | Service | Fonction |
|-------|---------|----------|
| Discovery | Lambda (VPC) | Découverte des données vidéo/LiDAR via S3 AP, génération du manifeste |
| Frame Extraction | Lambda + Rekognition | Extraction d'images clés depuis la vidéo, détection d'objets |
| Point Cloud QC | Lambda | Contrôles qualité du nuage de points LiDAR (densité de points, intégrité des coordonnées, validation NaN) |
| Annotation Manager | Lambda + Bedrock | Génération de suggestions d'annotation, sortie JSON COCO |
| SageMaker Invoke | Lambda + SageMaker | Batch Transform pour l'inférence de segmentation du nuage de points |

### Sortie
| Artefact | Format | Description |
|----------|--------|-------------|
| Images clés | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | Images clés extraites |
| Rapport QC | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | Résultats du contrôle qualité du nuage de points |
| Annotations | `annotations/YYYY/MM/DD/{stem}_coco.json` | Annotations compatibles COCO |
| Inférence | `inference/YYYY/MM/DD/{stem}_segmentation.json` | Résultats d'inférence ML |
| Notification SNS | E-mail | Notification de fin de traitement (nombre et scores de qualité) |

---

## Décisions de conception clés

1. **S3 AP plutôt que NFS** — Pas de montage NFS nécessaire depuis Lambda ; données volumineuses récupérées via l'API S3
2. **Traitement parallèle** — Frame Extraction et Point Cloud QC s'exécutent en parallèle pour réduire le temps de traitement
3. **Rekognition + SageMaker en deux étapes** — Rekognition pour la détection d'objets immédiate, SageMaker pour la segmentation haute précision
4. **Format compatible COCO** — Format d'annotation standard de l'industrie garantissant la compatibilité avec les pipelines ML en aval
5. **Porte de qualité** — Point Cloud QC filtre les données ne répondant pas aux normes de qualité en début de pipeline
6. **Interrogation périodique (non événementielle)** — S3 AP ne prend pas en charge les notifications d'événements, une exécution planifiée périodique est donc utilisée

---

## Services AWS utilisés

| Service | Rôle |
|---------|------|
| FSx for NetApp ONTAP | Stockage de données de conduite autonome (vidéo et LiDAR) |
| S3 Access Points | Accès serverless aux volumes ONTAP |
| EventBridge Scheduler | Déclencheur périodique |
| Step Functions | Orchestration du workflow |
| Lambda | Calcul (Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke) |
| Amazon Rekognition | Détection d'objets (véhicules, piétons, panneaux de signalisation) |
| Amazon SageMaker | Batch Transform (inférence de segmentation du nuage de points) |
| Amazon Bedrock | Génération de suggestions d'annotation |
| SNS | Notification de fin de traitement |
| Secrets Manager | Gestion des identifiants de l'API REST ONTAP |
| CloudWatch + X-Ray | Observabilité |
