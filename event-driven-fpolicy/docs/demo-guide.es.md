🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

# FPolicy basado en eventos — Guía de demostración

## Descripción general

Esta demostración muestra cómo una operación de creación de archivo a través de NFS se convierte en un evento en tiempo real mediante el pipeline ONTAP FPolicy → ECS Fargate → SQS → EventBridge.

**Tiempo estimado**: 10–15 minutos (3–5 minutos con entorno pre-desplegado)

---

## Prerrequisitos

| Elemento | Requisito |
|----------|-----------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 o posterior, compatible con FPolicy |
| VPC | Subredes privadas en la misma VPC que FSxN |
| Montaje NFS | Cliente con montaje NFS al volumen FSxN |
| AWS CLI | v2 o posterior con permisos IAM apropiados |

---

## Paso 1: Desplegar la pila

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-fpolicy-demo \
  --parameter-overrides \
    VpcId=vpc-xxxxxxxxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    FsxnSvmSecurityGroupId=sg-xxxxxxxxx \
    ContainerImage=<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
    FsxnMgmtIp=10.0.3.72 \
    FsxnSvmUuid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
    FsxnCredentialsSecret=fsxn-admin-credentials \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

---

## Paso 2: Configurar ONTAP FPolicy

Conectarse al SVM FSxN por SSH y ejecutar:

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename

vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false

vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

---

## Paso 3: Crear archivo de prueba

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Paso 4: Verificar mensaje SQS

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

---

## Paso 5: Verificar evento EventBridge

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"
aws logs tail $LOG_GROUP --since 5m
```

---

## Paso 6: Limpieza

```bash
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1
```

---

## Solución de problemas

- **No se puede conectar al FPolicy Server**: Verificar que Security Group permite TCP 9898, confirmar que la tarea Fargate está en estado RUNNING
- **Sin mensajes en SQS**: Verificar existencia del VPC Endpoint SQS, confirmar permisos del rol de tarea
- **Eventos NFSv4.2 no detectados**: Especificar explícitamente `mount -o vers=4.1`
