# FSxN S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Colección de patrones de automatización serverless por sector, basados en los S3 Access Points de Amazon FSx for NetApp ONTAP.

## Descripción general

Este repositorio proporciona **5 patrones sectoriales** para el procesamiento serverless de datos empresariales almacenados en FSx for NetApp ONTAP a través de **S3 Access Points**.

Cada caso de uso es un template de CloudFormation independiente, con módulos compartidos (cliente ONTAP REST API, helper FSx, helper S3 AP) en `shared/`.

### Características principales

- **Arquitectura basada en sondeo**: EventBridge Scheduler + Step Functions (FSx ONTAP S3 AP no soporta `GetBucketNotificationConfiguration`)
- **Separación de módulos compartidos**: OntapClient / FsxHelper / S3ApHelper reutilizados en todos los casos de uso
- **CloudFormation nativo**: Cada caso de uso es un template de CloudFormation independiente
- **Seguridad primero**: Verificación TLS habilitada por defecto, IAM de mínimo privilegio, cifrado KMS
- **Optimización de costos**: Los recursos permanentes de alto costo (VPC Endpoints, etc.) son opcionales

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
    ...
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
| IaC | CloudFormation (YAML) |
| Cómputo | AWS Lambda |
| Orquestación | AWS Step Functions |
| Programación | Amazon EventBridge Scheduler |
| Almacenamiento | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| Seguridad | Secrets Manager, KMS, IAM mínimo privilegio |
| Pruebas | pytest + Hypothesis (PBT) |

## Licencia

MIT License. Consulte [LICENSE](LICENSE) para más detalles.
