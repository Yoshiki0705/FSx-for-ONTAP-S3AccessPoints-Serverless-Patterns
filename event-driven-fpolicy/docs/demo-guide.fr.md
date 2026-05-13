🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# FPolicy Événementiel — Guide de démonstration

## Aperçu

Cette démonstration montre comment les opérations de création de fichiers via NFS sont converties en événements en temps réel via le chemin ONTAP FPolicy → ECS Fargate → SQS → EventBridge.

**Durée estimée** : 10 à 15 minutes (3 à 5 minutes avec un environnement pré-déployé)

---

## Prérequis

| Élément | Exigence |
|---------|----------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 ou supérieur, FPolicy pris en charge |
| VPC | Sous-réseau privé dans le même VPC que FSxN |
| Montage NFS | Montage NFS du client vers le volume FSxN effectué |
| AWS CLI | v2 ou supérieur, permissions IAM appropriées |
| Docker | Pour la construction d'images de conteneurs |
| ECR | Dépôt créé |

---

## Step 1 : Déployer la pile

### 1.1 Construire l'image du conteneur

```bash
cd event-driven-fpolicy/

# Connexion ECR
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# Construction & Push
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 Déploiement CloudFormation

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

### 1.3 Vérifier l'IP de la tâche Fargate

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2 : Configuration ONTAP FPolicy

Connectez-vous au FSxN SVM via SSH et exécutez les commandes suivantes.

### 2.1 Créer l'External Engine

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Créer l'Event

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Créer la Policy

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Configurer le Scope

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Activer la Policy

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 Vérifier la connexion

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# Confirmer Status: connected
```

---

## Step 3 : Créer un fichier de test

Créez un fichier depuis le client monté en NFS.

```bash
# Montage NFS (si non effectué)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# Créer le fichier de test
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4 : Vérifier les messages SQS

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# Recevoir les messages (pour vérification)
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**Sortie attendue** :

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

## Step 5 : Vérifier les événements EventBridge

Vérifiez les événements dans CloudWatch Logs.

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# Obtenir le dernier flux de logs
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# Obtenir les événements de log
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**Sortie attendue** :

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

## Step 6 : Vérifier la mise à jour automatique de l'IP (Optionnel)

Forcez le redémarrage de la tâche Fargate et vérifiez la mise à jour automatique de l'IP.

```bash
# Forcer l'arrêt de la tâche (une nouvelle tâche démarrera automatiquement)
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# Attendre 30 secondes puis vérifier la nouvelle IP de la tâche
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# Vérifier que l'IP de l'engine ONTAP a été mise à jour
# Se connecter au FSxN SVM via SSH
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7 : Nettoyage

```bash
# 1. Désactiver ONTAP FPolicy
# Se connecter au FSxN SVM via SSH
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. Supprimer la pile CloudFormation
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. Supprimer le fichier de test
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## Dépannage

### Impossible de se connecter au FPolicy Server

1. Vérifier que TCP 9898 est autorisé dans le Security Group
2. Vérifier que la tâche Fargate est à l'état RUNNING
3. Vérifier que l'IP de l'ONTAP external-engine est correcte
4. Vérifier que le SQS VPC Endpoint existe

### Les messages n'arrivent pas dans SQS

1. Vérifier les logs du FPolicy Server : `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. Vérifier que le SQS VPC Endpoint existe
3. Vérifier que le rôle de tâche a la permission `sqs:SendMessage`

### Les événements n'arrivent pas dans EventBridge

1. Vérifier les logs du Bridge Lambda
2. Vérifier que le SQS Event Source Mapping est activé
3. Vérifier que le nom du bus personnalisé EventBridge est correct

### Événements non détectés avec NFSv4.2

NFSv4.2 n'est pas pris en charge pour le monitoring ONTAP FPolicy. Spécifiez explicitement `mount -o vers=4.1`.
