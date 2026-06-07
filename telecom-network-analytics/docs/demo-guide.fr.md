# Analyse Réseau Télécom — Guide de Démo Détection d'Anomalies CDR/Journaux Réseau

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Résumé

Cette démo présente le pipeline automatisé d'analyse des CDR (enregistrements détaillés d'appels) et des journaux d'équipements réseau. Les statistiques de trafic Athena et la détection d'anomalies Bedrock permettent la détection précoce des pannes réseau et l'automatisation des rapports de conformité.

**Message principal** : L'IA analyse automatiquement les CDR/journaux réseau, détecte les anomalies en temps réel et génère des rapports quotidiens.

**Durée estimée** : 3 à 5 minutes

---

## Déploiement et Validation Étape par Étape

### Étape 1 : Vérification des prérequis

```bash
aws --version          # v2.x requis
sam --version          # 1.x ou plus
python3 --version      # 3.9 ou plus
aws sts get-caller-identity
```

### Étape 2 : Cloner le dépôt

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Étape 3 : Préparer les données d'exemple

Placer les données d'exemple sur le volume FSx ONTAP.

### Étape 4 : Déployer

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

### Étape 5 : Vérifier le déploiement

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Étape 6 : Exécution manuelle du workflow

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

### Étape 7 : Vérifier les résultats

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

## Liste de vérification

| Élément | Méthode de vérification | Résultat attendu |
|---------|------------------------|-----------------|
| Détection fichiers CDR | Journal d'exécution Step Functions | L'étape Discovery retourne le nombre de fichiers CDR |
| Statistiques trafic Athena | Bucket S3 de sortie | `cdr-stats.json` généré |
| Détection d'anomalies | Examen `anomalies.json` | Enregistrements d'anomalies marqués présents |
| Rapport quotidien | Bucket S3 | `network-health.json` existe |
| Alerte SNS | Vérification email | Email de notification reçu si anomalies critiques |

---

---

## Captures d'écran

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## Nettoyage

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
