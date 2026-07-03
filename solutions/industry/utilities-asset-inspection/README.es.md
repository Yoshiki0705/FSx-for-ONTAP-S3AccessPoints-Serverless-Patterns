# UC25: Energía y servicios públicos — Inspección de imágenes con drones / Detección de anomalías SCADA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Resumen

Un flujo de trabajo serverless que aprovecha FSx for ONTAP S3 Access Points para detectar defectos de equipos a partir de imágenes de inspección con drones de instalaciones de transmisión, identificar anomalías en los registros de series temporales SCADA y analizar puntos calientes de imágenes térmicas FLIR.

## Success Metrics

### Outcome
Automatizar el procesamiento y análisis de documentos para mejorar la eficiencia operativa y el cumplimiento.

### Metrics
| Métrica | Objetivo (ejemplo) |
|-----------|------------|
| Tasa de detección de defectos | ≥ 85% |
| Tasa de falsos positivos de anomalías SCADA | < 10% |
| Precisión de detección de puntos calientes térmicos | ≥ 90% |
| Tiempo de generación de informes | < 5 min / lote |
| Costo / ejecución diaria | < $3.00 |
| Tasa de revisión humana requerida | > 30% (se revisan todas las detecciones de gravedad Critical) |

### Measurement Method
Historial de ejecución de Step Functions, resultados de extracción de servicios de AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Los resultados de baja confianza requieren verificación manual
- Las alertas Critical son revisadas por expertos del dominio
- Los informes de resumen periódicos son revisados por la dirección

## Arquitectura

Consulte el [documento de arquitectura](docs/architecture.es.md) para ver diagramas detallados de flujo de datos.

## Requisitos previos

> **Nota sobre S3 AP NetworkOrigin**: La función Lambda Discovery se despliega dentro de una VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a él a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos de FSx). Utilice un S3 AP con NetworkOrigin=VPC o configure el acceso a través de un NAT Gateway. Consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Cuenta de AWS con los permisos de IAM adecuados
- Sistema de archivos FSx for ONTAP (ONTAP 9.17.1P4D3 o posterior)
- S3 Access Point habilitado en el volumen
- VPC con subredes privadas
- Acceso a modelos de Amazon Bedrock habilitado (Claude / Nova)

## Despliegue

```bash
# Requisito previo: se necesita AWS SAM CLI. 'sam build' empaqueta el código y la capa compartida automáticamente.
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
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

> **Nota**: `template.yaml` está diseñado para usarse con la SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con `aws cloudformation deploy`, utilice en su lugar `template-deploy.yaml` (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar MapConcurrency=10 en paralelo puede afectar a otras cargas de trabajo en el mismo volumen.
- Para el procesamiento por lotes de grandes volúmenes de archivos, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency según corresponda.
- Recomendado: Comience con MapConcurrency=5 en producción, supervise las métricas de CloudWatch de FSx for ONTAP (ThroughputUtilization) y auméntelo gradualmente.

## Limpieza

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## Estimación de costos (mensual)

> **Nota**: Estimaciones para ap-northeast-1. Los costos reales varían según el uso.

| Configuración | Estimación mensual |
|------|---------|
| Mínima (1x diaria) | ~$8-20 |
| Estándar | ~$20-50 |

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Los datos SCADA son información de infraestructura crítica. La gestión del control de acceso y la retención de registros de auditoría deben cumplir con las regulaciones aplicables sobre actividades eléctricas y las directrices de protección de infraestructuras críticas.

> **Regulaciones relacionadas**: Ley de Negocios Eléctricos (電気事業法), Normas técnicas de instalaciones eléctricas (電気設備技術基準)

---

## S3AP Compatibility

Consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de FSx for ONTAP S3 Access Points.
