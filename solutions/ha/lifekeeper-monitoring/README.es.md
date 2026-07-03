# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

## Descripción general

Un patrón serverless que recopila y analiza de forma no intrusiva los registros y los eventos de conmutación por error (failover) de un clúster de alta disponibilidad (HA) construido con **SIOS LifeKeeper**, a través de los S3 Access Points de **Amazon FSx for NetApp ONTAP**.

El **análisis de causa raíz (Root Cause Analysis)** y la **puntuación de salud del clúster** impulsados por Amazon Bedrock (Nova Pro) permiten identificar rápidamente la causa de una conmutación por error y detectar señales tempranas.

---

## Escenario objetivo

En entornos empresariales, SAP, Oracle y las aplicaciones críticas de negocio están protegidas en HA con SIOS LifeKeeper, y se utiliza FSx for ONTAP Multi-AZ como almacenamiento compartido.

**Desafíos**:
- Identificar la causa raíz cuando se produce una conmutación por error lleva mucho tiempo
- El análisis de los registros de LifeKeeper implica mucho trabajo manual y depende de la experiencia individual
- Añadir un agente de supervisión a los nodos del clúster HA aumenta el número de puntos de fallo
- Distinguir los fallos de la capa de almacenamiento (FSx for ONTAP) de los de la capa de aplicación (LifeKeeper) es difícil

**Solución**:
Utilizar los FSx for ONTAP S3 Access Points para procesar los registros que escribe LifeKeeper de forma **no intrusiva** mediante una canalización de análisis serverless. El análisis automatizado impulsado por IA reduce la carga operativa.

---

## Combinación de SIOS LifeKeeper + FSx for ONTAP

### Posicionamiento en la arquitectura

| Capa | Responsabilidad | Alcance de HA |
|---------|------|------------|
| Almacenamiento | FSx for ONTAP Multi-AZ | Disponibilidad de datos, redundancia de AZ, conmutación por error automática |
| Aplicación | SIOS LifeKeeper | Control de VIP, supervisión de servicios, recuperación automática |
| Análisis (este patrón) | S3 AP + Serverless + Bedrock | Análisis de registros no intrusivo, análisis de causa raíz por IA |

### Qué es SIOS LifeKeeper

Software de clustering HA para Linux/Windows proporcionado por SIOS Technology. Ofrece alta disponibilidad para aplicaciones críticas en AWS.

**Características principales**:
- Recovery Kits con reconocimiento de aplicaciones (supervisan directamente SAP S/4HANA, Oracle, NFS, IP, etc.)
- Conmutación por error entre AZ (2 AZ dentro de una misma región)
- Gestión de VIP (Elastic IP / Secondary IP)
- Prevención de split-brain mediante rutas de comunicación redundantes
- Disponible oficialmente como AWS Partner Solution

**Historial**: Astro Malaysia adoptó SIOS LifeKeeper en un entorno SAP + Oracle on AWS y logró una disponibilidad del 99,99 %.

### Compatibilidad con disco compartido de FSx for ONTAP (V10 y posteriores)

A partir de LifeKeeper V10.0.1, FSx for ONTAP puede protegerse directamente como disco compartido. Anteriormente solo estaba disponible DataKeeper (replicación a nivel de bloque); la incorporación de una configuración de disco compartido permite una configuración de HA más sencilla.

| Protocolo | Recovery Kit necesario | Notas |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | Obligatorio al usar FSx for ONTAP en AWS |
| NFS | NAS Recovery Kit | Configuración estándar de disco compartido NFS |

> Un artículo de validación de SIOS bcblog (2026-05-08) confirma que la conmutación (switchover) funciona correctamente en una configuración RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS).

### Valor que aporta FSx for ONTAP

- **Almacenamiento compartido Multi-AZ**: accesible desde ambos nodos de LifeKeeper mediante NFS/iSCSI
- **Conmutación por error automática del almacenamiento**: gestiona automáticamente los fallos de AZ de la capa de almacenamiento
- **Snapshot**: preserva el estado de los datos antes y después de la conmutación por error
- **S3 Access Points**: ruta de acceso a datos no intrusiva para el análisis de registros
- **Multiprotocolo**: ofrece SMB + NFS + iSCSI + S3 API desde un único volumen, evitando la duplicación de datos
- **Nativo de la nube**: puede empezar a usarse directamente desde la AWS Management Console (no requiere licencia aparte)

> «La gran ventaja es que, en lugar de copiar los datos a S3 para utilizarlos, se pueden aprovechar los datos que están en FSx for ONTAP directamente a través de la API de S3» — del [artículo de entrevista de SIOS bcblog](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### Referencias públicas

| Recurso | Editor | URL |
|------|--------|-----|
| Solución de alta disponibilidad con SIOS LifeKeeper y Amazon FSx for NetApp ONTAP | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| Diseño de alta disponibilidad con NetApp ONTAP y LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Uso de Amazon FSx for NetApp ONTAP como disco compartido de LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## Funcionalidades

### Discovery Lambda
- Detecta archivos de registro de LifeKeeper a través de FSx for ONTAP S3 AP
- Clasifica los registros: eventos de conmutación por error / comprobaciones de salud / cambios de configuración / registros de Recovery Kit
- Evalúa automáticamente la gravedad (CRITICAL / HIGH / MEDIUM / LOW)

### Processing Lambda
- Detecta transiciones de estado de los recursos de LifeKeeper (ISP→OSF, ISS→ISP, etc.)
- Análisis de causa raíz mediante Bedrock (Nova Pro)
- Calcula una puntuación de salud del clúster (0-100)
- Distingue los fallos de la capa de almacenamiento de los de la capa de aplicación

### Report Lambda
- Genera informes de salud en Markdown
- Envía alertas de conmutación por error mediante SNS según umbrales de gravedad
- Incluye acciones recomendadas con comandos de LifeKeeper (`lcdstatus`, comprobación de rutas de comunicación)

---

## Despliegue

### Requisitos previos

- AWS SAM CLI
- Python 3.12
- Sistema de archivos FSx for ONTAP + S3 Access Point (no necesario cuando DemoMode=true)
- Acceso al modelo de Bedrock habilitado (Amazon Nova Pro)

### Despliegue rápido

```bash
# Despliegue en DemoMode (no requiere FSx for ONTAP)
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **Nota**: `template.yaml` se utiliza con la SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con el comando `aws cloudformation deploy`, utilice `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a S3).

### Despliegue en producción

```bash
# Requisito previo: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### Parámetros

| Parámetro | Valor predeterminado | Descripción |
|-----------|-----------|------|
| S3AccessPointAlias | (obligatorio) | Alias de FSx for ONTAP S3 AP |
| DemoMode | false | Habilitar el modo demostración |
| ScheduleExpression | rate(5 minutes) | Intervalo de supervisión |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | amazon.nova-pro-v1:0 | Modelo de Bedrock para el análisis |
| FailoverAlertSeverity | CRITICAL | Gravedad mínima para las alertas de SNS |
| ClusterName | lifekeeper-cluster | Nombre del clúster de LifeKeeper |
| OutputDestination | STANDARD_S3 | Destino de salida de los informes |
| LogRetentionInDays | 90 | Período de retención de CloudWatch Logs |

---

## Pruebas

```bash
# Pruebas unitarias
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# Prueba de extremo a extremo en DemoMode
# (coloque de antemano registros de ejemplo en el bucket de S3 de demostración)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Puntuación de salud

| Puntuación | Nivel | Significado | Acción recomendada |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | Normal | Revisar informes periódicos |
| 70-89 | WARNING | Atención | Comprobar rutas de comunicación y E/S de almacenamiento |
| 50-69 | DEGRADED | Degradado | Verificar el estado con LifeKeeper GUI/CLI, supervisar FSx for ONTAP |
| 0-49 | CRITICAL | Crítico | Acción inmediata. Verificar el estado con `lcdstatus` + CLI de administración de ONTAP |

---

## Estructura de directorios

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # Plantilla SAM
├── samconfig.toml.example     # Ejemplo de configuración de despliegue
├── README.md                  # Este documento (japonés)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # Detección de registros de LifeKeeper
│   ├── processing/
│   │   └── handler.py         # Análisis de causa raíz con Bedrock
│   └── report/
│       └── handler.py         # Generación de informes, alertas
├── statemachine/
│   └── workflow.asl.json      # Definición de Step Functions
├── docs/
│   ├── architecture.md        # Detalles de la arquitectura
│   └── demo-guide.md          # Guía de demostración (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # Pruebas unitarias
```

---

## Patrones relacionados

| Patrón | Relación |
|---------|--------|
| `solutions/sap/erp-adjacent/` | Procesamiento de IDoc/por lotes de entornos SAP protegidos por LifeKeeper |
| `solutions/event-driven/fpolicy/` | Detección inmediata de registros mediante activación por eventos de FPolicy |
| `solutions/flexcache/anycast-dr/` | Referencia para configuraciones de DR multirregión |

---

## Governance Note

Este patrón está diseñado para **asistir en la supervisión operativa** de clústeres HA. Tenga en cuenta lo siguiente:

- Los resultados del análisis por IA son **información de referencia** para las decisiones operativas; no se realiza ningún control de conmutación por error automática ni operación de recuperación
- Los cambios de configuración de LifeKeeper deben realizarse siempre desde LifeKeeper GUI/CLI
- Las decisiones de conmutación por error deben delegarse en los propios mecanismos de comprobación de salud de LifeKeeper
- Este patrón está diseñado bajo la premisa de un **Human-in-the-loop**

---

## Performance Considerations

- **Intervalo de supervisión**: un intervalo de 5 minutos conlleva hasta 5 minutos de retraso de detección. Cuando se requiere inmediatez, combine la activación por eventos de FPolicy con `TriggerMode=HYBRID`
- **Tamaño de los registros**: cuando hay una gran cantidad de archivos de registro, controle el tamaño del lote con `MaxFilesPerExecution`
- **Coste de Bedrock**: en entornos donde las conmutaciones por error son frecuentes, preste atención a los costes de invocación de Bedrock. Acote los objetivos de análisis con `FailoverAlertSeverity`
- **Rendimiento de S3 AP**: FSx for ONTAP S3 AP comparte el ancho de banda de todo el sistema de archivos. Considere lecturas basadas en Snapshot para que grandes volúmenes de lectura de registros no afecten a la E/S del negocio

---

## License

MIT
