🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

# FPolicy Basada en Eventos — Guía de demostración

## Descripción general

Esta demostración muestra cómo las operaciones de creación de archivos a través de NFS se convierten en eventos en tiempo real mediante la ruta ONTAP FPolicy → ECS Fargate → SQS → EventBridge.

**Tiempo estimado**: 10–15 minutos (3–5 minutos con un entorno pre-desplegado)

---

## Requisitos previos

| Elemento | Requisito |
|----------|-----------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 o superior, FPolicy compatible |
| VPC | Subred privada en el mismo VPC que FSxN |
| Montaje NFS | Montaje NFS del cliente al volumen FSxN realizado |
| AWS CLI | v2 o superior, permisos IAM apropiados |
| Docker | Para construir imágenes de contenedor |
| ECR | Repositorio creado |

---

## Step 1: Desplegar la pila

### 1.1 Construir la imagen del contenedor

```bash
cd event-driven-fpolicy/

# Inicio de sesión en ECR
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# Construcción & Push
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 Despliegue de CloudFormation

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

### 1.3 Confirmar la IP de la tarea Fargate

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: Configuración de ONTAP FPolicy

Conéctese al FSxN SVM mediante SSH y ejecute los siguientes comandos.

### 2.1 Crear External Engine

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Crear Event

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Crear Policy

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Configurar Scope

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Habilitar Policy

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 Verificar conexión

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# Confirmar Status: connected
```

---

## Step 3: Crear archivo de prueba

Cree un archivo desde el cliente montado por NFS.

```bash
# Montaje NFS (si no se ha realizado)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# Crear archivo de prueba
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: Verificar mensajes SQS

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# Recibir mensajes (para verificación)
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**Salida esperada**:

```json
{
  "Messages": [
    {
      "Body": "{\"event_id\":\"...\",\"operation_type\":\"create\",\"file_path\":\"test-fpolicy-event.txt\",\"volume_name\":\"vol1\",\"svm_name\":\"FSxN_OnPre\",\"timestamp\":\"...\",\"file_size\":0}"
    }
  ]
}
```

---

## Step 5: Verificar eventos de EventBridge

Verifique los eventos en CloudWatch Logs.

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# Obtener el flujo de logs más reciente
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# Obtener eventos de log
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**Salida esperada**:

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "operation_type": "create",
    "file_path": "test-fpolicy-event.txt",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-01-15T10:30:00+00:00",
    "file_size": 0
  }
}
```

---

## Step 6: Verificar actualización automática de IP (Opcional)

Fuerce el reinicio de la tarea Fargate y verifique la actualización automática de IP.

```bash
# Forzar detención de la tarea (una nueva tarea se iniciará automáticamente)
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# Esperar 30 segundos y verificar la nueva IP de la tarea
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# Verificar que la IP del engine ONTAP se ha actualizado
# Conectar al FSxN SVM mediante SSH
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: Limpieza

```bash
# 1. Deshabilitar ONTAP FPolicy
# Conectar al FSxN SVM mediante SSH
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. Eliminar la pila de CloudFormation
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. Eliminar archivo de prueba
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## Solución de problemas

### No se puede conectar al FPolicy Server

1. Verificar que TCP 9898 está permitido en el Security Group
2. Verificar que la tarea Fargate está en estado RUNNING
3. Verificar que la IP del ONTAP external-engine es correcta
4. Verificar que el SQS VPC Endpoint existe

### Los mensajes no llegan a SQS

1. Verificar los logs del FPolicy Server: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. Verificar que el SQS VPC Endpoint existe
3. Verificar que el rol de tarea tiene el permiso `sqs:SendMessage`

### Los eventos no llegan a EventBridge

1. Verificar los logs del Bridge Lambda
2. Verificar que el SQS Event Source Mapping está habilitado
3. Verificar que el nombre del bus personalizado de EventBridge es correcto

### Eventos no detectados con NFSv4.2

NFSv4.2 no es compatible con el monitoreo ONTAP FPolicy. Especifique explícitamente `mount -o vers=4.1`.
