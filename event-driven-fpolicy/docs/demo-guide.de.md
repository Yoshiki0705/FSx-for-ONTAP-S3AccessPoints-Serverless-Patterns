🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

# Ereignisgesteuerte FPolicy — Demo-Leitfaden

## Überblick

Diese Demo zeigt, wie eine Dateierstellungsoperation über NFS in Echtzeit über die Pipeline ONTAP FPolicy → ECS Fargate → SQS → EventBridge in ein Ereignis umgewandelt wird.

**Geschätzte Dauer**: 10–15 Minuten (3–5 Minuten mit vorbereiteter Umgebung)

---

## Voraussetzungen

| Element | Anforderung |
|---------|-------------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 oder höher, FPolicy-fähig |
| VPC | Private Subnetze in derselben VPC wie FSxN |
| NFS-Mount | Client mit NFS-Mount zum FSxN-Volume |
| AWS CLI | v2 oder höher mit entsprechenden IAM-Berechtigungen |

---

## Schritt 1: Stack bereitstellen

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

## Schritt 2: ONTAP FPolicy konfigurieren

Per SSH mit FSxN SVM verbinden und ausführen:

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

## Schritt 3: Testdatei erstellen

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Schritt 4: SQS-Nachricht überprüfen

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

## Schritt 5: EventBridge-Ereignis überprüfen

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"
aws logs tail $LOG_GROUP --since 5m
```

---

## Schritt 6: Aufräumen

```bash
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1
```

---

## Fehlerbehebung

- **Keine Verbindung zum FPolicy Server**: Security Group TCP 9898 prüfen, Fargate-Task RUNNING-Status bestätigen
- **Keine Nachrichten in SQS**: SQS VPC Endpoint prüfen, Task-Rollenberechtigungen bestätigen
- **NFSv4.2-Ereignisse nicht erkannt**: Explizit `mount -o vers=4.1` angeben
