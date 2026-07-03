# UC24: Organizaciones sin fines de lucro — Clasificación de solicitudes de subvención / Correspondencia de resultados

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Un flujo de trabajo serverless que aprovecha los S3 Access Points de FSx for ONTAP para clasificar automáticamente las solicitudes de subvención, extraer la información de los solicitantes y los presupuestos, y hacer coincidir las métricas de resultados de los informes de actividad con los objetivos originales de la subvención.

## Success Metrics

### Outcome
Automatizar el procesamiento y análisis de documentos para mejorar la eficiencia operativa y el cumplimiento.

### Metrics
| Métrica | Objetivo (ejemplo) |
|-----------|------------|
| Precisión de la clasificación de solicitudes de subvención | ≥ 85% |
| Precisión de la medición del grado de logro de resultados | ≥ 80% |
| Tasa de extracción de datos de las solicitudes | ≥ 90% |
| Tiempo de generación de informes | < 5 min / lote |
| Coste / ejecución diaria | < $1.50 |
| Tasa de Human Review requerida | > 25% (resultados de clasificación de baja confianza) |

### Measurement Method
Historial de ejecución de Step Functions, resultados de extracción de los servicios de IA/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Los resultados de baja confianza requieren verificación manual
- Las alertas Critical son revisadas por expertos del dominio
- Los informes de resumen periódicos son revisados por la dirección

## Arquitectura

Consulte el [documento de arquitectura](docs/architecture.es.md) para ver los diagramas detallados de flujo de datos.

## Requisitos previos

> **Nota sobre S3 AP NetworkOrigin**: la función Lambda Discovery se implementa dentro de una VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a él a través de un S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos de FSx). Utilice un S3 AP con NetworkOrigin=VPC o configure el acceso a través de NAT Gateway. Consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Cuenta de AWS con los permisos IAM adecuados
- Sistema de archivos FSx for ONTAP (ONTAP 9.17.1P4D3 o posterior)
- Volumen con S3 Access Point habilitado
- VPC, subredes privadas
- Acceso a modelos de Amazon Bedrock habilitado (Claude / Nova)
- Amazon Textract — configuración de llamada Cross-Region (us-east-1)

## Implementación

```bash
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
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

> **Nota**: `template.yaml` está diseñado para usarse con SAM CLI (`sam build` + `sam deploy`).
> Para implementar directamente con `aws cloudformation deploy`, utilice `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar en paralelo con MapConcurrency=10 puede afectar a otras cargas de trabajo en el mismo volumen.
- Para el procesamiento por lotes de grandes volúmenes de archivos, compruebe la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency en consecuencia.
- Recomendación: comience con MapConcurrency=5 en producción, supervise las métricas de CloudWatch de FSx for ONTAP (ThroughputUtilization) y auméntelo gradualmente.

## Limpieza

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## Estimación de costes (mensual)

> **Nota**: estimaciones para ap-northeast-1. Los costes reales varían según el uso.

| Configuración | Estimación mensual |
|------|---------|
| Mínima (1 vez al día) | ~$8-20 |
| Estándar | ~$20-50 |

---

## Governance Note

> Este patrón proporciona orientación técnica de arquitectura. No constituye asesoramiento legal, de cumplimiento ni regulatorio. El tratamiento de la información personal y organizativa contenida en las solicitudes de subvención debe cumplir con las normas de cada organismo financiador y con las leyes de protección de datos personales aplicables.

> **Normativas relacionadas**: Ley japonesa de OSFL (Ley NPO), Ley de certificación de personas jurídicas de interés público

---

## S3AP Compatibility

Consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de FSx for ONTAP S3 AP.
