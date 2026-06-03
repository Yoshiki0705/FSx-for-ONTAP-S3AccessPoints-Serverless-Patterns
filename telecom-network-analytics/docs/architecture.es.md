# UC18: Telecomunicaciones / Análisis de Red — Detección de Anomalías CDR/Logs de Red e Informes de Cumplimiento

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | Español

## Arquitectura de Extremo a Extremo (Entrada → Salida)

---

## Diagrama de Arquitectura

```mermaid
flowchart TB
    subgraph INPUT["📥 Entrada — FSx for ONTAP"]
        DATA["Datos de Telecomunicaciones<br/>.csv/.asn1/.parquet (Archivos CDR)<br/>syslog / SNMP trap (Logs de Equipos de Red)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Disparador"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Diario 00:00 UTC"]
    end

    subgraph SFN["⚙️ Flujo de Trabajo Step Functions"]
        DISC["1️⃣ Discovery Lambda<br/>• Ejecución en VPC<br/>• Detección de archivos CDR/syslog<br/>• Aplicación de filtro de sufijos<br/>• Generación de manifiesto"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• Recuperación CDR via S3 AP<br/>• Extracción de metadatos de llamadas<br/>(ID llamante, ID llamado, duración, timestamp, ID torre celular)<br/>• Consultas estadísticas de tráfico Athena<br/>(volumen de llamadas por hora, duración media, llamadas simultáneas pico)"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Análisis Syslog RFC 5424<br/>• Análisis SNMP trap<br/>• Detección de fallos de equipo<br/>(link-down, error de hardware, caída de proceso)<br/>• Detección de exceso de umbral de capacidad (predeterminado 80%)"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• Comparación con línea base móvil de 7 días<br/>• Marcado de anomalías umbral 3σ<br/>• Puntuación de anomalías"]
        RL["5️⃣ Report Lambda<br/>• Resumen diario de salud de red<br/>• Generación de informe de alertas de anomalías<br/>• Salida S3 (reports/daily/{YYYY-MM-DD}/)<br/>• Notificación SNS<br/>• Métricas CloudWatch EMF"]
    end

    subgraph OUTPUT["📤 Salida — S3 Bucket"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>Estadísticas de Tráfico CDR"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>Análisis de Fallos de Equipo"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>Resultados de Detección de Anomalías"]
        ERROUT["errors/cdr/{filename}.json<br/>Registros de Errores de Análisis CDR"]
    end

    subgraph NOTIFY["📧 Notificación"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Alertas de Anomalías Críticas y Fallos)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## Decisiones de Diseño Clave

1. **Procesamiento paralelo de CDR y syslog** — Paralelización via Step Functions Map State para mejorar el rendimiento
2. **Athena para agregación CDR a gran escala** — SQL serverless para agregar eficientemente volúmenes masivos de CDR
3. **Línea base móvil de 7 días** — Detección de anomalías estadística considerando características del día de la semana
4. **Umbral 3σ para marcado de anomalías** — Detecta solo anomalías estadísticamente significativas
5. **Aislamiento de errores** — Los fallos de análisis CDR se registran sin interrumpir el lote completo
6. **Basado en polling** — S3 AP no soporta notificaciones de eventos

---

## Servicios AWS Utilizados

| Servicio | Rol |
|---------|------|
| FSx for ONTAP | Almacenamiento CDR/logs de red |
| S3 Access Points | Acceso serverless a volúmenes ONTAP |
| EventBridge Scheduler | Disparador diario (00:00 UTC) |
| Step Functions | Orquestación de flujo de trabajo (Map State paralelo) |
| Lambda | Cómputo (Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report) |
| Amazon Athena | Consultas SQL de estadísticas de tráfico CDR |
| Amazon Bedrock | Inferencia de detección de anomalías (Claude / Nova) |
| SNS | Notificaciones de alertas de anomalías críticas y fallos |
| Secrets Manager | Gestión de credenciales ONTAP REST API |
| CloudWatch + X-Ray | Observabilidad (Métricas EMF, trazado) |
