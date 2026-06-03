# Análisis de Red de Telecomunicaciones — Guía de Demo Detección de Anomalías CDR/Logs de Red

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Resumen

Esta demo demuestra el pipeline automatizado de análisis de CDR (Registros Detallados de Llamadas) y logs de equipos de red. Las estadísticas de tráfico basadas en Athena y la detección de anomalías basada en Bedrock permiten la detección temprana de fallos de red y la automatización de informes de cumplimiento.

**Mensaje principal**: La IA analiza automáticamente CDR/logs de red, detecta anomalías en tiempo real y genera informes diarios.

**Duración estimada**: 3–5 minutos

---

## Despliegue y Validación Paso a Paso

### Paso 1: Verificación de prerrequisitos

```bash
aws --version          # v2.x requerido
sam --version          # 1.x o superior
python3 --version      # 3.9 o superior
aws sts get-caller-identity
```

### Paso 2: Clonar repositorio

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Paso 3: Preparar datos de ejemplo

Colocar datos de ejemplo en el volumen FSx ONTAP.

### Paso 4: Desplegar

```bash
sam build

sam deploy \
  --stack-name fsxn-telecom-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    CdrSuffixFilter=".csv,.asn1,.parquet" \
    AnomalyThresholdStdDev=3 \
    CapacityThresholdPercent=80 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Paso 5: Verificar despliegue

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Paso 6: Ejecutar workflow manualmente

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### Paso 7: Verificar resultados

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/ --region ap-northeast-1
```

---

## Lista de Verificación

| Elemento | Método de Verificación | Resultado Esperado |
|---------|----------------------|-------------------|
| Detección de archivos CDR | Log de ejecución Step Functions | El paso Discovery devuelve el conteo de archivos CDR |
| Estadísticas de tráfico Athena | Bucket S3 de salida | `cdr-stats.json` generado |
| Detección de anomalías | Revisión `anomalies.json` | Registros de anomalías marcados presentes |
| Informe diario | Bucket S3 | `network-health.json` existe |
| Alerta SNS | Verificación de email | Email de notificación recibido si hay anomalías críticas |

---

## Limpieza

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
