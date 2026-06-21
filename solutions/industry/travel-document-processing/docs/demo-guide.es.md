# Viajes y Hospitalidad — Guía de demostración

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Resumen

Esta demostración muestra un pipeline automatizado para procesar documentos de reserva e imágenes de inspección de instalaciones. Textract/Comprehend para extracción de datos de reserva, Rekognition/Bedrock para análisis del estado de instalaciones.

**Duración**: 3–5 minutos

---

## Despliegue paso a paso

### Step 1: Prerrequisitos

```bash
aws --version && sam --version && python3 --version
aws sts get-caller-identity
```

### Step 2: Despliegue

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/travel-document-processing
sam build && sam deploy \
  --stack-name fsxn-travel-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 3: Ejecución del flujo de trabajo

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

---

## Capturas de pantalla

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc20-demo/step-functions-graph-view.png)


## Limpieza

```bash
aws cloudformation delete-stack --stack-name fsxn-travel-demo --region ap-northeast-1
```
