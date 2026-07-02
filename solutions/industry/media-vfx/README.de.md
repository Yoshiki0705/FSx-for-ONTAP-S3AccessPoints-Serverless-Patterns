# UC4: Medien – VFX-Rendering-Pipeline

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architekturdiagramm](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Übersicht

Ein serverloser Workflow, der die S3 Access Points von FSx for ONTAP nutzt, um das Einreichen von VFX-Rendering-Jobs, Qualitätsprüfungen und das Zurückschreiben genehmigter Ausgaben zu automatisieren.

### Wann dieses Muster geeignet ist

- Sie nutzen FSx for ONTAP als Rendering-Speicher für die VFX-/Animationsproduktion
- Sie möchten Qualitätsprüfungen nach Abschluss des Renderings automatisieren und den Aufwand für manuelle Überprüfungen reduzieren
- Sie möchten Assets, die die Qualitätsprüfung bestanden haben, automatisch auf den Dateiserver zurückschreiben (S3 AP PutObject)
- Sie möchten eine Pipeline aufbauen, die Deadline Cloud mit vorhandenem NAS-Speicher integriert

### Wann dieses Muster nicht geeignet ist

- Sie benötigen ein sofortiges Anstoßen von Rendering-Jobs (Trigger beim Speichern von Dateien)
- Sie verwenden eine andere Render-Farm als Deadline Cloud (z. B. Thinkbox Deadline On-Premises)
- Die Rendering-Ausgabe überschreitet 5 GB (die Obergrenze von S3 AP PutObject)
- Für die Qualitätsprüfung ist ein proprietäres Modell zur Bildqualitätsbewertung erforderlich (die Labelerkennung von Rekognition reicht nicht aus)

### Hauptfunktionen

- Automatische Erkennung der Ziel-Rendering-Assets über S3 AP
- Automatisches Einreichen von Rendering-Jobs an AWS Deadline Cloud
- Qualitätsbewertung durch Amazon Rekognition (Auflösung, Artefakte, Farbkonsistenz)
- Bei Bestehen PutObject an FSx for ONTAP über S3 AP; bei Nichtbestehen SNS-Benachrichtigung

## Success Metrics

### Outcome
Verkürzung der Asset-Suchzeit durch automatische Klassifizierung und Metadaten-Kennzeichnung von VFX-Assets.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Verarbeitete Assets pro Ausführung | > 200 files |
| Erfolgsrate der Metadaten-Kennzeichnung | > 95% |
| Verkürzung der Asset-Suchzeit | > 60% |
| Verarbeitungszeit pro Datei | < 60 Sek. |
| Kosten pro Ausführung | < $10 |
| Anteil für Human Review | < 10% |

### Measurement Method
Step Functions-Ausführungsverlauf, Rekognition label count, S3-Ausgabemetadaten.

## Architektur

```mermaid
graph LR
    subgraph "Step Functions-Workflow"
        D[Discovery Lambda<br/>Asset-Erkennung]
        JS[Job Submit Lambda<br/>Deadline Cloud Job-Einreichung]
        QC[Quality Check Lambda<br/>Rekognition-Qualitätsbewertung]
    end

    D -->|Manifest| JS
    JS -->|Job Result| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    JS -.->|GetObject| S3AP
    JS -.->|CreateJob| DC[AWS Deadline Cloud]
    QC -.->|DetectLabels| Rekognition[Amazon Rekognition]
    QC -.->|PutObject (bei Bestehen)| S3AP
    QC -.->|Publish (bei Nichtbestehen)| SNS[SNS Topic]
```

### Workflow-Schritte

1. **Discovery**: Ziel-Rendering-Assets aus dem S3 AP erkennen und ein Manifest generieren
2. **Job Submit**: Assets über den S3 AP abrufen und Rendering-Jobs an AWS Deadline Cloud einreichen
3. **Quality Check**: Die Qualität der Rendering-Ergebnisse mit Rekognition bewerten. Bei Bestehen PutObject an den S3 AP; bei Nichtbestehen per SNS-Benachrichtigung zum erneuten Rendern kennzeichnen

## Voraussetzungen

- Ein AWS-Konto und geeignete IAM-Berechtigungen
- Ein FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- Ein Volume mit aktivierten S3 Access Points
- In Secrets Manager registrierte ONTAP REST API-Anmeldeinformationen
- Ein VPC und private Subnetze
- Eine bereits konfigurierte AWS Deadline Cloud Farm / Queue
- Eine Region, in der Amazon Rekognition verfügbar ist

## Bereitstellungsschritte

### 1. Parameter vorbereiten

Bestätigen Sie vor der Bereitstellung die folgenden Werte:

- FSx for ONTAP S3 Access Point Alias
- ONTAP-Verwaltungs-IP-Adresse
- Secrets Manager-Secret-Name
- AWS Deadline Cloud Farm ID / Queue ID
- VPC ID, private Subnetz-ID

### 2. SAM-Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI ist erforderlich. sam build verpackt den Code und den gemeinsamen Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-media-vfx \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    S3AccessPointOutputAlias=<your-output-volume-ext-s3alias> \
    OntapSecretName=<your-ontap-secret-name> \
    OntapManagementIp=<your-ontap-management-ip> \
    ScheduleExpression="rate(1 hour)" \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    DeadlineFarmId=<your-deadline-farm-id> \
    DeadlineQueueId=<your-deadline-queue-id> \
    QualityThreshold=80.0 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Hinweis**: `template.yaml` wird mit der SAM CLI (`sam build` + `sam deploy`) verwendet.
> Um direkt mit dem Befehl `aws cloudformation deploy` bereitzustellen, verwenden Sie stattdessen `template-deploy.yaml` (dies erfordert das vorherige Verpacken der Lambda-Zip-Dateien und das Hochladen nach S3).

> **Hinweis**: Ersetzen Sie die Platzhalter `<...>` durch die tatsächlichen Werte Ihrer Umgebung.

### 3. SNS-Abonnement bestätigen

Nach der Bereitstellung wird eine SNS-Abonnement-Bestätigungs-E-Mail an die angegebene E-Mail-Adresse gesendet.

> **Hinweis**: Wenn Sie `S3AccessPointName` weglassen, wird die IAM-Richtlinie nur Alias-basiert, was zu einem `AccessDenied`-Fehler führen kann. In einer Produktionsumgebung wird die Angabe empfohlen. Weitere Details finden Sie im [Leitfaden zur Fehlerbehebung](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー).

## Liste der Konfigurationsparameter

| Parameter | Beschreibung | Standard | Erforderlich |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx for ONTAP S3 AP Alias (für Eingabe) | — | ✅ |
| `S3AccessPointName` | S3 AP-Name (für ARN-basierte IAM-Berechtigungsvergabe; bei Weglassen nur Alias-basiert) | `""` | ⚠️ Empfohlen |
| `S3AccessPointOutputAlias` | FSx for ONTAP S3 AP Alias (für Ausgabe) | — | ✅ |
| `OntapSecretName` | Secrets Manager-Secret-Name für ONTAP-Anmeldeinformationen | — | ✅ |
| `OntapManagementIp` | ONTAP-Cluster-Verwaltungs-IP-Adresse | — | ✅ |
| `ScheduleExpression` | Zeitplanausdruck von EventBridge Scheduler | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | Liste der privaten Subnetz-IDs | — | ✅ |
| `NotificationEmail` | SNS-Benachrichtigungs-E-Mail-Adresse | — | ✅ |
| `DeadlineFarmId` | AWS Deadline Cloud Farm ID | — | ✅ |
| `DeadlineQueueId` | AWS Deadline Cloud Queue ID | — | ✅ |
| `QualityThreshold` | Rekognition-Qualitätsbewertungsschwelle (0.0–100.0) | `80.0` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints aktivieren | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms aktivieren | `false` | |

## Kostenstruktur

### Anfragebasiert (nutzungsabhängig)

| Service | Abrechnungseinheit | Schätzung (100 Assets/Monat) |
|---------|---------|----------------------|
| Lambda | Anzahl der Anfragen + Ausführungszeit | ~$0.01 |
| Step Functions | Anzahl der Zustandsübergänge | Innerhalb des kostenlosen Kontingents |
| S3 API | Anzahl der Anfragen | ~$0.01 |
| Rekognition | Anzahl der Bilder | ~$0.10 |
| Deadline Cloud | Rendering-Zeit | Separat geschätzt※ |

※ Die Kosten von AWS Deadline Cloud hängen vom Umfang und der Dauer der Rendering-Jobs ab.

### Dauerbetrieb (optional)

| Service | Parameter | Monatlich |
|---------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints=true` | ~$28.80 |
| CloudWatch Alarms | `EnableCloudWatchAlarms=true` | ~$0.20 |

> In einer Demo-/PoC-Umgebung können Sie mit ausschließlich variablen Kosten ab **~$0.12/Monat** (ohne Deadline Cloud) starten.

## Bereinigung

```bash
# CloudFormation-Stack löschen
aws cloudformation delete-stack \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1

# Auf Abschluss der Löschung warten
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1
```

> **Hinweis**: Das Löschen des Stacks kann fehlschlagen, wenn im S3-Bucket noch Objekte vorhanden sind. Leeren Sie den Bucket im Voraus.

## Supported Regions

UC4 verwendet die folgenden Services:

| Service | Regionale Einschränkung |
|---------|-------------|
| Amazon Rekognition | In fast allen Regionen verfügbar |
| AWS Deadline Cloud | Eingeschränkte Regionsverfügbarkeit ([Von Deadline Cloud unterstützte Regionen](https://docs.aws.amazon.com/general/latest/gr/deadline-cloud.html)) |
| AWS X-Ray | In fast allen Regionen verfügbar |
| CloudWatch EMF | In fast allen Regionen verfügbar |

> Weitere Details finden Sie in der [Matrix zur Regionskompatibilität](../docs/region-compatibility.md).

## Referenzlinks

### Offizielle AWS-Dokumentation

- [Übersicht über FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Streaming mit CloudFront (offizielles Tutorial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html)
- [Serverlose Verarbeitung mit Lambda (offizielles Tutorial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Deadline Cloud API-Referenz](https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html)
- [Rekognition DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html)

### AWS-Blogbeiträge

- [S3 AP-Ankündigungsblog](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
- [Drei serverlose Architekturmuster](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### GitHub-Beispiele

- [aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing](https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing) — Rekognition-Verarbeitung im großen Maßstab
- [aws-samples/dotnet-serverless-imagerecognition](https://github.com/aws-samples/dotnet-serverless-imagerecognition) — Step Functions + Rekognition
- [aws-samples/serverless-patterns](https://github.com/aws-samples/serverless-patterns) — Sammlung serverloser Muster

### Projektinterne Leitfäden

- [FlexClone Serverless Patterns (Japanisch)](../docs/guides/flexclone-serverless-patterns.md) — Pipeline zur sequenziellen Frame-Verarbeitung mit FlexClone + Step Functions + S3AP, Multiprotokoll-Mount, branchenspezifische Anwendungsfälle
- [FlexClone Serverless Patterns (English)](../docs/guides/flexclone-serverless-patterns-en.md) — FlexClone + Step Functions + S3AP sequential frame processing pipeline

## Validierte Umgebung

| Element | Wert |
|------|-----|
| AWS-Region | ap-northeast-1 (Tokio) |
| FSx for ONTAP-Version | ONTAP 9.17.1P4D3 |
| FSx-Konfiguration | SINGLE_AZ_1 |
| Python | 3.12 |
| Bereitstellungsmethode | CloudFormation (Standard) |

## Lambda-VPC-Platzierungsarchitektur

Basierend auf den bei der Validierung gewonnenen Erkenntnissen werden die Lambda-Funktionen innerhalb und außerhalb des VPC getrennt platziert.

**Lambda innerhalb des VPC** (nur Funktionen, die ONTAP REST API-Zugriff benötigen):
- Discovery Lambda — S3 AP + ONTAP API

**Lambda außerhalb des VPC** (nutzen nur APIs verwalteter AWS-Services):
- Alle anderen Lambda-Funktionen

> **Grund**: Der Zugriff auf APIs verwalteter AWS-Services (Athena, Bedrock, Textract usw.) von einer Lambda innerhalb des VPC erfordert einen Interface VPC Endpoint (jeweils 7,20 $/Monat). Lambda-Funktionen außerhalb des VPC können über das Internet direkt auf AWS-APIs zugreifen und laufen ohne zusätzliche Kosten.

> **Hinweis**: Für UCs, die die ONTAP REST API verwenden (UC1 Recht und Compliance), ist `EnableVpcEndpoints=true` zwingend erforderlich, da die ONTAP-Anmeldeinformationen über den Secrets Manager VPC Endpoint abgerufen werden.

## FlexCache-Rendering-Beschleunigungserweiterung

### Übersicht

In VFX-Rendering-Workflows sind render input assets (Texturen, Geometrie, Plates) leselastig, was sie zu einem idealen Ziel für FlexCache macht. Durch das dynamische Erstellen eines FlexCache beim Jobstart und das automatische Löschen nach Abschluss des Renderings können Sie sowohl Kostenoptimierung als auch Leistungsverbesserung erreichen.

### Klassifizierung von Rendering-Daten

| Datentyp | Zugriffsmuster | FlexCache anwendbar | S3 AP-Nutzung |
|-----------|---------------|:---:|:---:|
| Textures | Nur Lesen | ✅ | ⚠️ Binär |
| Geometry/Plates | Nur Lesen | ✅ | ⚠️ Binär |
| Scene Files | Nur Lesen | ✅ | ❌ |
| Render Output (EXR/PNG) | Schreiben | ❌ | ✅ QC/Metadaten |
| Logs | Schreiben → Lesen | ❌ | ✅ Analyse |
| Cache (sim/fluid) | Lesen/Schreiben | ❌ | ❌ |

### Dynamic FlexCache Render Workflow

Details zu einem Workflow, der pro Job einen FlexCache erstellt und löscht, finden Sie unter:

- **[Dynamic FlexCache Render/EDA Workflow](../dynamic-flexcache-render-workflow/README.md)** — Automatisierung mit Step Functions
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md) — Multi-Region-Render-Farm
- [Branchen-/Workload-Zuordnung](../docs/industry-workload-mapping.md) — Pattern E: Media/VFX Render Farm

### Erwartete Vorteile

| KPI | Ohne FlexCache | Mit FlexCache | Verbesserung |
|-----|--------------|---------------|--------|
| Wartezeit bis zum Rendering-Start | 10-20 Min. | 2-5 Min. | 75% |
| Zeit pro Frame | 15 Min. | 10 Min. | 33% |
| WAN-Übertragung pro Job | 500GB | 50GB | 90% |
| Kosten pro Frame | $0.50 | $0.35 | 30% |

---

## AWS-Dokumentationslinks

| Service | Dokumentation |
|---------|------------|
| FSx for ONTAP | [FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon CloudFront | [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) |
| Amazon Bedrock | [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Ausrichtung am Well-Architected Framework

| Säule | Ausrichtung |
|----|------|
| Operative Exzellenz | X-Ray-Tracing, EMF-Metriken, Überwachung des Jobstatus |
| Sicherheit | IAM mit geringsten Rechten, CloudFront OAC, KMS-Verschlüsselung |
| Zuverlässigkeit | Step Functions Retry/Catch, Qualitätsprüfungs-Gate |
| Leistungseffizienz | CloudFront CDN-Auslieferung, Lambda-Parallelverarbeitung |
| Kostenoptimierung | Serverlos, Nutzung des CloudFront-Cache |
| Nachhaltigkeit | On-Demand-Ausführung, reduzierte Origin-Last über CDN |

---

## Lokale Tests

### Prüfung der Voraussetzungen

```bash
# Voraussetzungen prüfen
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (für sam local)
aws sts get-caller-identity  # AWS-Anmeldeinformationen
```

### sam local invoke

```bash
# Build
# Voraussetzung: AWS SAM CLI ist erforderlich. sam build verpackt den Code und den gemeinsamen Layer automatisch.
sam build

# Discovery Lambda lokal ausführen
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Mit Überschreibung der Umgebungsvariablen
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit-Tests

```bash
python3 -m pytest tests/ -v
```

Weitere Details finden Sie im [Schnellstart für lokale Tests](../docs/local-testing-quick-start.md).

---

## Ausgabebeispiel (Output Sample)

Beispielausgabe einer VFX-Rendering-Qualitätsprüfung:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 48,
    "prefix": "renders/shot-042/"
  },
  "quality_check": [
    {
      "key": "renders/shot-042/frame-0001.exr",
      "resolution": "4096x2160",
      "color_space": "ACEScg",
      "quality_score": 0.94,
      "issues": [],
      "cloudfront_url": "https://d1234.cloudfront.net/delivery/shot-042/frame-0001.exr"
    }
  ],
  "delivery": {
    "total_frames": 48,
    "passed_qc": 46,
    "failed_qc": 2,
    "cloudfront_distribution": "d1234.cloudfront.net"
  }
}
```

> **Anmerkung**: Das Obige ist eine Beispielausgabe; die tatsächlichen Werte variieren je nach Umgebung und Eingabedaten. Benchmark-Zahlen sind ein Dimensionierungsrichtwert (sizing reference), keine Servicegrenze (service limit).

---

## Governance Note

> Dieses Muster bietet technische Architekturberatung. Es handelt sich nicht um Rechts-, Compliance- oder Regulierungsberatung. Organisationen sollten qualifizierte Fachleute konsultieren.

---

## S3AP Compatibility

Informationen zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Mustern der S3 Access Points for FSx for ONTAP finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
