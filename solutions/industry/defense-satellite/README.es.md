# UC15: Defensa / Espacio — Pipeline de análisis de imágenes satelitales

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español
📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Script de demostración](docs/demo-guide.es.md) | [Solución de problemas](../docs/phase7-troubleshooting.md)

## Descripción general

Pipeline de análisis automatizado de imágenes satelitales (SAR / óptico) que aprovecha
Amazon FSx for NetApp ONTAP S3 Access Points. Los datos de imágenes satelitales de gran
volumen se almacenan en FSx for ONTAP, y el procesamiento serverless se ejecuta a través
de S3 Access Points.

## Caso de uso

Las agencias de defensa e inteligencia y las organizaciones relacionadas con el espacio
procesan y analizan automáticamente los datos de observación de la Tierra
(Earth Observation) adquiridos por satélite.

### Flujo de procesamiento

```
FSx for ONTAP (almacenamiento de imágenes satelitales)
  → S3 Access Point
    → Flujo de trabajo de Step Functions
      → Discovery: detectar imágenes nuevas (GeoTIFF, NITF, HDF5)
      → Tiling: dividir imágenes grandes en mosaicos (conversión Cloud Optimized GeoTIFF)
      → ObjectDetection: detección de objetos con Rekognition / SageMaker
      → ChangeDetection: detección de cambios mediante comparación de series temporales
      → GeoEnrichment: enriquecimiento de metadatos (coordenadas, fecha/hora de captura, resolución)
      → AlertGeneration: generación de alerta ante detección de anomalías
```

### Datos objetivo

| Formato de datos | Descripción | Tamaño típico |
|-----------|------|-----------|
| GeoTIFF | Imagen satelital óptica | 100 MB – 10 GB |
| NITF | Formato de imagen estándar militar | 500 MB – 50 GB |
| HDF5 | Datos SAR (Sentinel-1, etc.) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | Imagen ya dividida en mosaicos | 10 – 500 MB |

### Servicios de AWS

| Servicio | Uso |
|---------|------|
| FSx for ONTAP | Almacenamiento persistente de imágenes satelitales (control de acceso mediante NTFS ACL) |
| S3 Access Points | Acceso a imágenes desde serverless |
| Step Functions | Orquestación del flujo de trabajo |
| Lambda | División en mosaicos, extracción de metadatos, generación de alertas |
| SageMaker (Batch Transform) | Inferencia ML de detección de objetos / de cambios |
| Amazon Rekognition | Detección de etiquetas (vehículos, edificios, embarcaciones) |
| Amazon Bedrock | Generación de leyendas de imagen, resumen de informes |
| DynamoDB | Gestión del estado de procesamiento, índice de resultados de detección |
| SNS | Notificación de alertas |
| CloudWatch | Observabilidad |

### Idoneidad para Public Sector

- **DoD CC SRG**: FSx for ONTAP está certificado para Impact Level 2/4/5 (GovCloud)
- **CSfC**: NetApp ONTAP está certificado para Commercial Solutions for Classified
- **FedRAMP**: cumple FedRAMP High en AWS GovCloud
- **Soberanía de datos**: los datos permanecen dentro de la región (ap-northeast-1 / us-gov-west-1)

## Pantallas verificadas (capturas de pantalla)

Centrado en **la UI que el personal general utiliza en el día a día**, con base en una
ejecución real verificada en ap-northeast-1 el 2026-05-10. Para las pantallas de consola
orientadas a técnicos (gráficos de Step Functions, etc.), consulte
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md).

### 1. Colocación de imágenes satelitales (vía FSx for ONTAP / S3 Access Point)

La pantalla de confirmación de colocación de las imágenes satelitales a analizar, tal como
la ve el administrador del servidor de archivos. Basta con colocar imágenes nuevas bajo el
prefijo `satellite/YYYY/MM/`, y el flujo de trabajo periódico de Step Functions las recoge
automáticamente.

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     Contenido: listar satellite/2026/05/*.tif vía S3 AP (nombre de objeto, tamaño, fecha de modificación)
     Enmascarar: ID de cuenta, ARN del Access Point, nombres reales de imágenes satelitales -->
![UC15: Colocación de imágenes satelitales](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. Visualización de resultados de análisis (bucket S3 de salida)

Los resultados de detección (`detections/*.json`), los metadatos geográficos
(`enriched/*.json`) y la información de mosaicos (`tiles/*/metadata.json`) se organizan y
almacenan.

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     Contenido: vista general de los 3 prefijos detections/, enriched/, tiles/ en la consola de S3
     Enmascarar: ID de cuenta, prefijo del nombre del bucket -->
![UC15: Bucket S3 de salida](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. Alerta de detección de cambios (notificación por correo SNS)

El correo de alerta SNS que recibe el personal general (operadores). Se envía
automáticamente cuando el área de cambio supera el umbral (1 km² por defecto).

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     Contenido: mostrar alert_type=SATELLITE_CHANGE_DETECTED en un cliente de correo (Gmail/Outlook)
     Enmascarar: dirección de correo del destinatario, dirección del remitente, coordenadas reales, tile_id -->
![UC15: Correo de alerta SNS](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. Contenido del JSON de resultado de detección

Un visor JSON limpio de los resultados de detección (etiqueta, confianza, bbox).

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     Contenido: vista previa del objeto en la consola de S3, contenido del JSON detections
     Enmascarar: ID de cuenta -->
![UC15: Resultados de detección JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
Al automatizar el análisis de imágenes satelitales (detección de objetos, detección de cambios, alertas), se logra un análisis de inteligencia más rápido.

### Metrics
| Métrica | Valor objetivo (ejemplo) |
|-----------|------------|
| Imágenes procesadas / ejecución | > 50 images |
| Precisión de detección de objetos | > 80% |
| Tasa de éxito de detección de cambios | > 85% |
| Tiempo de generación de alertas | < 5 min |
| Coste / ejecución | < $15 |
| Tasa obligatoria de Human Review | 100% (aprobación humana obligatoria antes del envío de la alerta) |

> **Motivo del 100% Human Review**: dado que el impacto en el negocio de una alerta errónea o no detectada es extremadamente grande, la aprobación humana de todos los elementos es obligatoria.

### Measurement Method
Historial de ejecución de Step Functions, resultados de detección de Rekognition, informes de análisis de Bedrock, registros de notificación de SNS y CloudWatch Metrics. Los registros de aprobación se almacenan en DynamoDB para poder rastrear en una auditoría «quién aprobó qué y cuándo».

## Despliegue

### Verificación previa

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Despliegue en un solo paso

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### Despliegue manual

```bash
# Requisito: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Importante**: `S3AccessPointName` es necesario para conceder permisos IAM al S3 AP.
Para más detalles, consulte [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md).

## Estructura de directorios

```
defense-satellite/
├── template.yaml              # Plantilla SAM (desarrollo)
├── template-deploy.yaml       # Plantilla CloudFormation (despliegue)
├── functions/
│   ├── discovery/handler.py   # Detección de imágenes satelitales nuevas
│   ├── tiling/handler.py      # División en mosaicos + conversión COG
│   ├── object_detection/handler.py  # Detección de objetos (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # Detección de cambios por serie temporal
│   ├── geo_enrichment/handler.py    # Enriquecimiento de metadatos geográficos
│   └── alert_generation/handler.py  # Generación de alertas
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## Enlaces a la documentación de AWS

| Servicio | Documentación |
|---------|------------|
| FSx for ONTAP | [Guía del usuario](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guía del desarrollador](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [Guía del desarrollador](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [Guía del desarrollador](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [Guía del usuario](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Alineación con el Well-Architected Framework

| Pilar | Alineación |
|----|------|
| Excelencia operativa | X-Ray, EMF, generación de alertas, 100% Human Review |
| Seguridad | DoD CC SRG, FedRAMP, IAM de mínimo privilegio, KMS, aislamiento de VPC |
| Fiabilidad | Step Functions Retry/Catch, pruebas de resiliencia, reserva |
| Eficiencia del rendimiento | Mosaico COG, detección de objetos en paralelo, SageMaker Batch |
| Optimización de costes | Serverless, SageMaker Spot, procesamiento por mosaico |
| Sostenibilidad | Ejecución bajo demanda, detección de cambios diferencial |





---

## Estimación de costes (aproximado mensual)

> **Nota**: las siguientes son cifras aproximadas para la región ap-northeast-1; los costes reales varían según el uso. Consulte los precios más recientes en la [AWS Pricing Calculator](https://calculator.aws/).

### Componentes serverless (pago por uso)

| Servicio | Precio unitario | Uso supuesto | Aprox. mensual |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 funciones × 10 scenes/día | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/día | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/día | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/ejecución | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/consulta | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/día | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mes | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### Coste fijo (FSx for ONTAP — se asume un entorno existente)

| Componente | Mensual |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (entorno existente compartido) |
| S3 Access Point | Sin cargo adicional (solo cargos de API de S3) |

### Total aproximado

| Configuración | Aprox. mensual |
|------|---------|
| Configuración mínima (una vez al día) | ~$5-15 |
| Configuración estándar (por hora) | ~$15-50 |
| Configuración a gran escala (alta frecuencia + alarmas) | ~$50-150 |

> **Governance Caveat**: las estimaciones de costes son aproximadas, no valores garantizados. El importe realmente facturado varía según el patrón de uso, el volumen de datos y la región.

---

## Pruebas locales

### Comprobación de prerrequisitos

```bash
# Comprobar los prerrequisitos
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (para sam local)
aws sts get-caller-identity  # Credenciales de AWS
```

### sam local invoke

```bash
# Build
# Requisito: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y la capa compartida.
sam build

# Ejecutar la Lambda Discovery en local
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

Para más detalles, consulte [Inicio rápido de pruebas locales](../docs/local-testing-quick-start.md).

---

## Muestra de salida (Output Sample)

Ejemplo de salida del pipeline de análisis de imágenes satelitales (Human Review requerido):

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **Nota**: lo anterior es una salida de muestra; los valores reales varían según el entorno y los datos de entrada. Las cifras de benchmark son una referencia de dimensionamiento, no un límite de servicio.

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Las organizaciones deben consultar a profesionales cualificados.

---

## S3AP Compatibility

Para las restricciones de compatibilidad, la solución de problemas y los patrones de activación de S3 Access Points for FSx for ONTAP, consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
