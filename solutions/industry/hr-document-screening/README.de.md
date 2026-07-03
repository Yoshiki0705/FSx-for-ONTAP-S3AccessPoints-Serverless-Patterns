# UC27: Personalwesen — Lebenslauf-Screening / PII-Strict-Modus

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Übersicht

Ein serverloser Workflow, der die FSx for ONTAP S3 Access Points nutzt, um Fähigkeiten und Erfahrung aus Lebensläufen und Werdegängen strukturiert zu extrahieren und im PII-Strict-Modus eine Bewertung durchzuführen, die geschützte Merkmale ausschließt.

> **Wichtig: Regulatorischer Hinweis**
> Dieses Muster ist ein **Workflow zur Dokumententriage und -zusammenfassung** und kein automatisiertes System zur Einstellungsentscheidung. Endgültige Einstellungsentscheidungen müssen stets von qualifiziertem HR-Personal getroffen werden. Vor der Nutzung müssen Sie die Konformität mit den Arbeitsgesetzen, Datenschutzvorschriften (DSGVO, APPI, CCPA usw.) und Antidiskriminierungsanforderungen der jeweiligen Länder und Regionen überprüfen. Die Ausgaben dürfen keine Rangfolge nach geschützten Merkmalen enthalten, und Bewertungserläuterungen müssen ausschließlich auf berufsbezogenen Qualifikationen und Erfahrungen beruhen.

## Success Metrics

### Outcome
Automatisierung der Dokumentenverarbeitung und -analyse zur Steigerung der betrieblichen Effizienz und Stärkung der Compliance.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Extraktionsrate der Lebenslaufdaten | ≥ 90 % |
| Fairness der Bewertung | Keine Verzerrung durch geschützte Merkmale (Alter, Geschlecht, Nationalität ausgeschlossen) |
| PII-Compliance | 100 % (keine PII in Logs) |
| Zeit zur Berichterstellung | < 5 Min. / Batch |
| Kosten / tägliche Ausführung | < 2,00 $ |
| Pflichtquote für Human Review | > 30 % (alle Bewertungsergebnisse werden vom HR-Team geprüft) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Extraktionsergebnisse der AI/ML-Dienste, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Ergebnisse mit niedriger Konfidenz erfordern eine manuelle Überprüfung
- Critical-Alarme werden von Fachexperten geprüft
- Regelmäßige Zusammenfassungsberichte werden vom Management geprüft

### Output Safeguard Requirements
- Das Ausgabeschema darf keine Felder age/gender/ethnicity/nationality enthalten
- Bewertungserläuterungen müssen ausschließlich auf berufsbezogenen Qualifikationen und Erfahrungen beruhen
- Erkannte geschützte Merkmale müssen vor der Speicherung entfernt werden
- Alle Empfehlungsergebnisse müssen zwingend einer menschlichen Prüfung unterzogen werden

## Architektur

Ausführliche Datenflussdiagramme finden Sie im [Architekturdokument](docs/architecture.de.md).

## Voraussetzungen

> **Hinweis zum NetworkOrigin des S3 AP**: Die Discovery-Lambda-Funktion wird innerhalb eines VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Point `Internet` lautet, kann er nicht über einen S3 Gateway VPC Endpoint erreicht werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen S3 AP mit NetworkOrigin=VPC oder konfigurieren Sie den Zugriff über ein NAT Gateway. Weitere Einzelheiten finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- AWS-Konto mit entsprechenden IAM-Berechtigungen
- FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- Volume mit aktiviertem S3 Access Point
- VPC, private Subnetze
- Aktivierter Amazon-Bedrock-Modellzugriff (Claude / Nova)
- Amazon Textract — Cross-Region-Aufrufkonfiguration (us-east-1)

## Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build" verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Hinweis**: `template.yaml` wird mit dem SAM CLI (`sam build` + `sam deploy`) verwendet.
> Für eine direkte Bereitstellung mit dem Befehl `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (dies erfordert das Vorab-Verpacken der Lambda-Zip-Dateien und deren Upload nach S3).

## ⚠️ Hinweise zur Performance

- Die Durchsatzkapazität von FSx for ONTAP wird **über NFS/SMB/S3 AP gemeinsam genutzt**. Die parallele Verarbeitung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinträchtigen.
- Prüfen Sie bei der Massenverarbeitung großer Dateimengen die Throughput Capacity (MBps) von FSx for ONTAP und passen Sie MapConcurrency entsprechend an.
- Empfehlung: Beginnen Sie in der Produktion mit MapConcurrency=5 und erhöhen Sie den Wert schrittweise, während Sie die CloudWatch-Metriken von FSx for ONTAP (ThroughputUtilization) überwachen.

## Bereinigung

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## Kostenschätzung (monatlich)

> **Anmerkung**: Grobe Schätzungen für die Region ap-northeast-1. Die tatsächlichen Kosten variieren je nach Nutzung.

| Konfiguration | Monatliche Schätzung |
|------|---------|
| Minimalkonfiguration (täglich 1x) | ~8-20 $ |
| Standardkonfiguration | ~20-50 $ |

---

## Governance Note

> Dieses Muster liefert technische Architekturhinweise. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Der Einsatz von KI im Bewerber-Screening muss dem Beschäftigungssicherungsgesetz und dem Gesetz über die Chancengleichheit bei der Beschäftigung entsprechen und Verzerrungen aufgrund geschützter Merkmale (Alter, Geschlecht, Nationalität usw.) ausschließen. Die KI-Bewertung ist nur eine Referenzinformation; die endgültige Entscheidung muss vom HR-Personal getroffen werden.

> **Zugehörige Vorschriften**: Beschäftigungssicherungsgesetz, Gesetz zum Schutz personenbezogener Informationen (APPI), Arbeitsnormengesetz

---

## S3AP Compatibility

Informationen zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Mustern der FSx for ONTAP S3 Access Points finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
