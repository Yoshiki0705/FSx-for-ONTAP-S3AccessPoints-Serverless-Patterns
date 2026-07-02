# UC20: Viajes y Hospitalidad — Procesamiento de documentos de reserva / Análisis de imágenes de inspección de instalaciones

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Un flujo de trabajo serverless que aprovecha FSx for ONTAP S3 Access Points para extraer automáticamente datos estructurados de documentos de reserva de hoteles (PDF, imágenes escaneadas) y generar análisis de estado de instalaciones y recomendaciones de mantenimiento a partir de imágenes de inspección.

### Funcionalidades principales

- Detección automática de documentos de reserva e imágenes de inspección via S3 AP
- Extracción de datos estructurados con Textract + Comprehend (nombre del huésped, fechas, tipo de habitación, monto)
- Soporte multilingüe (detección de idioma → indicaciones Textract + selección automática de modelo Comprehend)
- Análisis del estado de instalaciones con Rekognition (detección de daños, puntuación de limpieza 0–100)
- Generación de recomendaciones de mantenimiento con Bedrock

## Success Metrics

| Métrica | Objetivo |
|---------|----------|
| Precisión de extracción de reservas | ≥ 90% |
| Tasa de detección del estado de instalaciones | ≥ 85% |
| Cobertura multilingüe | ≥ 5 idiomas |
| Tiempo de generación de informes | < 5 min / lote |
| Tasa de revisión humana | > 15% |

## Nota de gobernanza

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento o regulatorio.

## Despliegue

Despliegue con AWS SAM CLI (reemplace los parámetros de ejemplo por los de su entorno):

```bash
# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-travel-processing \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Nota**: `template.yaml` está diseñado para usarse con AWS SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar con MapConcurrency=10 en paralelo puede afectar otras cargas de trabajo en el mismo volumen.
- Para el procesamiento por lotes de gran volumen, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency en consecuencia.
- Recomendado: Comience con MapConcurrency=5 en producción, monitoree las métricas de CloudWatch (ThroughputUtilization) y aumente gradualmente.

> **Nota S3 AP NetworkOrigin**: La Lambda Discovery se despliega dentro de un VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos FSx). Use un S3 AP de tipo VPC-origin o configure el acceso mediante NAT Gateway. Ver [Notas de compatibilidad S3AP](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
