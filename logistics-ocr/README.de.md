# UC12: Logistik / Lieferkette — Lieferschein OCR & Lagerbestandsbildanalyse

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

## Übersicht
Dies ist ein serverloser Workflow, der S3 Access Points für Amazon FSx for NetApp ONTAP nutzt, um die OCR-Textextraktion von Lieferscheinen, Objekterkennung und Zählung von Lagerbestandsbildern sowie die Erstellung von Berichten zur Optimierung von Lieferrouten zu automatisieren.
### Fälle, in denen dieses Muster geeignet ist
- Lieferscheinbilder und Lagerbestandsbilder werden in FSx ONTAP gespeichert.
- Die OCR (Absender, Empfänger, Tracking-Nummer, Artikel) für Lieferscheine mittels Textract soll automatisiert werden.
- Es ist eine Normalisierung der extrahierten Felder und die Generierung strukturierter Versanddaten mittels Bedrock erforderlich.
- Die Objekterkennung und Zählung (Paletten, Kisten, Regalauslastung) von Lagerbestandsbildern mittels Rekognition soll durchgeführt werden.
- Der automatische Generierungsbericht zur Routenoptimierung soll erstellt werden.
### Fälle, in denen dieses Muster nicht geeignet ist
- Ein Echtzeit-Lieferverfolgungssystem ist erforderlich
- Eine direkte Integration mit einem großen WMS (Warehouse Management System) ist erforderlich
- Eine vollständige Lieferrouten-Optimierungs-Engine (eigene Software ist angemessen)
- Umgebungen, in denen keine Netzwerkreichweite zur ONTAP REST API möglich ist
### Hauptfunktionen
- Automatische Erkennung von Lieferscheinbildern (.jpg,.jpeg,.png,.tiff, .pdf) und Lagerbestandsbildern über S3 AP
- OCR (Text- und Formularextraktion) für Lieferscheine mit Textract (Cross-Region)
- Manuelle Überprüfungsflag-Einstellung für Ergebnisse mit geringer Zuverlässigkeit
- Normalisierung extrahierter Felder und Generierung strukturierter Versanddatensätze mit Bedrock
- Objekterkennung und -zählung von Lagerbestandsbildern mit Rekognition
- Generierung von Berichten zur Optimierung von Lieferrouten mit Bedrock
## Architektur

```mermaid
graph LR
    subgraph "Step Functions ワークフロー"
        D[Discovery Lambda<br/>伝票/在庫画像検出]
        OCR[OCR Lambda<br/>Textract テキスト抽出]
        DS[Data Structuring Lambda<br/>Bedrock フィールド正規化]
        IA[Inventory Analysis Lambda<br/>Rekognition 物体検出]
        RPT[Report Lambda<br/>Bedrock 最適化レポート]
    end

    D -->|Manifest| OCR
    D -->|Manifest| IA
    OCR -->|OCR Results| DS
    DS -->|Structured Records| RPT
    IA -->|Inventory Counts| RPT

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    OCR -.->|Cross-Region| Textract[Amazon Textract<br/>us-east-1]
    DS -.->|InvokeModel| Bedrock[Amazon Bedrock]
    IA -.->|DetectLabels| Rekog[Amazon Rekognition]
    RPT -.->|InvokeModel| Bedrock
    RPT -.->|PutObject| S3OUT[S3 Output Bucket]
    RPT -.->|Publish| SNS[SNS Topic]
```

### Workflowschritt
1. **Erkennung**: Erkennung von Versandbelegbildern und Lagerbestandsbildern von S3 AP
2. **OCR**: Text- und Formularextraktion von Versandbelegen mit Textract (Cross-Region)
3. **Datenstrukturierung**: Normalisierung der extrahierten Felder in Bedrock und Generierung strukturierter Versanddatensätze
4. **Bestandsanalyse**: Objekterkennung und Zählung von Lagerbestandsbildern mit Rekognition
5. **Bericht**: Generierung eines optimierten Versandroutenberichts in Bedrock, S3-Ausgabe + SNS-Benachrichtigung
## Voraussetzungen
- AWS-Konto und geeignete IAM-Berechtigungen
- FSx for NetApp ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- S3 Access Point aktivierter Volume (zur Speicherung von Lieferscheinen und Bestandsbildern)
- VPC, private Subnetz
- Amazon Bedrock-Modellzugriff aktiviert (Claude / Nova)
- **Cross-Region**: Da Textract nicht in ap-northeast-1 verfügbar ist, ist ein Cross-Region-Aufruf nach us-east-1 erforderlich
## Bereitstellungsschritte

### 1. Überprüfung der cros-Region-Parameter
Da Textract nicht in der Tokio-Region verfügbar ist, konfigurieren Sie den Cross-Region-Aufruf mit dem `CrossRegionTarget`-Parameter.
### 2. CloudFormation-Bereitstellung

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template.yaml \
  --stack-name fsxn-logistics-ocr \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="rate(1 hour)" \
    NotificationEmail=<your-email@example.com> \
    CrossRegionTarget=us-east-1 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

## Liste der Konfigurationsparameter

| パラメータ | 説明 | デフォルト | 必須 |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx ONTAP S3 AP Alias（入力用） | — | ✅ |
| `S3AccessPointName` | S3 AP 名（ARN ベースの IAM 権限付与用。省略時は Alias ベースのみ） | `""` | ⚠️ 推奨 |
| `ScheduleExpression` | EventBridge Scheduler のスケジュール式 | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | プライベートサブネット ID リスト | — | ✅ |
| `NotificationEmail` | SNS 通知先メールアドレス | — | ✅ |
| `CrossRegionTarget` | Textract のターゲットリージョン | `us-east-1` | |
| `MapConcurrency` | Map ステートの並列実行数 | `10` | |
| `LambdaMemorySize` | Lambda メモリサイズ (MB) | `512` | |
| `LambdaTimeout` | Lambda タイムアウト (秒) | `300` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints の有効化 | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms の有効化 | `false` | |

## Bereinigung

```bash
aws s3 rm s3://fsxn-logistics-ocr-output-${AWS_ACCOUNT_ID} --recursive

aws cloudformation delete-stack \
  --stack-name fsxn-logistics-ocr \
  --region ap-northeast-1

aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-logistics-ocr \
  --region ap-northeast-1
```

## Unterstützte Regionen
UC12 verwendet die folgenden Dienste:
| サービス | リージョン制約 |
|---------|-------------|
| Amazon Textract | ap-northeast-1 非対応。`TEXTRACT_REGION` パラメータで対応リージョン（us-east-1 等）を指定 |
| Amazon Rekognition | ほぼ全リージョンで利用可能 |
| Amazon Bedrock | 対応リージョンを確認（[Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)） |
| AWS X-Ray | ほぼ全リージョンで利用可能 |
| CloudWatch EMF | ほぼ全リージョンで利用可能 |
> Rufen Sie die Textract API über den Cross-Region Client auf. Überprüfen Sie die Datenresidenzanforderungen. Weitere Informationen finden Sie in der [Regionskompatibilitätsmatrix](../docs/region-compatibility.md).
## Referenzlinks
- [FSx ONTAP S3 Access Points 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Amazon Textract Dokumentation](https://docs.aws.amazon.com/textract/latest/dg/what-is.html)
- [Amazon Rekognition Labelerkennung](https://docs.aws.amazon.com/rekognition/latest/dg/labels.html)
- [Amazon Bedrock API Referenz](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html)