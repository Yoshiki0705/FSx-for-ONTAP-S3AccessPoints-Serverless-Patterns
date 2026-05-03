# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Colección de patrones de automatización serverless por sector, basados en los S3 Access Points de Amazon FSx for NetApp ONTAP.

> **Posicionamiento de este repositorio**: Esta es una «implementación de referencia para aprender decisiones de diseño». Algunos casos de uso han sido verificados E2E en un entorno AWS, mientras que otros han sido validados mediante despliegue de CloudFormation, Lambda Discovery compartido y pruebas de componentes principales. El objetivo es demostrar decisiones de diseño sobre optimización de costos, seguridad y manejo de errores a través de código concreto, con un camino desde PoC hasta producción.

## Artículo relacionado

Este repositorio es el compañero práctico del siguiente artículo:

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

El artículo explica el razonamiento arquitectónico y las compensaciones. Este repositorio proporciona patrones de implementación concretos y reutilizables.

## Descripción general

Este repositorio proporciona **5 patrones sectoriales** para el procesamiento serverless de datos empresariales almacenados en FSx for NetApp ONTAP a través de **S3 Access Points**.

> En adelante, FSx for ONTAP S3 Access Points se abrevia como **S3 AP**.

Cada caso de uso es un template de CloudFormation independiente, con módulos compartidos (cliente ONTAP REST API, helper FSx, helper S3 AP) en `shared/`.

### Características principales

- **Arquitectura basada en sondeo**: EventBridge Scheduler + Step Functions (S3 AP no soporta `GetBucketNotificationConfiguration`)
- **Separación de módulos compartidos**: OntapClient / FsxHelper / S3ApHelper reutilizados en todos los casos de uso
- **CloudFormation / SAM Transform**: Cada caso de uso es un template de CloudFormation independiente con SAM Transform
- **Seguridad primero**: Verificación TLS habilitada por defecto, IAM de mínimo privilegio, cifrado KMS
- **Optimización de costos**: Los recursos permanentes de alto costo (Interface VPC Endpoints, etc.) son opcionales

## Casos de uso

| # | Directorio | Sector | Patrón | Servicios AI/ML | Compatibilidad regional |
|---|------------|--------|--------|-----------------|------------------------|
| UC1 | `legal-compliance/` | Legal y cumplimiento | Auditoría de servidor de archivos y gobernanza de datos | Athena, Bedrock | Todas las regiones |
| UC2 | `financial-idp/` | Servicios financieros | Procesamiento de contratos/facturas (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: entre regiones |
| UC3 | `manufacturing-analytics/` | Manufactura | Registros de sensores IoT e inspección de calidad | Athena, Rekognition | Todas las regiones |
| UC4 | `media-vfx/` | Medios y entretenimiento | Pipeline de renderizado VFX | Rekognition, Deadline Cloud | Regiones de Deadline Cloud |
| UC5 | `healthcare-dicom/` | Salud | Clasificación de imágenes DICOM y anonimización | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: entre regiones |

> **Restricciones regionales**: Amazon Textract y Amazon Comprehend Medical no están disponibles en todas las regiones (ej.: ap-northeast-1). Se admiten llamadas entre regiones mediante los parámetros `TEXTRACT_REGION` y `COMPREHEND_MEDICAL_REGION`. Consulte la [Matriz de compatibilidad regional](docs/region-compatibility.md).

## Inicio rápido

### Requisitos previos

- AWS CLI v2
- Python 3.12+
- FSx for NetApp ONTAP con S3 Access Points habilitados
- Credenciales de ONTAP en AWS Secrets Manager

### Despliegue

> ⚠️ **Impacto en el entorno existente**
>
> - `EnableS3GatewayEndpoint=true` agrega un S3 Gateway Endpoint a su VPC. Establezca en `false` si ya existe uno.
> - `ScheduleExpression` activa ejecuciones periódicas de Step Functions. Desactive la programación después del despliegue si no se necesita de inmediato.
> - La eliminación del stack puede fallar si los buckets de S3 contienen objetos. Vacíe los buckets antes de eliminar.
> - La eliminación del VPC Endpoint tarda de 5 a 15 minutos. La liberación de ENI de Lambda puede retrasar la eliminación del Security Group.
>
> **Región**: Use `us-east-1` o `us-west-2` para disponibilidad completa de servicios AI/ML. Consulte [Compatibilidad regional](docs/region-compatibility.md).

```bash
# Establecer la región
export AWS_DEFAULT_REGION=us-east-1

# Empaquetar funciones Lambda
./scripts/deploy_uc.sh legal-compliance package

# Desplegar la pila de CloudFormation
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ParameterKey=PrivateRouteTableIds,ParameterValue=<your-route-table-ids> \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false
```

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [Guía de despliegue](docs/guides/deployment-guide.md) | Instrucciones de despliegue paso a paso |
| [Guía de operaciones](docs/guides/operations-guide.md) | Procedimientos de monitoreo y operaciones |
| [Guía de solución de problemas](docs/guides/troubleshooting-guide.md) | Problemas comunes y soluciones |
| [Análisis de costos](docs/cost-analysis.md) | Estructura de costos y optimización |
| [Compatibilidad regional](docs/region-compatibility.md) | Disponibilidad de servicios por región |
| [Patrones de extensión](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [Resultados de verificación](docs/verification-results.md) | Resultados de pruebas en entorno AWS |

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Lenguaje | Python 3.12 |
| IaC | CloudFormation (YAML) + SAM Transform |
| Cómputo | AWS Lambda |
| Orquestación | AWS Step Functions |
| Programación | Amazon EventBridge Scheduler |
| Almacenamiento | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| Seguridad | Secrets Manager, KMS, IAM mínimo privilegio |
| Pruebas | pytest + Hypothesis (PBT) |

## Licencia

MIT License. Consulte [LICENSE](LICENSE) para más detalles.
