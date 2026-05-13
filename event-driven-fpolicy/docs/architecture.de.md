🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

# Ereignisgesteuerte FPolicy — Architektur

## End-to-End-Architektur

```mermaid
flowchart TB
    subgraph CLIENT["📁 NFS/SMB-Client"]
        NFS["Dateioperationen<br/>create / write / delete / rename"]
    end

    subgraph ONTAP["🗄️ FSx for NetApp ONTAP"]
        FPOLICY["FPolicy Engine<br/>Asynchroner Modus"]
    end

    subgraph FARGATE["🐳 ECS Fargate"]
        SERVER["FPolicy Server<br/>TCP :9898<br/>• XML-Parsing<br/>• Pfadnormalisierung<br/>• JSON-Konvertierung"]
    end

    subgraph PIPELINE["⚡ Ereignis-Pipeline"]
        SQS["SQS Queue<br/>Ingestion + DLQ"]
        BRIDGE["Bridge Lambda<br/>SQS → EventBridge<br/>Batch-Verarbeitung (10/Aufruf)"]
        EB["EventBridge<br/>Benutzerdefinierter Bus<br/>fsxn-fpolicy-events"]
    end

    subgraph TARGETS["🎯 UC-Ziele"]
        UC1["UC: Compliance-Audit"]
        UC2["UC: Sicherheitsüberwachung"]
        UC3["UC: Datenpipeline"]
    end

    NFS -->|"Dateioperation"| FPOLICY
    FPOLICY -->|"TCP-Benachrichtigung<br/>(Async)"| SERVER
    SERVER -->|"SendMessage"| SQS
    SQS -->|"Event Source Mapping"| BRIDGE
    BRIDGE -->|"PutEvents"| EB
    EB -->|"Regel 1"| UC1
    EB -->|"Regel 2"| UC2
    EB -->|"Regel 3"| UC3
```

## Komponentendetails

### 1. FPolicy Server (ECS Fargate)

| Element | Details |
|---------|---------|
| Laufzeitumgebung | ECS Fargate (ARM64, 0.25 vCPU / 512 MB) |
| Protokoll | TCP :9898 (ONTAP FPolicy Binär-Framing) |
| Modus | Asynchron — keine Antwort für NOTI_REQ erforderlich |
| Verarbeitung | XML-Parsing → Pfadnormalisierung → JSON-Konvertierung → SQS-Versand |

### 2. IP Updater Lambda

| Element | Details |
|---------|---------|
| Auslöser | EventBridge Rule (ECS Task State Change → RUNNING) |
| Verarbeitung | 1. Policy deaktivieren → 2. Engine-IP aktualisieren → 3. Policy reaktivieren |
| Authentifizierung | ONTAP-Anmeldedaten aus Secrets Manager abrufen |

## Sicherheitsüberlegungen

- FPolicy Server im privaten Subnetz bereitgestellt (kein öffentlicher Zugang)
- AWS-Dienstzugriff über VPC Endpoints (kein Internet-Transit)
- Security Group erlaubt TCP 9898 nur aus VPC CIDR (10.0.0.0/8)
- ONTAP-Administratoranmeldedaten über Secrets Manager verwaltet
