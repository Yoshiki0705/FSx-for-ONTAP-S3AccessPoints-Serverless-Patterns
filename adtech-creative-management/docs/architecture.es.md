# UC19: Publicidad y Marketing / Gestión de Activos Creativos — Catalogación de Activos y Verificación de Cumplimiento de Marca

🌐 **Language / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | Español

## Arquitectura de Extremo a Extremo (Entrada → Salida)

---

## Diagrama de Arquitectura

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrada — FSx for ONTAP"]
        DATA["Activos Creativos<br/>.jpeg/.png/.tiff (Imágenes)<br/>.mp4/.mov (Video)<br/>.psd (Archivos de Diseño)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Disparador"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Diario 00:00 UTC"]
    end

    subgraph SFN["⚙️ Flujo de Trabajo Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Ejecución en VPC<br/>• Detección de archivos de medios<br/>• Filtro de formato + tamaño (límite 5 GB)<br/>• Generación de Manifest"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• Obtención de activo vía S3 AP<br/>• Rekognition DetectLabels (umbral 80%)<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• Hasta 50 etiquetas/activo"]
        TC["3️⃣ Text Compliance Lambda<br/>• Extracción de texto Textract (us-east-1 cross-region)<br/>• Carga de JSON de directrices de marca<br/>• Bedrock InvokeModel — verificación de cumplimiento<br/>• Resultado: conforme / no conforme + términos coincidentes"]
        RL["4️⃣ Report Lambda<br/>• Generación de catálogo de activos (JSON + CSV)<br/>• Señalamiento de violaciones de moderación (requires-review)<br/>• Emisión de CloudWatch EMF Metrics<br/>• Notificación SNS"]
    end

    subgraph OUTPUT["📤 Salida — S3 Bucket"]
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

## Servicios AWS Utilizados

| Servicio | Rol |
|----------|-----|
| FSx for ONTAP | Almacenamiento de activos creativos |
| S3 Access Points | Acceso serverless a volúmenes ONTAP |
| EventBridge Scheduler | Disparador diario (00:00 UTC) |
| Step Functions | Orquestación de flujo de trabajo (Map State paralelo) |
| Lambda | Cómputo (Discovery, Visual Analyzer, Text Compliance, Report) |
| Amazon Rekognition | Análisis visual (etiquetas, moderación, detección de texto) |
| Amazon Textract | Extracción de texto superpuesto (us-east-1 cross-region) |
| Amazon Bedrock | Inferencia de cumplimiento de marca (Claude / Nova) |
| SNS | Notificación de alerta de violación de moderación |
| CloudWatch + X-Ray | Observabilidad (EMF Metrics, rastreo) |
