# UC20: Viajes y Hospitalidad — Arquitectura

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | Español

## Diagrama de arquitectura

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrada — FSx for ONTAP"]
        DATA["Datos de Viaje/Hospitalidad<br/>Confirmaciones de reserva, avisos de cancelación<br/>Fotos de inspección de instalaciones"]
    end

    subgraph SFN["⚙️ Flujo de trabajo Step Functions"]
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

## Servicios AWS utilizados

| Servicio | Rol |
|----------|-----|
| FSx for ONTAP | Almacenamiento de documentos e imágenes |
| Amazon Textract | Análisis de documentos (Cross-Region us-east-1) |
| Amazon Comprehend | Extracción de entidades y detección de idioma |
| Amazon Rekognition | Análisis de imágenes del estado de instalaciones |
| Amazon Bedrock | Generación de recomendaciones de mantenimiento |

## Decisiones de diseño clave

1. **Procesamiento paralelo** — Extracción de reservas e inspección de instalaciones se ejecutan independientemente
2. **Cross-Region Textract** — Usa us-east-1 para disponibilidad completa de funciones
3. **Detección multilingüe automática** — Comprehend detecta el idioma y selecciona modelos apropiados
4. **Puntuación de limpieza** — Etiquetas Rekognition interpretadas por Bedrock en puntuación 0–100
5. **Aislamiento de errores** — Fallos individuales no detienen el lote completo
