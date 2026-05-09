# UC5: Salud — Clasificación automática y anonimización de imágenes DICOM

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | Español

## Arquitectura de extremo a extremo (Entrada → Salida)

---

## Flujo de alto nivel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/pacs_archive/                                                          │
│  ├── CT/patient_001/study_20240315/series_001.dcm    (CT scan)               │
│  ├── MR/patient_002/study_20240316/brain_t1.dcm      (MRI)                   │
│  ├── XR/patient_003/study_20240317/chest_pa.dcm      (X-ray)                 │
│  └── US/patient_004/study_20240318/abdomen.dicom     (Ultrasound)            │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-dicom-vol-ext-s3alias                                           │
│  • ListObjectsV2 (DICOM file discovery)                                      │
│  • GetObject (DICOM file retrieval)                                          │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │  Discovery   │───▶│ DICOM Parse  │───▶│PII Detection │───▶│Anonymiza- │  │
│  │  Lambda      │    │  Lambda      │    │  Lambda      │    │tion Lambda│  │
│  │             │    │             │    │             │    │           │  │
│  │  • VPC内     │    │  • Metadata  │    │  • Comprehend│    │  • PHI     │  │
│  │  • S3 AP List│    │    extraction│    │    Medical   │    │    removal │  │
│  │  • .dcm      │    │  • Patient   │    │  • PII       │    │  • Masking │  │
│  │    detection │    │    info      │    │    detection │    │    process │  │
│  └─────────────┘    └──────────────┘    └──────────────┘    └───────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── metadata/YYYY/MM/DD/                                                    │
│  │   └── patient_001_series_001.json   ← DICOM metadata                     │
│  ├── pii-reports/YYYY/MM/DD/                                                 │
│  │   └── patient_001_series_001_pii.json  ← PII detection results           │
│  └── anonymized/YYYY/MM/DD/                                                  │
│      └── anon_series_001.dcm           ← Anonymized DICOM                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Diagrama Mermaid

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrada — FSx for NetApp ONTAP"]
        DICOM["Imágenes médicas DICOM<br/>.dcm, .dicom"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Disparador"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Flujo de trabajo Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Ejecución dentro del VPC<br/>• Descubrimiento de archivos via S3 AP<br/>• Filtro .dcm/.dicom<br/>• Generación de manifiesto"]
        DP["2️⃣ DICOM Parse Lambda<br/>• Recuperación de DICOM via S3 AP<br/>• Extracción de metadatos del encabezado<br/>  (nombre del paciente, fecha de estudio, modalidad,<br/>   parte del cuerpo, institución)<br/>• Clasificación basada en modalidad"]
        PII["3️⃣ PII Detection Lambda<br/>• Comprehend Medical<br/>• API DetectPHI<br/>• Detección de información de salud protegida (PHI)<br/>• Posición de detección y puntuación de confianza"]
        ANON["4️⃣ Anonymization Lambda<br/>• Procesamiento de enmascaramiento PHI<br/>• Anonimización de etiquetas DICOM<br/>  (nombre del paciente→hash, fecha de nacimiento→edad)<br/>• Salida de DICOM anonimizado"]
    end

    subgraph OUTPUT["📤 Salida — S3 Bucket"]
        META["metadata/*.json<br/>Metadatos DICOM"]
        PIIR["pii-reports/*.json<br/>Resultados de detección PII"]
        ANOND["anonymized/*.dcm<br/>DICOM anonimizado"]
    end

    subgraph NOTIFY["📧 Notificación"]
        SNS["Amazon SNS<br/>Notificación de finalización del procesamiento"]
    end

    DICOM --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> DP
    DP --> PII
    PII --> ANON
    DP --> META
    PII --> PIIR
    ANON --> ANOND
    ANON --> SNS
```

---

## Detalle del flujo de datos

### Entrada
| Elemento | Descripción |
|----------|-------------|
| **Origen** | Volumen FSx for NetApp ONTAP |
| **Tipos de archivo** | .dcm, .dicom (imágenes médicas DICOM) |
| **Método de acceso** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Estrategia de lectura** | Recuperación completa del archivo DICOM (encabezado + datos de píxeles) |

### Procesamiento
| Paso | Servicio | Función |
|------|----------|---------|
| Discovery | Lambda (VPC) | Descubrir archivos DICOM via S3 AP, generar manifiesto |
| DICOM Parse | Lambda | Extraer metadatos de encabezados DICOM (info del paciente, modalidad, fecha de estudio, etc.) |
| PII Detection | Lambda + Comprehend Medical | Detectar información de salud protegida via DetectPHI |
| Anonymization | Lambda | Enmascaramiento y anonimización de PHI, salida de DICOM anonimizado |

### Salida
| Artefacto | Formato | Descripción |
|-----------|---------|-------------|
| Metadatos DICOM | `metadata/YYYY/MM/DD/{stem}.json` | Metadatos extraídos (modalidad, parte del cuerpo, fecha de estudio) |
| Informe PII | `pii-reports/YYYY/MM/DD/{stem}_pii.json` | Resultados de detección PHI (posición, tipo, confianza) |
| DICOM anonimizado | `anonymized/YYYY/MM/DD/{stem}.dcm` | Archivo DICOM anonimizado |
| Notificación SNS | Correo electrónico | Notificación de finalización del procesamiento (cantidad procesada y anonimizada) |

---

## Decisiones de diseño clave

1. **S3 AP en lugar de NFS** — No se necesita montaje NFS desde Lambda; archivos DICOM recuperados via API S3
2. **Especialización de Comprehend Medical** — Identificación PII de alta precisión mediante detección PHI específica del dominio médico
3. **Anonimización por etapas** — Tres etapas (extracción de metadatos → detección PII → anonimización) garantizan la trazabilidad de auditoría
4. **Conformidad con el estándar DICOM** — Reglas de anonimización basadas en DICOM PS3.15 (perfiles de seguridad)
5. **Conformidad HIPAA / leyes de privacidad** — Anonimización por método Safe Harbor (eliminación de 18 identificadores)
6. **Sondeo (no basado en eventos)** — S3 AP no admite notificaciones de eventos, por lo que se utiliza ejecución programada periódica

---

## Servicios AWS utilizados

| Servicio | Rol |
|----------|-----|
| FSx for NetApp ONTAP | Almacenamiento de imágenes médicas PACS/VNA |
| S3 Access Points | Acceso serverless a volúmenes ONTAP |
| EventBridge Scheduler | Disparador periódico |
| Step Functions | Orquestación del flujo de trabajo |
| Lambda | Cómputo (Discovery, DICOM Parse, PII Detection, Anonymization) |
| Amazon Comprehend Medical | Detección de PHI (información de salud protegida) |
| SNS | Notificación de finalización del procesamiento |
| Secrets Manager | Gestión de credenciales de la API REST de ONTAP |
| CloudWatch + X-Ray | Observabilidad |
