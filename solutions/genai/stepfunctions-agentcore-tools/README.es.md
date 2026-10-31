# Step Functions × AgentCore Gateway — Flujos de trabajo como herramientas de agente IA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

Un ejemplo que expone un flujo de trabajo Standard de Step Functions (Descubrir →
Procesar → Informar) sobre archivos en FSx for ONTAP S3 Access Points como herramientas
de agente IA, mediante el conector Step Functions integrado de Amazon Bedrock AgentCore
Gateway.

El agente decide cuándo ejecutar el flujo y qué entrada pasar; la máquina de estados
garantiza el orden de los pasos. La secuencia aprobada queda en el flujo, la decisión de
inicio corresponde al agente.

## Casos de uso

- Iniciar un flujo de Step Functions existente desde un agente sin modificar la máquina de estados
- Mantener los pasos y las aprobaciones en el flujo, delegar solo la decisión de ejecución al agente
- Dejar que el agente inspeccione hasta dónde avanzó una ejecución mediante el historial

## Arquitectura

```
Agente IA ──MCP──▶ AgentCore Gateway (conector Step Functions)
                     │ GatewayServiceRole → states:StartExecution, etc.
                     ▼
            Standard StateMachine (Discover→Choice→Map→Report)
                     │
        Discovery / Processing / Report Lambda
                     │
               S3 Access Point (FSx for ONTAP / S3 normal en DemoMode)
```

Consulte [docs/architecture.md](docs/architecture.md) para más detalles.

## Herramientas expuestas

| Herramienta | Entrada | Uso |
|---|---|---|
| `workflow___StartExecution` | `input` (cadena JSON) | Iniciar el flujo |
| `workflow___ListExecutions` | `statusFilter` (opcional) | Listar ejecuciones (solo Standard) |
| `workflow___DescribeStateMachine` | `includedData` (opcional) | Metadatos/definición de la máquina de estados |
| `workflow___DescribeExecution` | `executionArn`, `includedData` | Comprobar estado y resultado |
| `workflow___GetExecutionHistory` | `executionArn` | Historial de pasos |

El ARN fijado de la máquina de estados no aparece en la herramienta y el agente no puede cambiarlo.

## Parámetros

| Parámetro | Descripción | Predeterminado |
|---|---|---|
| `S3AccessPointAlias` | Alias S3 AP del volumen FSx for ONTAP (nombre de bucket normal en DemoMode) | (obligatorio) |
| `DemoMode` | `true` funciona sin FSx for ONTAP (bucket S3 normal) | `false` |
| `FilePrefix` | Prefijo a recorrer | `input/` |
| `BedrockModelId` | Modelo de resumen / ID de perfil de inferencia ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Máx. archivos por ejecución | `100` |
| `NotificationEmail` | Destino SNS (vacío para omitir) | `""` |
| `GatewayName` | Nombre del Gateway (usado por el script de despliegue) | `sfn-agentcore-tools-gateway` |

## Despliegue

El Gateway y el destino conector son recursos de CloudFormation de primera clase
(`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`), así que todo el patrón cabe en
una plantilla declarativa. El script de despliegue es un envoltorio
`sam build` + `sam deploy` que verifica `tools/list` después.

```bash
# DemoMode (sin FSx for ONTAP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# Producción (S3 AP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# Limpieza
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

Los ejemplos de conversación y los pasos de verificación están en [docs/demo-guide.md](docs/demo-guide.md).

## Umbrales de Human Review

La Lambda Processing evalúa la confianza del resumen con `shared/human_review.py`.

| Confianza | Decisión |
|---|---|
| `>= 0.85` (predeterminado `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`) | AUTO_APPROVE |
| `>= 0.30` (predeterminado `HUMAN_REVIEW_REJECT_THRESHOLD`) y `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

Los umbrales se pueden sobrescribir con variables de entorno. La decisión se incluye en
el resultado; este patrón no actúa sobre ella automáticamente.

## Clasificación de datos

La Lambda Report etiqueta la salida con `data_classification` de
`shared/data_classification.py` (predeterminado `INTERNAL`, modificable con `DATA_CLASSIFICATION`).

## Governance Note

- El agente solo decide cuándo ejecutar y comprueba el estado. El orden, las
  ramificaciones y las aprobaciones los garantiza la máquina de estados; el agente no
  puede omitirlos ni reordenarlos.
- El ARN fijado no se expone, así que el agente no puede iniciar otra máquina de estados.
- El resumen/clasificación por IA es una **señal de apoyo**, no una decisión final. Una
  confianza por debajo del umbral se enruta a revisión humana.
- Las operaciones por token de tarea (`SendTaskSuccess`, etc.) no se exponen aquí, porque
  IAM no puede limitarlas a ejecuciones específicas.
- Esto es una guía de gobernanza, no asesoramiento legal ni de cumplimiento.

## Pruebas

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## Puntos a tener en cuenta

La restricción de misma región, un pin por operación, el mojibake `?` de las entradas en
japonés y el remedio `\uXXXX`, y el límite de Cedar sobre `input` están reunidos en
[docs/demo-guide.md](docs/demo-guide.md#既知の注意点).

## Referencias

- [AWS Step Functions as Connector Target (oficial)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools (What's New)](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)
