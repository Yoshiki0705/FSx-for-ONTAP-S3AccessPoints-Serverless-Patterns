# UC22: Transportation & Rail — Architecture

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["Railway Infrastructure Data<br/>JPEG/PNG/TIFF (inspection images)<br/>PDF/Excel (maintenance reports)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda"]
        DD["2️⃣ Deterioration Detector Lambda<br/>Rekognition (dual threshold: 60%/80%)<br/>+ Bedrock severity classification"]
        ME["3️⃣ Maintenance Extractor Lambda<br/>Textract + Comprehend"]
        RL["4️⃣ Report Lambda<br/>12-month trend + priority ranking"]
    end

    DISC --> DD
    DISC --> ME
    DD --> RL
    ME --> RL
```

## Safety-Critical Design

| Category | Threshold | Human Review |
|----------|-----------|-------------|
| Standard infrastructure | Rekognition >= 80% | Detection recorded |
| Bridges | Rekognition >= 60% | All < 90% reviewed |
| Signaling equipment | Rekognition >= 60% | All < 90% reviewed |
| Rail joints | Rekognition >= 60% | All < 90% reviewed |

## AWS Services Used

| Service | Role |
|---------|------|
| Amazon Rekognition | Deterioration detection (dual threshold) |
| Amazon Bedrock | Severity classification (4 levels) |
| Amazon Textract | Maintenance report analysis (Cross-Region us-east-1) |
| Amazon Comprehend | Entity extraction |

## Key Design Decisions

1. **Dual threshold** — Safety-critical (60%) vs standard (80%) detection sensitivity
2. **Mandatory human review** — All detections < 90% require engineer review
3. **12-month trend analysis** — Visualization of deterioration patterns over time
4. **Severity x component age** — Two-axis priority ranking
5. **Low-resolution handling** — Images < 1024x768 marked requires-reinspection
