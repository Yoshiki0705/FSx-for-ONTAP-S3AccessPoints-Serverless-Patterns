🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

# Event-Driven Prototype (prototipo basado en eventos)

## Descripción general

Este prototipo es una implementación de referencia de una canalización de
procesamiento de archivos basada en eventos que se anticipa a la futura
funcionalidad de notificación nativa de FSx for ONTAP S3 Access Points (FSx for ONTAP S3 AP).

Utiliza las Event Notifications de un bucket de S3 normal para simular
el comportamiento de la futura notificación nativa de FSx for ONTAP S3 AP.

## Arquitectura

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge habilitado)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (etiquetado de imágenes + generación de metadatos)
          → Latency Reporter Lambda (salida de métricas EMF)
```

## Correspondencia con la futura compatibilidad de FSx for ONTAP S3 AP

| Prototipo actual | Futuro FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| Origen de eventos `aws.s3` | Origen de eventos `aws.fsx` (previsto) |
| Filtrar por nombre de bucket de S3 | Filtrar por alias de S3 AP |
| Lectura mediante S3 GetObject | Lectura mediante S3 AP |

## Cambios necesarios (cuando se admitan las notificaciones nativas)

Cambios necesarios cuando FSx for ONTAP S3 AP admita notificaciones nativas:

### 1. Cambios en la plantilla

```yaml
# Antes (prototipo)
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# Después (FSx for ONTAP S3 AP)
# Eliminar el recurso S3 Bucket y hacer referencia al FSx for ONTAP S3 AP existente
# Actualizar el filtro de origen de la EventBridge Rule
```

### 2. Cambios en la regla de EventBridge

```json
// Antes
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// Después (previsto)
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Cambios en las variables de entorno de Lambda

```yaml
# Antes
SOURCE_BUCKET: !Ref SourceBucket

# Después
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Cambios en el código de Lambda

```python
# Antes (prototipo)
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# Después (FSx for ONTAP S3 AP)
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## Pasos de despliegue

### Requisitos previos

- AWS CLI configurado
- Python 3.12
- Bucket de S3 para el paquete de despliegue de Lambda

### Despliegue

```bash
# 1. Compilar y cargar el paquete de Lambda
# (omitido: automatizado por la canalización de CI/CD)

# 2. Desplegar la pila de SAM
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y las capas compartidas.
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. Cargar un archivo de prueba
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### Ejecución de pruebas

```bash
# Pruebas unitarias
pytest event-driven-prototype/tests/ -v

# Prueba de comparación de latencia (después del despliegue)
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## Estructura de directorios

```
event-driven-prototype/
├── template-deploy.yaml          # Plantilla de CloudFormation
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # Lambda de procesamiento de eventos (compatible con UC11)
│   └── latency_reporter/
│       └── handler.py            # Lambda de medición de latencia
├── tests/
│   ├── test_event_processor.py   # Pruebas unitarias del procesamiento de eventos
│   ├── test_latency_reporter.py  # Pruebas unitarias de la medición de latencia
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # Este documento
```

## Métricas

Se emiten las siguientes métricas en formato CloudWatch EMF:

| Nombre de la métrica | Unidad | Descripción |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | Ocurrencia del evento → inicio del procesamiento |
| `EndToEndDuration` | Milliseconds | Ocurrencia del evento → finalización del procesamiento |
| `ProcessingDuration` | Milliseconds | Tiempo de ejecución del procesamiento |
| `EventVolumePerMinute` | Count | Eventos procesados por minuto |

## Documentos relacionados

- [Diseño de la arquitectura basada en eventos](../docs/event-driven/architecture-design.md)
- [Guía de migración](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
