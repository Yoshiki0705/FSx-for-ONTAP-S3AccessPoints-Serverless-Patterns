🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

# Ereignisgesteuerte FPolicy — Demo-Leitfaden

## Überblick

Diese Demo zeigt, wie Dateierstellungsoperationen über NFS in Echtzeit über den Pfad ONTAP FPolicy → ECS Fargate → SQS → EventBridge in Ereignisse umgewandelt werden.

**Geschätzte Zeit**: 10–15 Minuten (3–5 Minuten bei vorbereiteter Umgebung)

---

## Voraussetzungen

| Element | Anforderung |
|---------|-------------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 oder höher, FPolicy unterstützt |
| VPC | Privates Subnetz im gleichen VPC wie FSxN |
| NFS-Mount | NFS-Mount vom Client zum FSxN-Volume durchgeführt |
| AWS CLI | v2 oder höher, entsprechende IAM-Berechtigungen |
| Docker | Zum Erstellen von Container-Images |
| ECR | Repository erstellt |

---

## Step 1: Stack bereitstellen

### 1.1 Container-Image erstellen

```bash
cd event-driven-fpolicy/

# ECR-Anmeldung
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# Build & Push
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 CloudFormation-Bereitstellung

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

### 1.3 Fargate-Aufgaben-IP überprüfen

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy-Konfiguration

Verbinden Sie sich per SSH mit der FSxN SVM und führen Sie die folgenden Befehle aus.

### 2.1 External Engine erstellen

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Event erstellen

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Policy erstellen

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Scope konfigurieren

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Policy aktivieren

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 Verbindung überprüfen

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# Status: connected bestätigen
```

---

## Step 3: Testdatei erstellen

Erstellen Sie eine Datei vom NFS-gemounteten Client.

```bash
# NFS-Mount (falls noch nicht durchgeführt)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# Testdatei erstellen
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: SQS-Nachrichten überprüfen

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# Nachrichten empfangen (zur Überprüfung)
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**Erwartete Ausgabe**:

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

## Step 5: EventBridge-Ereignisse überprüfen

Überprüfen Sie die Ereignisse in CloudWatch Logs.

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# Neuesten Log-Stream abrufen
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# Log-Ereignisse abrufen
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**Erwartete Ausgabe**:

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

## Step 6: Automatische IP-Aktualisierung überprüfen (Optional)

Erzwingen Sie einen Neustart der Fargate-Aufgabe und überprüfen Sie die automatische IP-Aktualisierung.

```bash
# Aufgabe erzwungen stoppen (neue Aufgabe startet automatisch)
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# 30 Sekunden warten, dann neue Aufgaben-IP überprüfen
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# Überprüfen, dass die ONTAP-Engine-IP aktualisiert wurde
# Per SSH mit FSxN SVM verbinden
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: Aufräumen

```bash
# 1. ONTAP FPolicy deaktivieren
# Per SSH mit FSxN SVM verbinden
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. CloudFormation-Stack löschen
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. Testdatei löschen
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## Fehlerbehebung

### Verbindung zum FPolicy Server nicht möglich

1. Überprüfen, ob TCP 9898 in der Security Group erlaubt ist
2. Überprüfen, ob die Fargate-Aufgabe im RUNNING-Zustand ist
3. Überprüfen, ob die IP der ONTAP external-engine korrekt ist
4. Überprüfen, ob der SQS VPC Endpoint existiert

### Nachrichten kommen nicht in SQS an

1. FPolicy Server-Logs überprüfen: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. Überprüfen, ob der SQS VPC Endpoint existiert
3. Überprüfen, ob die Aufgabenrolle die Berechtigung `sqs:SendMessage` hat

### Ereignisse kommen nicht in EventBridge an

1. Bridge Lambda-Logs überprüfen
2. Überprüfen, ob das SQS Event Source Mapping aktiviert ist
3. Überprüfen, ob der Name des benutzerdefinierten EventBridge-Bus korrekt ist

### Ereignisse werden mit NFSv4.2 nicht erkannt

NFSv4.2 wird für ONTAP FPolicy Monitoring nicht unterstützt. Geben Sie explizit `mount -o vers=4.1` an.
