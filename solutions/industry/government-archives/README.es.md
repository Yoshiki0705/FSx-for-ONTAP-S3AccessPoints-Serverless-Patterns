# UC16: Organismos públicos — Archivo digital de documentos públicos y respuesta FOIA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español
📚 **Documentación**: [Arquitectura](docs/architecture.md) | [Script de demostración](docs/demo-guide.md) | [Solución de problemas](../docs/phase7-troubleshooting.md)

## Descripción general

Canalización automatizada para el archivo digital de documentos públicos
de organismos públicos y la respuesta a solicitudes de acceso a la información
(FOIA: Freedom of Information Act), basada en
FSx for ONTAP S3 Access Points.

## Caso de uso

Digitalizar, clasificar y ocultar (redacción) automáticamente el gran
volumen de documentos públicos (PDF, imágenes escaneadas, correos
electrónicos) que poseen los organismos públicos, para responder con rapidez
a las solicitudes de acceso a la información.

### Flujo de procesamiento

```
FSx for ONTAP (Almacenamiento de documentos públicos — ACL NTFS por departamento)
  → S3 Access Point
    → Flujo de trabajo de Step Functions
      → Discovery: Detección de nuevos documentos (PDF, TIFF, EML, MSG)
      → OCR: Digitalización de documentos con Textract (multirregión porque ap-northeast-1 no es compatible)
      → Classification: Clasificación de documentos con Comprehend (determinación del nivel de confidencialidad)
      → EntityExtraction: Detección de PII (nombre, dirección, SSN, número de teléfono)
      → Redaction: Ocultación automática de información confidencial (redacción)
      → IndexGeneration: Generación de índice de búsqueda de texto completo (OpenSearch, se puede desactivar)
      → ComplianceCheck: Verificación del período de conservación / calendario de eliminación (NARA GRS)
```

### Datos de destino

| Formato de datos | Descripción | Tamaño típico |
|-----------|------|-----------|
| PDF | Documentos públicos, informes, contratos | 100 KB – 50 MB |
| TIFF | Documentos escaneados | 1 – 100 MB |
| EML / MSG | Archivos de correo electrónico | 10 KB – 10 MB |
| DOCX / XLSX | Documentos de Office | 50 KB – 20 MB |

### Servicios de AWS

| Servicio | Propósito |
|---------|------|
| FSx for ONTAP | Almacenamiento persistente de documentos públicos (ACL NTFS por departamento) |
| S3 Access Points | Acceso a documentos desde serverless |
| Step Functions | Orquestación del flujo de trabajo |
| Lambda | Clasificación de documentos, detección de PII, ocultación |
| Amazon Textract ⚠️ | OCR de documentos (multirregión vía us-east-1) |
| Amazon Comprehend | Extracción de entidades, clasificación de documentos, detección de PII |
| Amazon Bedrock | Resumen de documentos, generación de borradores de respuesta FOIA |
| Amazon Macie | Detección automática de datos sensibles |
| DynamoDB | Metadatos de documentos, gestión del estado de procesamiento |
| OpenSearch Serverless | Índice de búsqueda de texto completo (opcional, desactivado por defecto) |
| SNS | Alertas de plazo FOIA |

### Idoneidad para el sector público

- **Cumplimiento NARA (National Archives and Records Administration)**: Cumple los requisitos de gestión de registros electrónicos
- **Respuesta FOIA**: Realiza un seguimiento automático del plazo de respuesta de 20 días hábiles
- **FedRAMP High**: Conforme en AWS GovCloud
- **Section 508**: Compatibilidad con accesibilidad (OCR + generación de texto alternativo)
- **Records Management**: Gestión automática de los períodos de conservación y calendarios de eliminación

### Flujo de respuesta FOIA

```
Recepción de la solicitud FOIA
  → Búsqueda de documentos de destino (OpenSearch)
  → Determinación del nivel de confidencialidad de los documentos correspondientes
  → Ocultación automática (PII, información de seguridad nacional)
  → Notificación a los revisores
  → Seguimiento del plazo de respuesta (20 días hábiles)
  → Generación del paquete de documentos publicables
```

## Pantallas verificadas (capturas de pantalla)

### 1. Almacenamiento de documentos públicos (vía S3 Access Point)

Tras recibir una solicitud de acceso a la información, los documentos de destino se almacenan bajo el prefijo `archives/YYYY/MM/`.

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     Contenido: Lista de documentos PDF bajo el prefijo archives/ en el S3 AP
     Máscara: ID de cuenta, ARN del S3 AP, nombres de documentos -->
![UC16: Confirmación del almacenamiento de documentos públicos](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. Visualización de documentos redactados

Texto almacenado bajo el prefijo `redacted/` tras el procesamiento, donde la PII
se ha sustituido por el marcador `[REDACTED]`. **La pantalla que el personal general revisa antes de la publicación.**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     Contenido: Vista previa del texto redacted en la consola de S3, marcadores [REDACTED] visibles
     Máscara: ID de cuenta, nombres de documentos redactados (solo nombres de ejemplo) -->
![UC16: Vista previa del documento redactado](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. Metadatos de redacción (sidecar JSON)

Datos sidecar para auditoría. La PII original no se almacena — solo hashes SHA-256.
Se registran los desplazamientos, los tipos de entidad (NAME / EMAIL / SSN, etc.) y la confianza.

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     Contenido: Vista formateada de redaction-metadata/*.json
     Máscara: ID de cuenta, nombres de documentos originales -->
![UC16: Metadatos de redacción JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. Recordatorio de plazo FOIA (notificación por correo SNS)

Correo de recordatorio que los responsables de FOIA reciben 3 días hábiles antes del plazo.
Cuando se supera el plazo, una notificación OVERDUE con severity=HIGH.

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     Contenido: Correo FOIA_DEADLINE_APPROACHING mostrado en un cliente de correo
     Máscara: correos de destinatario/remitente, request_id (solo ID de ejemplo) -->
![UC16: Correo de recordatorio de plazo FOIA](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. Calendario de conservación NARA GRS (DynamoDB Explorer)

Tabla `fsxn-uc16-demo-retention`. Para cada documento se registran el código NARA GRS
(GRS 2.1 / 2.2 / 1.1), los años de conservación (3 / 7 / 30 años) y la fecha de eliminación prevista.

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     Contenido: Lista de elementos de la tabla retention en DynamoDB Explorer
     Máscara: ID de cuenta, document_key (solo nombres de ejemplo) -->
![UC16: Tabla del calendario de conservación](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
Acelerar la respuesta a las solicitudes de acceso a la información mediante la automatización del archivo de documentos públicos y la respuesta FOIA (OCR, clasificación, redacción, gestión de plazos de conservación).

### Metrics
| Métrica | Valor objetivo (ejemplo) |
|-----------|------------|
| Documentos procesados / ejecución | > 500 documents |
| Tasa de éxito de extracción de texto OCR | > 95% |
| Precisión de detección de PII | > 95% |
| Tiempo de redacción / documento | < 30 segundos |
| Reducción del tiempo de respuesta FOIA | > 50% |
| Tasa obligatoria de Human Review | 100% (todos los resultados de redacción requieren confirmación humana) |

> **Por qué 100% de Human Review**: Como una redacción omitida afecta directamente a la divulgación de información y a la protección de datos personales, la confirmación humana de cada elemento es obligatoria.

### Measurement Method
Historial de ejecución de Step Functions, resultados de detección de PII de Comprehend, diff antes/después de la redacción, historial de conservación de DynamoDB, CloudWatch Metrics. Los resultados de la revisión se registran en DynamoDB para que, durante las auditorías, sea posible rastrear "quién confirmó/aprobó qué y cuándo".

### Sample Run Results (ejemplo medido)

**Entorno**: FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| Indicador | Before (manual) | After (automatización S3AP) |
|------|-------------|-------------------|
| Tiempo de respuesta FOIA | De días a semanas | 389 ms (10 docs, sequential) |
| Detección de documentos | Búsqueda manual | 32 ms (10 documents) |
| Lectura de archivos | Acceso individual | avg 36 ms / document |
| Calidad de redacción | Depende del responsable, con incoherencias | Detección de PII con Comprehend + redacción automática |
| Human Review | Ninguna o irregular | 100% (todos los elementos requieren confirmación humana) |
| Registro de auditoría | Registros personales | DynamoDB (who/when/what) + S3 Object Lock |
| Gestión de plazos de conservación | Manual | Seguimiento automático + alertas |

> **Nota**: El sample run de UC16 es una validación que utiliza documentos de muestra sintéticos o no sensibles y no representa documentos administrativos reales ni datos de producción. Este sample run valida únicamente la ruta de procesamiento. La calidad de la redacción, la exhaustividad de la Human Review y la evaluación del registro de auditoría deben realizarse por separado en un PoC específico del cliente.

## Despliegue

### Validación previa

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### Despliegue en un solo paso

```bash
bash scripts/deploy_phase7.sh government-archives
```

### Despliegue manual

```bash
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### Modos de OpenSearch

| Modo | Propósito | Coste mensual (estimación) |
|--------|------|-------------------|
| `none` | Validación / operación de bajo coste (por defecto) | $0 |
| `serverless` | Cargas variables, pago por uso | $350 – $700 |
| `managed` | Cargas fijas, bajo coste | $35 – $100 |

## Estructura de directorios

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # Textract multirregión
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # Período de conservación NARA GRS
│   └── foia_deadline_reminder/handler.py  # Seguimiento de 20 días hábiles
├── tests/                            # 52 pytest (incl. Hypothesis)
└── README.md
```


---

## Enlaces a la documentación de AWS

| Servicio | Documentación |
|---------|------------|
| FSx for ONTAP | [Guía del usuario](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Guía para desarrolladores](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [Guía para desarrolladores](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [Guía para desarrolladores](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [Guía del usuario](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [Guía para desarrolladores](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Alineación con el Well-Architected Framework

| Pilar | Alineación |
|----|------|
| Excelencia operativa | X-Ray, EMF, seguimiento de plazos FOIA, 52+ pruebas |
| Seguridad | Redacción de PII, sidecar de auditoría SHA-256, Macie, 100% Human Review |
| Fiabilidad | Step Functions Retry/Catch, OCR multirregión, pruebas de resiliencia |
| Eficiencia del rendimiento | Detección de PII en paralelo, índice OpenSearch, procesamiento por lotes |
| Optimización de costes | Serverless, OpenSearch Serverless, indexación condicional |
| Sostenibilidad | Cumplimiento NARA GRS, gestión de la conservación, calendario de eliminación automático |





---

## Estimación de costes (aproximación mensual)

> **Nota**: Las cifras siguientes son aproximaciones para la región ap-northeast-1; los costes reales varían según el uso. Consulte los precios más recientes en [AWS Pricing Calculator](https://calculator.aws/).

### Componentes serverless (pago por uso)

| Servicio | Precio unitario | Uso estimado | Aprox. mensual |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 funciones × 100 docs/día | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/día | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/día | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/ejecución | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/consulta | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/día | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mes | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### Coste fijo (FSx for ONTAP — supone un entorno existente)

| Componente | Mensual |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (comparte un entorno existente) |
| S3 Access Point | Sin cargo adicional (solo cargos de S3 API) |

### Estimación total

| Configuración | Aprox. mensual |
|------|---------|
| Mínima (una vez al día) | ~$5-15 |
| Estándar (por hora) | ~$15-50 |
| Gran escala (alta frecuencia + alarmas) | ~$50-150 |

> **Governance Caveat**: Las estimaciones de costes son aproximadas y no garantizadas. La facturación real varía según el patrón de uso, el volumen de datos y la región.

---

## Pruebas locales

### Comprobación de requisitos previos

```bash
# Comprobar los requisitos previos
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (para sam local)
aws sts get-caller-identity  # Credenciales de AWS
```

### sam local invoke

```bash
# Build
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y la capa compartida.
sam build

# Ejecución local de la Lambda Discovery
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

Para más detalles, consulte la [Guía de inicio rápido de pruebas locales](../docs/local-testing-quick-start.md).

---

## Ejemplo de salida (Output Sample)

Ejemplo de salida del procesamiento de archivo de documentos públicos / FOIA:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **Nota**: Lo anterior es una salida de ejemplo; los valores reales varían según el entorno y los datos de entrada. Las cifras de benchmark son una referencia de dimensionamiento, no un límite de servicio.

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Las organizaciones deben consultar a profesionales cualificados.

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la solución de problemas y los patrones de activación de S3 Access Points for FSx for ONTAP, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
