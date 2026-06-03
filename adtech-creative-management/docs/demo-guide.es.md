# Gestión de Activos Creativos — Guía de Demostración Catalogación y Verificación de Cumplimiento de Marca

🌐 **Language / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Resumen

Esta demostración presenta un pipeline automatizado de catalogación de activos creativos y verificación de cumplimiento de marca. El análisis visual de Rekognition combinado con la verificación de cumplimiento de Bedrock automatiza el control de calidad en la producción publicitaria.

**Mensaje principal**: La IA analiza automáticamente los activos creativos, verifica el cumplimiento de las directrices de marca y genera catálogos de activos.

**Tiempo estimado**: 3–5 minutos

---

## Despliegue y Validación Paso a Paso

### Step 1: Verificar prerrequisitos

```bash
aws --version          # AWS CLI v2 requerido
sam --version          # SAM CLI 1.x o superior
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: Clonar repositorio

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/adtech-creative-management
```

### Step 3: Construcción y despliegue SAM

```bash
sam build

sam deploy \
  --stack-name fsxn-adtech-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    BrandGuidelinesS3Key=brand-guidelines.json \
    ModerationConfidenceThreshold=80 \
    MaxTagsPerAsset=50 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 4: Ejecutar flujo de trabajo manualmente

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 5: Verificar resultados

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## Lista de Verificación

| Elemento | Método de Verificación | Resultado Esperado |
|----------|----------------------|-------------------|
| Detección de archivos de medios | Registro de ejecución Step Functions | El paso Discovery retorna el número de archivos |
| Extracción de etiquetas | `asset-catalog.json` | Hasta 50 etiquetas por activo |
| Inspección de moderación | `flagged-assets.json` | Contenido problemático señalado |
| Verificación de cumplimiento de marca | Campo compliance_status | Conforme / no conforme correctamente determinado |
| Alerta SNS | Verificar correo electrónico | Notificación solo cuando existen violaciones |

---

## Limpieza

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*Este documento sirve como guía de producción para videos de demostración de presentaciones técnicas.*
