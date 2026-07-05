# UC17: Smart City — Análisis geoespacial y planificación urbana

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español
📚 **Documentación**: [Arquitectura](docs/architecture.md) | [Script de demostración](docs/demo-guide.md) | [Solución de problemas](../docs/phase7-troubleshooting.md)

## Descripción general

Canal de análisis automatizado de datos geoespaciales (SIG) basado en
FSx for ONTAP S3 Access Points. Integra imágenes satelitales, LiDAR y
datos de sensores IoT para la planificación urbana, la supervisión de infraestructuras y la respuesta a desastres.

## Caso de uso

Los gobiernos locales y las agencias de planificación urbana integran datos
geoespaciales de múltiples fuentes para automatizar la supervisión del estado
de la infraestructura urbana, la detección de cambios y la evaluación de riesgos de desastre.

### Flujo de procesamiento

```
FSx for ONTAP (almacenamiento de datos SIG — control de acceso por departamento)
  → S3 Access Point
    → Flujo de trabajo de Step Functions
      → Discovery: detección de nuevos datos (GeoTIFF, Shapefile, GeoJSON, LAS)
      → Preprocessing: conversión / normalización del sistema de coordenadas (unificación EPSG, EPSG:4326)
      → LandUseClassification: clasificación del uso del suelo (inferencia de ML)
      → ChangeDetection: detección de cambios en series temporales (nuevas construcciones, reducción de zonas verdes)
      → InfraAssessment: evaluación del deterioro de infraestructuras (carreteras, puentes, nubes de puntos LAS)
      → RiskMapping: generación de mapas de riesgo de desastres (inundación, terremoto, deslizamiento)
      → ReportGeneration: generación de informes de planificación urbana (Bedrock Nova Lite)
```

### Datos objetivo

| Formato de datos | Descripción | Tamaño típico |
|-----------|------|-----------|
| GeoTIFF | Fotografías aéreas / imágenes satelitales | 100 MB – 10 GB |
| Shapefile (.shp) | Datos vectoriales (carreteras, edificios, parcelas) | 1 – 500 MB |
| GeoJSON | Datos vectoriales ligeros | 1 KB – 100 MB |
| LAS / LAZ | Nubes de puntos LiDAR (terreno / edificios 3D) | 100 MB – 5 GB |
| GeoPackage (.gpkg) | Base de datos SIG del estándar OGC | 10 MB – 2 GB |

### Servicios de AWS

| Servicio | Uso |
|---------|------|
| FSx for ONTAP | Almacenamiento persistente de datos SIG (NTFS ACL por departamento) |
| S3 Access Points | Acceso a datos desde componentes serverless |
| Step Functions | Orquestación del flujo de trabajo |
| Lambda | Preprocesamiento, conversión de coordenadas, extracción de metadatos |
| SageMaker (Batch Transform) | Clasificación del uso del suelo, inferencia de ML para detección de cambios (opcional) |
| Amazon Rekognition | Detección de objetos a partir de imágenes aéreas (edificios, vehículos) |
| Amazon Bedrock Nova Lite | Generación de informes de planificación urbana en japonés |
| DynamoDB | Historial de uso del suelo en series temporales, detección de cambios |
| SNS | Alertas de detección de anomalías |
| CloudWatch | Observabilidad |

### Adecuación al sector público

- **Compatibilidad con la Directiva INSPIRE** (infraestructura de datos geoespaciales de la UE)
- **Cumplimiento de los estándares OGC**: WMS, WFS, WCS, GeoPackage
- **Datos abiertos**: los resultados del procesamiento pueden publicarse en portales para la ciudadanía
- **Respuesta a desastres**: cartografía en tiempo real de la situación de daños
- **Soberanía de los datos**: los datos municipales permanecen dentro de la región

### Escenarios de uso

| Escenario | Datos de entrada | Salida |
|---------|-----------|------|
| Supervisión de la reforestación urbana | Imágenes satelitales (serie temporal) | Informe de cambio de zonas verdes |
| Detección de vertidos ilegales | Imágenes de dron | Alerta + información de ubicación |
| Evaluación del deterioro de carreteras | Imágenes de cámara embarcada | Mapa de prioridad de reparación |
| Evaluación del riesgo de inundación | LiDAR + datos de precipitación | Mapa de predicción de inundaciones |
| Apoyo a la verificación de edificación | Imágenes aéreas + solicitud de edificación | Informe de detección de diferencias |

## Pantallas verificadas (capturas de pantalla)

### 1. Almacenamiento de datos SIG (vía S3 Access Point)

Pantalla de confirmación de la ubicación de los datos a analizar, vista por un técnico SIG del municipio.
Se colocan GeoTIFF / Shapefile / LAS bajo el prefijo `gis/YYYY/MM/`.

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     Contenido: listado del prefijo gis/ del S3 AP, formatos de archivo mixtos
     Máscara: ID de cuenta, ARN del S3 AP, nombres de archivo derivados de coordenadas reales -->
![UC17: confirmación del almacenamiento de datos SIG](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Informe de planificación urbana generado por Bedrock (vista Markdown)

**Función destacada de UC17**: al integrar la distribución del uso del suelo,
la detección de cambios y la evaluación de riesgos, Bedrock Nova Lite genera
automáticamente un informe en japonés para el personal municipal.

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     Contenido: reports/*.md renderizado en la consola de S3
     Contenido real de la muestra:
       ### Informe de observaciones para el personal municipal
       #### Puntos de atención para la planificación urbana
       Según los datos SIG, la distribución del uso del suelo en la ciudad es estable...
       #### Medidas prioritarias a considerar
       1. Reforzar las medidas contra inundaciones ... 2. Reforzar las medidas antisísmicas ... 3. Reforzar las medidas contra deslizamientos de laderas ...
     Máscara: ID de cuenta, nombre del municipio (solo se muestra el nombre de muestra) -->
![UC17: informe generado por Bedrock](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. JSON del mapa de riesgo de desastres

Tres tipos de puntuaciones de riesgo — inundación, terremoto y deslizamiento — se clasifican
en cuatro niveles: CRITICAL / HIGH / MEDIUM / LOW.

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     Contenido: vista formateada de risk-maps/*.json (level de flood, earthquake, landslide resaltado)
     Máscara: ID de cuenta -->
![UC17: mapa de riesgo de desastres](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. Distribución del uso del suelo (JSON)

La distribución de clases de uso del suelo derivada de los resultados de inferencia de Rekognition / SageMaker.
Proporciones de residential / commercial / forest / water / road, etc.

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     Contenido: contenido de landuse/*.json (residential: 0.5, forest: 0.3, etc.)
     Máscara: ID de cuenta -->
![UC17: distribución del uso del suelo](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. Visualización del cambio en series temporales (DynamoDB Explorer)

Tabla `fsxn-uc17-demo-landuse-history`. Para cada area_id, se comparan las
distribuciones pasadas del uso del suelo con los valores actuales para calcular change_magnitude.

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     Contenido: elementos de series temporales de la tabla landuse-history en DynamoDB Explorer
     Máscara: ID de cuenta, area_id -->
![UC17: tabla de cambios en series temporales](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
Al automatizar el análisis geoespacial (normalización CRS, clasificación del uso del suelo, cartografía de riesgos de desastre), apoya la toma de decisiones en la planificación urbana.

### Metrics
| Métrica | Valor objetivo (ejemplo) |
|-----------|------------|
| Conjuntos de datos procesados / ejecución | > 100 files |
| Tasa de éxito de la normalización CRS | > 95% |
| Precisión de la clasificación del uso del suelo | > 80% |
| Tiempo de generación del mapa de riesgo | < 10 min |
| Coste / ejecución | < $10 |
| Tasa objetivo de Human Review | < 20 % (áreas con clasificación incierta) |

### Measurement Method
Historial de ejecución de Step Functions, informes de análisis de Bedrock, resultados de detección de Rekognition, GeoJSON de salida de S3, CloudWatch Metrics.

## Despliegue

### Verificación previa

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Despliegue en un solo paso

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### Despliegue manual

```bash
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=apac.amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Importante**: habilite el acceso al modelo `apac.amazon.nova-lite-v1:0` en la consola de Bedrock.

## Estructura de directorios

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # normalización CRS (EPSG:4326)
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # análisis de nubes de puntos LAS/LAZ
│   ├── risk_mapping/handler.py           # riesgo de inundación/terremoto/deslizamiento
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## Enlaces a la documentación de AWS

| Servicio | Documentación |
|---------|------------|
| FSx for ONTAP | [Guía del usuario](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guía del desarrollador](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [Guía del desarrollador](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [Guía del desarrollador](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [Guía del usuario](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Alineación con el Well-Architected Framework

| Pilar | Alineación |
|----|------|
| Excelencia operativa | X-Ray, EMF, seguimiento de cambios del uso del suelo, pruebas de resiliencia |
| Seguridad | IAM de privilegio mínimo, KMS, NTFS ACL por departamento, cumplimiento de INSPIRE |
| Fiabilidad | Step Functions Retry/Catch, normalización CRS, pruebas de resiliencia |
| Eficiencia del rendimiento | Mosaico de GeoTIFF, SageMaker Batch Transform |
| Optimización de costes | Serverless, SageMaker Spot, series temporales de DynamoDB |
| Sostenibilidad | Detección incremental de cambios, cumplimiento de los estándares OGC |





---

## Estimación de costes (aproximación mensual)

> **Nota**: lo siguiente es una estimación para la región ap-northeast-1; los costes reales varían según el uso. Consulte los precios más recientes con la [AWS Pricing Calculator](https://calculator.aws/).

### Componentes serverless (pago por uso)

| Servicio | Precio unitario | Uso estimado | Aprox. mensual |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 funciones × 20 datasets/día | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/día | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/día | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/ejecución | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/consulta | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/día | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mes | ~$0.76 |

### Costes fijos (FSx for ONTAP — se presupone un entorno existente)

| Componente | Mensual |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (entorno existente compartido) |
| S3 Access Point | Sin cargo adicional (solo cargos de S3 API) |

### Estimación total

| Configuración | Aprox. mensual |
|------|---------|
| Configuración mínima (una vez al día) | ~$5-15 |
| Configuración estándar (por hora) | ~$15-50 |
| Configuración a gran escala (alta frecuencia + alarmas) | ~$50-150 |

> **Governance Caveat**: las estimaciones de coste son aproximadas y no garantizadas. La facturación real varía según los patrones de uso, el volumen de datos y la región.

---

## Pruebas locales

### Comprobación de requisitos previos

```bash
# Verificar los requisitos previos
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (para sam local)
aws sts get-caller-identity  # Credenciales de AWS
```

### sam local invoke

```bash
# Build
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

# Ejecutar la Lambda Discovery localmente
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Con sobrescritura de variables de entorno
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Pruebas unitarias

```bash
python3 -m pytest tests/ -v
```

Para más detalles, consulte el [Inicio rápido de pruebas locales](../docs/local-testing-quick-start.md).

---

## Muestra de salida (Output Sample)

Ejemplo de salida del canal de análisis de datos geoespaciales:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **Nota**: lo anterior es una salida de muestra; los valores reales varían según el entorno y los datos de entrada. Las cifras de referencia son una referencia de dimensionamiento, no un límite de servicio.

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Las organizaciones deben consultar a profesionales cualificados.

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la solución de problemas y los patrones de activación de S3 Access Points for FSx for ONTAP, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
