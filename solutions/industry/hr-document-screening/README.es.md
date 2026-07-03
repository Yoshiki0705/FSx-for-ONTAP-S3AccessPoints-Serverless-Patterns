# UC27: Recursos Humanos — Cribado de currículums / Modo estricto de PII

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Un flujo de trabajo serverless que aprovecha los FSx for ONTAP S3 Access Points para extraer de forma estructurada las habilidades y la experiencia de currículums e historiales profesionales, y realizar una puntuación en modo estricto de PII que excluye las características protegidas.

> **Importante: Aviso normativo**
> Este patrón es un **flujo de trabajo de clasificación y resumen de documentos**, no un sistema de decisión de contratación automatizada. Las decisiones finales de contratación siempre deben tomarlas profesionales de RR. HH. cualificados. Antes de su uso, debe verificar el cumplimiento de las leyes laborales, las normativas de privacidad (RGPD, APPI, CCPA, etc.) y los requisitos contra la discriminación de cada país y región. Las salidas no deben incluir clasificaciones basadas en características protegidas, y las explicaciones de evaluación deben basarse únicamente en las cualificaciones y la experiencia relacionadas con el puesto.

## Success Metrics

### Outcome
Automatizar el procesamiento y el análisis de documentos para lograr eficiencia operativa y un mayor cumplimiento.

### Metrics
| Métrica | Objetivo (ejemplo) |
|-----------|------------|
| Tasa de extracción de datos del currículum | ≥ 90 % |
| Equidad de la puntuación | Sin sesgo por características protegidas (edad, sexo, nacionalidad excluidos) |
| Cumplimiento de PII | 100 % (cero PII en los registros) |
| Tiempo de generación del informe | < 5 min / lote |
| Costo / ejecución diaria | < $2.00 |
| Tasa obligatoria de Human Review | > 30 % (todos los resultados de puntuación revisados por el equipo de RR. HH.) |

### Measurement Method
Historial de ejecución de Step Functions, resultados de extracción de los servicios de AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Los resultados de baja confianza requieren verificación manual
- Las alertas Critical las revisan expertos del dominio
- Los informes de resumen periódicos los revisa la dirección

### Output Safeguard Requirements
- El esquema de salida no debe incluir los campos age/gender/ethnicity/nationality
- Las explicaciones de evaluación deben basarse únicamente en las cualificaciones y la experiencia relacionadas con el puesto
- Las características protegidas detectadas deben eliminarse antes del almacenamiento
- Todos los resultados de recomendación deben requerir revisión humana

## Arquitectura

Consulte el [documento de arquitectura](docs/architecture.es.md) para ver los diagramas detallados de flujo de datos.

## Requisitos previos

> **Nota sobre el NetworkOrigin del S3 AP**: la función Lambda Discovery se despliega dentro de una VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a él a través de un S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos de FSx). Use un S3 AP con NetworkOrigin=VPC o configure el acceso a través de una NAT Gateway. Para más detalles, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Cuenta de AWS con los permisos de IAM adecuados
- Sistema de archivos FSx for ONTAP (ONTAP 9.17.1P4D3 o posterior)
- Volumen con S3 Access Point habilitado
- VPC, subredes privadas
- Acceso a modelos de Amazon Bedrock habilitado (Claude / Nova)
- Amazon Textract — configuración de invocación Cross-Region (us-east-1)

## Implementación

```bash
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta el código y la capa compartida automáticamente.
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
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

> **Nota**: `template.yaml` se utiliza con el SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con el comando `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (esto requiere empaquetar previamente los archivos zip de Lambda y subirlos a S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar el procesamiento en paralelo con MapConcurrency=10 puede afectar a otras cargas de trabajo en el mismo volumen.
- Para el procesamiento masivo de grandes cantidades de archivos, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency según sea necesario.
- Recomendado: en producción, comience con MapConcurrency=5 y auméntelo gradualmente mientras supervisa las métricas de CloudWatch de FSx for ONTAP (ThroughputUtilization).

## Limpieza

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## Estimación de costos (mensual)

> **Nota**: estimaciones aproximadas para la región ap-northeast-1. Los costos reales varían según el uso.

| Configuración | Estimación mensual |
|------|---------|
| Configuración mínima (1x al día) | ~$8-20 |
| Configuración estándar | ~$20-50 |

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni normativo. El uso de IA en el cribado de contrataciones debe cumplir con la Ley de Seguridad del Empleo y la Ley de Igualdad de Oportunidades de Empleo, y debe eliminar el sesgo basado en características protegidas (edad, sexo, nacionalidad, etc.). La puntuación de IA es solo información de referencia; la decisión final debe tomarla el personal de RR. HH.

> **Normativas relacionadas**: Ley de Seguridad del Empleo, Ley de Protección de la Información Personal (APPI), Ley de Normas Laborales

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de los FSx for ONTAP S3 Access Points, consulte las [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
