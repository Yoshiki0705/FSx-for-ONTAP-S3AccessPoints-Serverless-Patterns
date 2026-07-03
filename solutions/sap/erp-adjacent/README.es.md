# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

Patrón serverless para procesar exportaciones de IDoc de SAP, archivos depositados por HULFT, archivos de zona de aterrizaje EDI y salidas de trabajos por lotes almacenados en FSx for ONTAP, con acceso a través de S3 Access Points.

## Use Cases

> **Scope note**: Este patrón está destinado a zonas de aterrizaje de archivos adyacentes a SAP/ERP, como exportaciones de IDoc, archivos EDI, transferencias HULFT, extracciones de auditoría y salidas por lotes. No pretende reemplazar los mecanismos de integración SAP certificados ni las interfaces ERP transaccionales. Para la integración de almacenamiento certificada por SAP, consulte la [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html).

- **Procesamiento de exportaciones de IDoc de SAP**: analiza y resume archivos planos IDoc (ORDERS, INVOIC, DESADV)
- **Aterrizaje de archivos HULFT**: procesa archivos transferidos por HULFT/DataSpider a FSx for ONTAP
- **Procesamiento de EDI entrante**: gestiona documentos EDI X12/EDIFACT en zonas de aterrizaje
- **Salida de trabajos por lotes**: analiza salidas de trabajos por lotes de mainframe, salidas JCL o informes programados
- **Extracción de datos de ERP**: procesa extracciones CSV/XML de SAP, Oracle EBS u otros sistemas ERP

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions Workflow           │ │
│  │  Scheduler   │────▶│                                          │ │
│  │              │     │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Processing│─▶│ Report │ │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda   │  │ Lambda │ │ │
│                       │  └────┬─────┘  └────┬─────┘  └───┬────┘ │ │
│                       └───────┼─────────────┼─────────────┼──────┘ │
│                               │             │             │        │
│                               ▼             ▼             ▼        │
│                       ┌──────────────┐ ┌─────────┐  ┌─────────┐   │
│                       │ FSx for ONTAP│ │ Amazon  │  │  Amazon │   │
│                       │ via S3 AP    │ │ Bedrock │  │   SNS   │   │
│                       │              │ │ (Nova)  │  │         │   │
│                       │ ListObjectsV2│ │Summarize│  │ Email   │   │
│                       │ GetObject    │ │Classify │  │ Notify  │   │
│                       └──────────────┘ └─────────┘  └─────────┘   │
│                                              │                     │
│                                              ▼                     │
│                                        ┌──────────┐                │
│                                        │ S3 Output│                │
│                                        │  Bucket  │                │
│                                        └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

1. **Discovery** — Enumera los archivos en FSx for ONTAP a través del S3 Access Point (`ListObjectsV2`), filtrados por prefijo
2. **Processing** — Para cada archivo: lee el contenido a través del S3 AP (`GetObject`) y lo envía a Amazon Bedrock para resumen/clasificación
3. **Report** — Genera un resumen de ejecución, lo escribe en S3 y envía una notificación de SNS

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | Alias de S3 AP para el volumen de FSx for ONTAP | (obligatorio) |
| `OntapSecretArn` | ARN de Secrets Manager para las credenciales de ONTAP | (obligatorio) |
| `ScheduleExpression` | Frecuencia de ejecución | `rate(1 hour)` |
| `OutputBucketName` | Bucket de S3 para los resultados | (obligatorio) |
| `NotificationEmail` | Correo electrónico para las alertas de SNS | (obligatorio) |
| `FilePrefix` | Prefijo de directorio a escanear | `idoc-export/` |
| `BedrockModelId` | Modelo de Bedrock para el resumen | `amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Máximo de archivos por ejecución | `100` |

## Deployment

```bash
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y las capas compartidas.
sam build
sam deploy --guided --stack-name fsxn-s3ap-sap-erp \
  --parameter-overrides \
    S3AccessPointAlias=my-sap-s3ap-alias \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:my-secret \
    OutputBucketName=my-sap-output-bucket \
    NotificationEmail=ops-team@example.com \
    FilePrefix="idoc-export/" \
    ScheduleExpression="cron(0 */2 * * ? *)"
```

> **Nota**: `template.yaml` se utiliza con la AWS SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con el comando `aws cloudformation deploy`, use `template-deploy.yaml` (que requiere empaquetar previamente los archivos zip de Lambda y subirlos a S3).

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

Edite `functions/processing/index.py` para personalizar el prompt de resumen según sus tipos de documentos.

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — Lista completa de patrones empresariales
- [Quick Start Guide](../docs/quick-start.md) — Recorrido del primer despliegue
- [Deployment Profiles](../docs/deployment-profiles.md) — Opciones de configuración de producción

---

## Estimación de costos (aproximación mensual)

> **Nota**: Lo siguiente es una aproximación para la región ap-northeast-1; los costos reales varían según el uso. Consulte los precios más recientes con la [AWS Pricing Calculator](https://calculator.aws/).

### Componentes serverless (pago por uso)

| Servicio | Precio unitario | Uso estimado | Aproximación mensual |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 funciones × 100 files/día | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/día | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/día | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/ejecución | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/día | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/mes | ~$0.76 |

### Costo fijo (FSx for ONTAP — se asume un entorno existente)

| Componente | Mensual |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (compartido con el entorno existente) |
| S3 Access Point | Sin cargo adicional (solo cargos de S3 API) |

### Aproximación total

| Configuración | Aproximación mensual |
|------|---------|
| Configuración mínima (una vez al día) | ~$5-15 |
| Configuración estándar (por hora) | ~$15-50 |
| Configuración a gran escala (alta frecuencia + alarmas) | ~$50-150 |

> **Governance Caveat**: Las estimaciones de costos son aproximaciones, no valores garantizados. Los cargos reales varían según los patrones de uso, el volumen de datos y la región.

---

## Pruebas locales

### Verificación de Prerequisites

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
# Requisito previo: se necesita AWS SAM CLI. sam build empaqueta automáticamente el código y las capas compartidas.
sam build

# Ejecutar la Discovery Lambda localmente
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

Ejemplo de salida del flujo de trabajo de procesamiento de archivos SAP/ERP:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 15,
    "prefix": "idoc-export/",
    "categories": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3}
  },
  "processing": [
    {
      "key": "idoc-export/ORDERS_20260523_001.idoc",
      "status": "completed",
      "category": "sap_idoc",
      "summary": "IDoc de pedido de cliente (ORDERS05). Socio comercial: Sample Corporation, número de pedido: PO-2026-001, importe: 2,500,000 JPY",
      "document_type": "ORDERS05",
      "key_fields": ["BELNR", "KUNNR", "NETWR", "WAERK"]
    }
  ],
  "report": {
    "total_files": 15,
    "succeeded": 14,
    "failed": 1,
    "success_rate_pct": 93.3,
    "category_breakdown": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3},
    "report_key": "reports/sap-erp-summary-1716480000.json"
  }
}
```

> **Nota**: Lo anterior es una salida de ejemplo; los valores reales varían según el entorno y los datos de entrada. Las cifras de benchmark son una sizing reference, no un service limit.

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Las organizaciones deben consultar a profesionales cualificados.

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de S3 Access Points for FSx for ONTAP, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
---

## Performance Considerations

- La capacidad de rendimiento de FSx for ONTAP se comparte entre NFS/SMB/S3AP
- La latencia a través del S3 Access Point genera una sobrecarga de decenas de milisegundos
- Al procesar grandes cantidades de archivos, controle el grado de paralelismo con MaxConcurrency del Step Functions Map state
- Aumentar el tamaño de memoria de Lambda también mejora el ancho de banda de red

> **Nota**: Las cifras de rendimiento de este patrón son una sizing reference, no un service limit. El rendimiento en entornos reales varía según la capacidad de rendimiento de FSx for ONTAP, la configuración de red y las cargas de trabajo concurrentes.
