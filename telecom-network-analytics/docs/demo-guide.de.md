# Telekommunikations-Netzwerkanalyse — Demo-Leitfaden CDR/Netzwerk-Log Anomalieerkennung

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Zusammenfassung

Diese Demo demonstriert die automatisierte CDR- (Call Detail Records) und Netzwerkgeräte-Log-Analyse-Pipeline. Athena-basierte Verkehrsstatistiken und Bedrock-basierte Anomalieerkennung ermöglichen die Früherkennung von Netzwerkausfällen und automatisierte Compliance-Berichterstattung.

**Kernbotschaft**: KI analysiert automatisch CDR/Netzwerk-Logs, erkennt Anomalien in Echtzeit und generiert tägliche Berichte.

**Geschätzte Dauer**: 3–5 Minuten

---

## Schritt-für-Schritt Bereitstellung und Validierung

### Schritt 1: Voraussetzungen prüfen

```bash
aws --version          # v2.x erforderlich
sam --version          # 1.x oder höher
python3 --version      # 3.9 oder höher
aws sts get-caller-identity
```

### Schritt 2: Repository klonen

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Schritt 3: Beispieldaten vorbereiten

Beispieldaten auf dem FSx ONTAP Volume platzieren.

### Schritt 4: Bereitstellen

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

### Schritt 5: Bereitstellung überprüfen

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Schritt 6: Workflow manuell ausführen

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

### Schritt 7: Ergebnisse überprüfen

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

## Validierungs-Checkliste

| Prüfpunkt | Überprüfungsmethode | Erwartetes Ergebnis |
|-----------|--------------------|--------------------|
| CDR-Dateierkennung | Step Functions Ausführungsprotokoll | Discovery-Schritt gibt CDR-Dateianzahl zurück |
| Athena-Verkehrsstatistik | S3-Ausgabe-Bucket | `cdr-stats.json` generiert |
| Anomalieerkennung | `anomalies.json` Prüfung | Markierte Anomalie-Datensätze vorhanden |
| Täglicher Bericht | S3-Bucket | `network-health.json` existiert |
| SNS-Alarm | E-Mail-Prüfung | Benachrichtigungs-E-Mail bei kritischen Anomalien |

---

---

## Screenshots

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## Bereinigung

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
