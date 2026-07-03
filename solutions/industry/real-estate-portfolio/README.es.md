# UC26: Bienes raíces — Análisis de imágenes de propiedades / Extracción de contratos

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Un flujo de trabajo serverless que aprovecha los S3 Access Points de FSx for ONTAP para extraer características de imágenes de propiedades, generar automáticamente descripciones de anuncios, extraer condiciones de contratos de arrendamiento y detectar PII para la protección de la privacidad.

## Success Metrics

### Outcome
Automatizar el procesamiento y análisis de documentos para mejorar la eficiencia operativa y el cumplimiento.

### Metrics
| Métrica | Objetivo (ejemplo) |
|---------|-------------------|
| Precisión de extracción de características de propiedad | ≥ 85% |
| Tasa de detección de PII | ≥ 95% |
| Precisión de extracción de condiciones del contrato | ≥ 90% |
| Tiempo de generación de informes | < 5 min / lote |
| Costo / ejecución diaria | < $2.50 |
| Tasa de revisión humana requerida | > 20% (todas las imágenes con PII detectadas se revisan) |

### Measurement Method
Historial de ejecución de Step Functions, resultados de extracción de los servicios AI/ML, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Los resultados de baja confianza requieren verificación manual
- Las alertas Critical son revisadas por expertos del dominio
- Los informes de resumen periódicos son revisados por la dirección

## Arquitectura

Consulte el [documento de arquitectura](docs/architecture.es.md) para ver los diagramas detallados de flujo de datos.

## Requisitos previos

> **Nota sobre S3 AP NetworkOrigin**: La Lambda Discovery se implementa dentro de una VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos de FSx for ONTAP). Utilice un S3 AP con NetworkOrigin=VPC o configure el acceso a través de NAT Gateway. Para más detalles, consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- Cuenta de AWS con los permisos de IAM adecuados
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
  --stack-name fsxn-real-estate \
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
> Para implementar directamente con el comando `aws cloudformation deploy`, utilice `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar en paralelo con MapConcurrency=10 puede afectar a otras cargas de trabajo del mismo volumen.
- Para el procesamiento por lotes de grandes volúmenes de archivos, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency según sea necesario.
- Recomendado: comience con MapConcurrency=5 en producción, supervise las métricas de CloudWatch (ThroughputUtilization) de FSx for ONTAP y aumente gradualmente.

## Limpieza

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## Estimación de costos (mensual)

> **Nota**: Estimaciones para la región ap-northeast-1. Los costos reales varían según el uso.

| Configuración | Estimación mensual |
|---------------|-------------------|
| Mínima (1x diario) | ~$8-20 |
| Estándar | ~$20-50 |

---

## Governance Note

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. La información de inquilinos incluida en los contratos de arrendamiento debe gestionarse de acuerdo con las leyes de protección de datos personales aplicables. El tratamiento de PII que aparezca en las imágenes de propiedades también debe tener en cuenta la normativa sobre transacciones inmobiliarias.

> **Regulaciones relacionadas**: 宅地建物取引業法 (Ley de intermediación inmobiliaria), 個人情報保護法 (Ley de protección de datos personales)

---

## S3AP Compatibility

Para conocer las restricciones de compatibilidad, la resolución de problemas y los patrones de activación de los S3 Access Points for FSx for ONTAP, consulte [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
