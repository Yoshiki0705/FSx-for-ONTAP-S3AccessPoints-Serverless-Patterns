🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# FPolicy événementiel — Guide de démonstration

## Présentation

Cette démonstration montre comment une opération de création de fichier via NFS est convertie en événement en temps réel via le pipeline ONTAP FPolicy → ECS Fargate → SQS → EventBridge.

**Durée estimée** : 10–15 minutes (3–5 minutes avec environnement pré-déployé)

---

## Prérequis

| Élément | Exigence |
|---------|----------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 ou ultérieur, compatible FPolicy |
| VPC | Sous-réseaux privés dans le même VPC que FSxN |
| Montage NFS | Client avec montage NFS vers le volume FSxN |
| AWS CLI | v2 ou ultérieur avec permissions IAM appropriées |

---

## Étape 1 : Déployer la pile

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

## Étape 2 : Configurer ONTAP FPolicy

Connectez-vous au SVM FSxN via SSH et exécutez :

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

## Étape 3 : Créer un fichier de test

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Étape 4 : Vérifier le message SQS

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

## Étape 5 : Vérifier l'événement EventBridge

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"
aws logs tail $LOG_GROUP --since 5m
```

---

## Étape 6 : Nettoyage

```bash
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1
```

---

## Dépannage

- **Impossible de se connecter au FPolicy Server** : Vérifier que le Security Group autorise TCP 9898, confirmer que la tâche Fargate est en état RUNNING
- **Pas de messages dans SQS** : Vérifier l'existence du VPC Endpoint SQS, confirmer les permissions du rôle de tâche
- **Événements NFSv4.2 non détectés** : Spécifier explicitement `mount -o vers=4.1`
