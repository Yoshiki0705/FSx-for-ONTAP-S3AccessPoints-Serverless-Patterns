# UC28: Química y materiales — Extracción de peligros de SDS / Validación GHS

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Diagrama de arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Un flujo de trabajo sin servidor que aprovecha FSx for ONTAP S3 Access Points para extraer clasificaciones de peligros y precauciones de manipulación de las fichas de datos de seguridad (SDS), validar la integridad de las secciones obligatorias del GHS y extraer datos experimentales a partir de imágenes de cuadernos de laboratorio.

## Success Metrics

### Outcome
Automatizar el procesamiento y el análisis de documentos para mejorar la eficiencia operativa y el cumplimiento.

### Metrics
| Métrica | Objetivo (ejemplo) |
|-----------|------------|
| Integridad de la validación de secciones GHS | 100 % (8 secciones obligatorias verificadas) |
| Tasa de detección de SDS caducadas | 100 % |
| Precisión de extracción de la clasificación de peligros | ≥ 90 % |
| Tiempo de generación del informe | < 5 min / lote |
| Costo / ejecución diaria | < $2.50 |
| Tasa de Human Review requerida | > 25 % (todas las alertas de prioridad Critical revisadas) |

### Measurement Method
Historial de ejecución de Step Functions, resultados de extracción de los servicios AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Los resultados de baja confianza requieren verificación manual
- Las alertas Critical son revisadas por expertos del dominio
- Los informes de resumen periódicos son revisados por la dirección

## Arquitectura

Consulte el [documento de arquitectura](docs/architecture.es.md) para ver diagramas de flujo de datos detallados.

## Requisitos previos

> **Nota sobre S3 AP NetworkOrigin**: La Lambda Discovery se implementa dentro de una VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos de FSx). Utilice un S3 AP con NetworkOrigin=VPC o configure el acceso a través de un NAT Gateway. Consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Cuenta de AWS con los permisos de IAM adecuados
- Sistema de archivos FSx for ONTAP (ONTAP 9.17.1P4D3 o posterior)
- S3 Access Point habilitado en el volumen
- VPC, subredes privadas
- Acceso a modelos de Amazon Bedrock habilitado (Claude / Nova)
- Amazon Textract — configuración de llamada Cross-Region (us-east-1)

## Despliegue

```bash
# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-chemical-sds \
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
> Para desplegar directamente con `aws cloudformation deploy`, utilice `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar MapConcurrency=10 en paralelo puede afectar a otras cargas de trabajo del mismo volumen.
- Para el procesamiento por lotes de grandes volúmenes de archivos, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency según corresponda.
- Recomendado: Comience con MapConcurrency=5 en producción, supervise las métricas de CloudWatch de FSx for ONTAP (ThroughputUtilization) y auméntela gradualmente.

## Limpieza

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds --region ap-northeast-1
```

## Estimación de costos (mensual)

> **Nota**: Estimación para la región ap-northeast-1. Los costos reales varían según el uso.

| Configuración | Estimación mensual |
|------|---------|
| Configuración mínima (1 vez al día) | ~$8-20 |
| Configuración estándar | ~$20-50 |

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. El manejo de la información sobre sustancias químicas contenida en las SDS debe cumplir con las leyes aplicables de gestión de sustancias químicas y de seguridad y salud en el trabajo. La determinación final de la clasificación GHS debe ser realizada por profesionales cualificados en seguridad química.

> **Reglamentaciones relacionadas**: Ley de promoción de la gestión de sustancias químicas (Ley PRTR), Ley de seguridad y salud en el trabajo, Ley de servicios contra incendios

---

## S3AP Compatibility

Consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de FSx for ONTAP S3 Access Points.
