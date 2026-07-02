# UC4: Medios — Pipeline de Renderizado VFX

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Diagrama de arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Resumen

Un flujo de trabajo sin servidor que aprovecha los S3 Access Points de FSx for ONTAP para automatizar el envío de trabajos de renderizado VFX, las verificaciones de calidad y la reescritura de las salidas aprobadas.

### Cuándo es adecuado este patrón

- Utiliza FSx for ONTAP como almacenamiento de renderizado para producción de VFX / animación
- Desea automatizar las verificaciones de calidad tras el renderizado y reducir la carga de la revisión manual
- Desea reescribir automáticamente en el servidor de archivos los recursos que pasaron las verificaciones de calidad (S3 AP PutObject)
- Desea construir un pipeline que integre Deadline Cloud con un almacenamiento NAS existente

### Cuándo no es adecuado este patrón

- Necesita un inicio inmediato de los trabajos de renderizado (desencadenadores al guardar archivos)
- Utiliza una granja de renderizado distinta de Deadline Cloud (p. ej., Thinkbox Deadline local)
- La salida de renderizado supera los 5 GB (el límite de S3 AP PutObject)
- Las verificaciones de calidad requieren un modelo propio de evaluación de la calidad de imagen (la detección de etiquetas de Rekognition es insuficiente)

### Características principales

- Detección automática de los recursos de renderizado objetivo a través de S3 AP
- Envío automático de trabajos de renderizado a AWS Deadline Cloud
- Evaluación de calidad mediante Amazon Rekognition (resolución, artefactos, coherencia de color)
- Si pasa, PutObject a FSx for ONTAP a través de S3 AP; si falla, notificación SNS

## Success Metrics

### Outcome
Reducir el tiempo de búsqueda de recursos mediante la clasificación automática y el etiquetado de metadatos de los recursos VFX.

### Metrics
| Métrica | Valor objetivo (ejemplo) |
|-----------|------------|
| Recursos procesados por ejecución | > 200 files |
| Tasa de éxito del etiquetado de metadatos | > 95% |
| Reducción del tiempo de búsqueda de recursos | > 60% |
| Tiempo de procesamiento por archivo | < 60 s |
| Coste por ejecución | < $10 |
| Tasa sujeta a Human Review | < 10% |

### Measurement Method
Historial de ejecución de Step Functions, Rekognition label count, metadatos de salida de S3.

## Arquitectura

```mermaid
graph LR
    subgraph "Flujo de trabajo de Step Functions"
        D[Discovery Lambda<br/>Detección de recursos]
        JS[Job Submit Lambda<br/>Envío de trabajo a Deadline Cloud]
        QC[Quality Check Lambda<br/>Evaluación de calidad con Rekognition]
    end

    D -->|Manifest| JS
    JS -->|Job Result| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    JS -.->|GetObject| S3AP
    JS -.->|CreateJob| DC[AWS Deadline Cloud]
    QC -.->|DetectLabels| Rekognition[Amazon Rekognition]
    QC -.->|PutObject (si pasa)| S3AP
    QC -.->|Publish (si falla)| SNS[SNS Topic]
```

### Pasos del flujo de trabajo

1. **Discovery**: Detectar los recursos de renderizado objetivo desde el S3 AP y generar un Manifest
2. **Job Submit**: Recuperar los recursos a través del S3 AP y enviar los trabajos de renderizado a AWS Deadline Cloud
3. **Quality Check**: Evaluar la calidad de los resultados de renderizado con Rekognition. Si pasa, PutObject al S3 AP; si falla, marcar para volver a renderizar mediante una notificación SNS

## Requisitos previos

- Una cuenta de AWS y los permisos IAM adecuados
- Un sistema de archivos FSx for ONTAP (ONTAP 9.17.1P4D3 o posterior)
- Un volumen con S3 Access Points habilitados
- Credenciales de la ONTAP REST API registradas en Secrets Manager
- Una VPC y subredes privadas
- Una Farm / Queue de AWS Deadline Cloud ya configurada
- Una región donde Amazon Rekognition esté disponible

## Pasos de implementación

### 1. Preparar los parámetros

Antes de la implementación, confirme los siguientes valores:

- FSx for ONTAP S3 Access Point Alias
- Dirección IP de gestión de ONTAP
- Nombre del secreto de Secrets Manager
- AWS Deadline Cloud Farm ID / Queue ID
- VPC ID, ID de subred privada

### 2. Implementación con SAM

```bash
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta el código y la capa compartida automáticamente.
sam build

sam deploy \
  --stack-name fsxn-media-vfx \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    S3AccessPointOutputAlias=<your-output-volume-ext-s3alias> \
    OntapSecretName=<your-ontap-secret-name> \
    OntapManagementIp=<your-ontap-management-ip> \
    ScheduleExpression="rate(1 hour)" \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    DeadlineFarmId=<your-deadline-farm-id> \
    DeadlineQueueId=<your-deadline-queue-id> \
    QualityThreshold=80.0 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Nota**: `template.yaml` se usa con la SAM CLI (`sam build` + `sam deploy`).
> Para implementar directamente con el comando `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (esto requiere empaquetar previamente los archivos zip de Lambda y subirlos a S3).

> **Nota**: Reemplace los marcadores de posición `<...>` con los valores reales de su entorno.

### 3. Confirmar la suscripción a SNS

Tras la implementación, se envía un correo electrónico de confirmación de suscripción a SNS a la dirección de correo electrónico que especificó.

> **Nota**: Si omite `S3AccessPointName`, la política IAM queda basada solo en el Alias, lo que puede provocar un error `AccessDenied`. Se recomienda especificarlo en un entorno de producción. Para más detalles, consulte la [Guía de solución de problemas](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー).

## Lista de parámetros de configuración

| Parámetro | Descripción | Predeterminado | Obligatorio |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx for ONTAP S3 AP Alias (para entrada) | — | ✅ |
| `S3AccessPointName` | Nombre del S3 AP (para la concesión de permisos IAM basados en ARN; solo basado en Alias si se omite) | `""` | ⚠️ Recomendado |
| `S3AccessPointOutputAlias` | FSx for ONTAP S3 AP Alias (para salida) | — | ✅ |
| `OntapSecretName` | Nombre del secreto de Secrets Manager para las credenciales de ONTAP | — | ✅ |
| `OntapManagementIp` | Dirección IP de gestión del clúster de ONTAP | — | ✅ |
| `ScheduleExpression` | Expresión de programación de EventBridge Scheduler | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | Lista de ID de subredes privadas | — | ✅ |
| `NotificationEmail` | Dirección de correo electrónico de notificación de SNS | — | ✅ |
| `DeadlineFarmId` | AWS Deadline Cloud Farm ID | — | ✅ |
| `DeadlineQueueId` | AWS Deadline Cloud Queue ID | — | ✅ |
| `QualityThreshold` | Umbral de evaluación de calidad de Rekognition (0.0–100.0) | `80.0` | |
| `EnableVpcEndpoints` | Habilitar Interface VPC Endpoints | `false` | |
| `EnableCloudWatchAlarms` | Habilitar CloudWatch Alarms | `false` | |

## Estructura de costes

### Basado en solicitudes (pago por uso)

| Servicio | Unidad de facturación | Estimación (100 recursos/mes) |
|---------|---------|----------------------|
| Lambda | Número de solicitudes + tiempo de ejecución | ~$0.01 |
| Step Functions | Número de transiciones de estado | Dentro del nivel gratuito |
| S3 API | Número de solicitudes | ~$0.01 |
| Rekognition | Número de imágenes | ~$0.10 |
| Deadline Cloud | Tiempo de renderizado | Estimado por separado※ |

※ El coste de AWS Deadline Cloud depende de la escala y la duración de los trabajos de renderizado.

### Siempre activo (opcional)

| Servicio | Parámetro | Mensual |
|---------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints=true` | ~$28.80 |
| CloudWatch Alarms | `EnableCloudWatchAlarms=true` | ~$0.20 |

> En un entorno de demostración/PoC, puede empezar desde **~$0.12/mes** con solo los costes variables (excluyendo Deadline Cloud).

## Limpieza

```bash
# Eliminar la pila de CloudFormation
aws cloudformation delete-stack \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1

# Esperar a que se complete la eliminación
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1
```

> **Nota**: La eliminación de la pila puede fallar si quedan objetos en el bucket de S3. Vacíe el bucket de antemano.

## Supported Regions

UC4 utiliza los siguientes servicios:

| Servicio | Restricción de región |
|---------|-------------|
| Amazon Rekognition | Disponible en casi todas las regiones |
| AWS Deadline Cloud | Disponibilidad regional limitada ([Regiones compatibles con Deadline Cloud](https://docs.aws.amazon.com/general/latest/gr/deadline-cloud.html)) |
| AWS X-Ray | Disponible en casi todas las regiones |
| CloudWatch EMF | Disponible en casi todas las regiones |

> Para más detalles, consulte la [Matriz de compatibilidad de regiones](../docs/region-compatibility.md).

## Enlaces de referencia

### Documentación oficial de AWS

- [Descripción general de FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Streaming con CloudFront (tutorial oficial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html)
- [Procesamiento sin servidor con Lambda (tutorial oficial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Referencia de la API de Deadline Cloud](https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html)
- [Rekognition DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html)

### Artículos del blog de AWS

- [Blog de anuncio de S3 AP](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
- [Tres patrones de arquitectura sin servidor](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### Ejemplos de GitHub

- [aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing](https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing) — Procesamiento de Rekognition a gran escala
- [aws-samples/dotnet-serverless-imagerecognition](https://github.com/aws-samples/dotnet-serverless-imagerecognition) — Step Functions + Rekognition
- [aws-samples/serverless-patterns](https://github.com/aws-samples/serverless-patterns) — Colección de patrones sin servidor

### Guías internas del proyecto

- [FlexClone Serverless Patterns (japonés)](../docs/guides/flexclone-serverless-patterns.md) — Pipeline de procesamiento de fotogramas secuenciales con FlexClone + Step Functions + S3AP, montaje multiprotocolo, casos de uso por sector
- [FlexClone Serverless Patterns (English)](../docs/guides/flexclone-serverless-patterns-en.md) — FlexClone + Step Functions + S3AP sequential frame processing pipeline

## Entorno validado

| Elemento | Valor |
|------|-----|
| Región de AWS | ap-northeast-1 (Tokio) |
| Versión de FSx for ONTAP | ONTAP 9.17.1P4D3 |
| Configuración de FSx | SINGLE_AZ_1 |
| Python | 3.12 |
| Método de implementación | CloudFormation (estándar) |

## Arquitectura de ubicación VPC de Lambda

Sobre la base de las lecciones aprendidas durante la validación, las funciones Lambda se distribuyen dentro y fuera de la VPC.

**Lambda dentro de la VPC** (solo las funciones que requieren acceso a la ONTAP REST API):
- Discovery Lambda — S3 AP + ONTAP API

**Lambda fuera de la VPC** (usando solo las API de servicios gestionados de AWS):
- Todas las demás funciones Lambda

> **Motivo**: Acceder a las API de servicios gestionados de AWS (Athena, Bedrock, Textract, etc.) desde una Lambda dentro de la VPC requiere un Interface VPC Endpoint (7,20 $/mes cada uno). Las funciones Lambda fuera de la VPC pueden acceder directamente a las API de AWS a través de Internet y funcionan sin coste adicional.

> **Nota**: Para los UC que utilizan la ONTAP REST API (UC1 Legal y cumplimiento), `EnableVpcEndpoints=true` es obligatorio, ya que las credenciales de ONTAP se recuperan a través del Secrets Manager VPC Endpoint.

## Extensión de aceleración de renderizado con FlexCache

### Resumen

En los flujos de trabajo de renderizado VFX, los render input assets (texturas, geometría, plates) están centrados en la lectura, lo que los convierte en un objetivo ideal para FlexCache. Al crear dinámicamente un FlexCache al inicio del trabajo y eliminarlo automáticamente una vez completado el renderizado, puede conciliar la optimización de costes y la mejora del rendimiento.

### Clasificación de datos de renderizado

| Tipo de dato | Patrón de acceso | FlexCache aplicable | Uso de S3 AP |
|-----------|---------------|:---:|:---:|
| Textures | Solo lectura | ✅ | ⚠️ Binario |
| Geometry/Plates | Solo lectura | ✅ | ⚠️ Binario |
| Scene Files | Solo lectura | ✅ | ❌ |
| Render Output (EXR/PNG) | Escritura | ❌ | ✅ QC/metadatos |
| Logs | Escritura → lectura | ❌ | ✅ Análisis |
| Cache (sim/fluid) | Lectura/escritura | ❌ | ❌ |

### Dynamic FlexCache Render Workflow

Para más detalles sobre un flujo de trabajo que crea y elimina un FlexCache por trabajo, consulte:

- **[Dynamic FlexCache Render/EDA Workflow](../dynamic-flexcache-render-workflow/README.md)** — Automatización con Step Functions
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md) — Granja de renderizado multirregión
- [Mapeo de sector / carga de trabajo](../docs/industry-workload-mapping.md) — Pattern E: Media/VFX Render Farm

### Beneficios esperados

| KPI | Sin FlexCache | Con FlexCache | Mejora |
|-----|--------------|---------------|--------|
| Espera para iniciar el renderizado | 10-20 min | 2-5 min | 75% |
| Tiempo por fotograma | 15 min | 10 min | 33% |
| Transferencia WAN por trabajo | 500GB | 50GB | 90% |
| Coste por fotograma | $0.50 | $0.35 | 30% |

---

## Enlaces a la documentación de AWS

| Servicio | Documentación |
|---------|------------|
| FSx for ONTAP | [FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon CloudFront | [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) |
| Amazon Bedrock | [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Alineación con el Well-Architected Framework

| Pilar | Alineación |
|----|------|
| Excelencia operativa | Rastreo con X-Ray, métricas EMF, supervisión del estado de los trabajos |
| Seguridad | IAM de privilegios mínimos, CloudFront OAC, cifrado KMS |
| Fiabilidad | Step Functions Retry/Catch, puerta de verificación de calidad |
| Eficiencia del rendimiento | Entrega por CDN de CloudFront, procesamiento paralelo de Lambda |
| Optimización de costes | Sin servidor, uso de la caché de CloudFront |
| Sostenibilidad | Ejecución bajo demanda, carga de origen reducida mediante CDN |

---

## Pruebas locales

### Comprobación de requisitos previos

```bash
# Confirmar los requisitos previos
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (para sam local)
aws sts get-caller-identity  # Credenciales de AWS
```

### sam local invoke

```bash
# Compilación
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta el código y la capa compartida automáticamente.
sam build

# Ejecutar la Discovery Lambda en local
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Con anulación de variables de entorno
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

Ejemplo de salida de una verificación de calidad de renderizado VFX:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 48,
    "prefix": "renders/shot-042/"
  },
  "quality_check": [
    {
      "key": "renders/shot-042/frame-0001.exr",
      "resolution": "4096x2160",
      "color_space": "ACEScg",
      "quality_score": 0.94,
      "issues": [],
      "cloudfront_url": "https://d1234.cloudfront.net/delivery/shot-042/frame-0001.exr"
    }
  ],
  "delivery": {
    "total_frames": 48,
    "passed_qc": 46,
    "failed_qc": 2,
    "cloudfront_distribution": "d1234.cloudfront.net"
  }
}
```

> **Nota**: Lo anterior es una muestra de salida; los valores reales varían según el entorno y los datos de entrada. Las cifras de referencia son una base de dimensionamiento (sizing reference), no un límite de servicio (service limit).

---

## Governance Note

> Este patrón proporciona orientación sobre arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Las organizaciones deben consultar a profesionales cualificados.

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la solución de problemas y los patrones de desencadenadores de los S3 Access Points for FSx for ONTAP, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
