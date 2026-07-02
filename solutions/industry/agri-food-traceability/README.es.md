# UC21: Agricultura y Alimentación — Análisis de imágenes aéreas / Gestión de documentos de trazabilidad

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Flujo de trabajo serverless que aprovecha FSx for ONTAP S3 Access Points para analizar imágenes aéreas de tierras agrícolas y automatizar la extracción de datos estructurados de documentos de trazabilidad.

## Success Metrics

| Métrica | Objetivo |
|---------|----------|
| Precisión detección anomalías cultivos | ≥ 70% |
| Tasa de clasificación trazabilidad | ≥ 80% |
| Tasa de verificación geolocalización | ≥ 90% |

## Nota de gobernanza

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal o regulatorio.

## Despliegue

Despliegue con AWS SAM CLI (reemplace los parámetros de ejemplo por los de su entorno):

```bash
# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-agri-traceability \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
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

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
