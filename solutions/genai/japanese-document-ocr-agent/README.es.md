# OCR de documentos japoneses × agentes de IA — Textract (Tokio) sobre S3 Access Points

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

Un ejemplo que lee documentos escaneados (imágenes, PDF, TIFF) de FSx for ONTAP S3 Access Points con Amazon Textract en la
región de Tokio y expone la ejecución como herramientas para agentes de IA mediante el conector de Step Functions de
Amazon Bedrock AgentCore Gateway. La compatibilidad de Textract con el japonés y su disponibilidad en Tokio se anunciaron
el 2026-11-02.

El agente decide solo qué colección leer, con qué perfil y cuántos documentos. La máquina de estados se encarga del orden
de los pasos, los reintentos y el tratamiento de los fallos. El texto OCR nunca llega al agente: se escribe en un bucket de
resultados.

## Casos de uso

- Aplicar OCR japonés a escaneos (facturas, contratos, notas) sin sacarlos del servidor de archivos
- Hacer que un agente enumere los documentos que debe revisar una persona, con el motivo de cada uno
- Extraer, con su evidencia, campos como el total de una factura japonesa donde Textract Forms no está disponible
  (opcional)

## Arquitectura

```
Agente de IA ──MCP──▶ AgentCore Gateway (NONE | AWS_IAM)
                       │ GatewayServiceRole: states:StartExecution, etc.
                       ▼
           Standard StateMachine (Discover → Map → Report)
                       │
   Imágenes: bytes a Textract (sync)    PDF / TIFF: copia temporal → Textract (async)
                       │
   S3 Access Points (S3 normal en DemoMode) ──▶ bucket de resultados (result.json / text.txt / manifest.json)
```

Consulte [docs/architecture.md](docs/architecture.md) para el detalle (en japonés).

## Herramientas expuestas

| Herramienta | Entrada | Uso |
|---|---|---|
| `ocr___StartExecution` | `input` (cadena JSON) | Inicia el OCR. Devuelve `executionArn` |
| `ocr___DescribeExecution` | `executionArn`, `includedData: "ALL_DATA"` | Estado y resultado |
| `ocr___ListExecutions` | `statusFilter` (opcional) | Ejecuciones recientes |
| `ocr___GetExecutionHistory` | `executionArn` | Encontrar dónde se detuvo una ejecución (salida grande) |
| `ocr___DescribeStateMachine` | `includedData` (opcional) | Consultar la definición |

El ARN de la máquina de estados está fijado y no aparece en ninguna herramienta, así que el agente no puede cambiarlo.
`DescribeExecution` sin `includedData: "ALL_DATA"` no devuelve `output` ni, en una ejecución FAILED, `error` y `cause`.

## Entrada que pasa el agente

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| Clave | Obligatoria | Regla |
|---|---|---|
| `collection` | Sí | ID ASCII (`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`) presente en la lista permitida (`CollectionsJson`) |
| `profile` | No | `text` (solo caracteres) o `structure` (caracteres, tablas, diseño). Por defecto, el de la colección |
| `max_files` | No | Entero de 1 a `MaxFilesPerExecution`. Los documentos se toman en orden de clave |
| `modified_after` | No | `YYYY-MM-DD`. Solo documentos modificados en esa fecha o después |

No se aceptan rutas ni claves de S3. Una clave desconocida o una infracción de las reglas termina la ejecución en FAILED, y
`Cause` indica cómo corregirla.

## Rutas y perfiles

| Documento | Ruta | Nota |
|---|---|---|
| PNG / JPEG, hasta 5 MiB | Sync, bytes pasados directamente | No se crea copia |
| PNG / JPEG, más de 5 MiB hasta 10 MiB | Async, copia temporal | |
| PDF / TIFF | Async, copia temporal | No se estima el número de páginas |

`text` llama a `DetectDocumentText`; `structure` llama a `AnalyzeDocument` (`TABLES` y `LAYOUT`). Forms, Queries,
AnalyzeExpense y AnalyzeID no se ofrecen (no admiten japonés o no están permitidos en Tokio).

## Lo que recibe el agente

El `output` de `DescribeExecution` (`ALL_DATA`) contiene el estado, los recuentos, la confianza media, la lista de revisión
con el motivo de cada documento y el URI S3 del resultado de cada uno. No contiene texto OCR, pero sí la clave original
(nombre de archivo). Con la extracción de campos activada, también contiene los valores de los campos (hasta 60
caracteres). La lista completa está en `manifest.json`, en el bucket de resultados.

## Parámetros

| Parámetro | Descripción | Valor por defecto |
|---|---|---|
| `S3AccessPointAlias` | Alias de los S3 Access Points (nombre de un bucket normal en DemoMode) | (obligatorio) |
| `DemoMode` | `true` funciona sin FSx for ONTAP | `false` |
| `CollectionsJson` | Lista permitida de colecciones (JSON). Si está vacía, se construye una desde `FilePrefix` | `""` |
| `MaxFilesPerExecution` | Máximo de documentos por ejecución (1–100) | `50` |
| `MapConcurrency` | Documentos procesados en paralelo. La API sync de Tokio está limitada a 1 TPS | `2` |
| `AsyncJobMaxSeconds` | Tiempo de espera de un trabajo asíncrono | `600` |
| `EnableFieldExtraction` | Extracción de campos con Bedrock. Desactivada, no se concede ningún permiso de Bedrock | `false` |
| `BedrockModelId` | ID de modelo o de perfil de inferencia para la extracción ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | Etiqueta de clasificación de datos por defecto en las salidas | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | Umbrales de confianza media | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | Qué cuenta como línea de baja confianza y la proporción de caracteres que envía un documento a revisión | `90` / `0.05` |
| `HandwritingWordRatioLimit` | Límite superior de palabras detectadas como manuscritas | `0.05` |
| `GatewayAuthorizerType` | `NONE` (solo PoC) o `AWS_IAM` | `NONE` |
| `GatewayName` | Nombre de la Gateway | `ja-ocr-agent-gateway` |
| `NotificationEmail` | Dirección de notificación SNS (vacía para omitir) | `""` |

## Despliegue

El script de despliegue ejecuta `sam build`, `sam package` y `aws cloudformation deploy`, y después comprueba el valor
almacenado de `CollectionsJson` y `tools/list`.

```bash
# DemoMode (sin FSx for ONTAP)
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points. Exigir llamadas firmadas y activar la extracción de campos
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# Limpieza (--delete-results elimina también el bucket de resultados, que contiene el texto OCR)
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

Cómo escribir las colecciones, el prompt de sistema del agente y ejemplos de conversación están en
[docs/demo-guide.md](docs/demo-guide.md) (en japonés).

## Umbrales de Human Review

La confianza media del OCR (ponderada por el número de caracteres) se evalúa con `shared/human_review.py` y luego se eleva
según estas condiciones.

| Condición | Decisión |
|---|---|
| Confianza media igual o superior a `ReviewAutoApproveThreshold` (0.95) y ninguna de las condiciones siguientes | AUTO_APPROVE |
| Confianza media inferior a 0.95 | HUMAN_REVIEW |
| Confianza media inferior a `ReviewRejectThreshold` (0.30) | REJECT |
| Más del 5 % de los caracteres están en líneas con confianza inferior a 90 | Elevado a HUMAN_REVIEW |
| Más del 5 % de las palabras se detectan como manuscritas | Elevado a HUMAN_REVIEW |
| Una tabla de estructura dudosa, como una celda combinada | Elevado a HUMAN_REVIEW |
| No se detecta ninguna línea | HUMAN_REVIEW |
| La extracción de campos tiene un campo sin evidencia o falló | Elevado a HUMAN_REVIEW (REJECT no se modifica) |

Los valores por defecto son un punto de partida, no óptimos medidos. En una ejecución con cuatro documentos sintéticos, los
cuatro pasaron a HUMAN_REVIEW con los valores por defecto, incluido un contrato sin ningún error de carácter
([docs/success-metrics.md](docs/success-metrics.md)). Mida la distribución en sus propios documentos antes de decidir. La
decisión solo se incluye en el resultado; el patrón no toma la decisión final. `result.json` contiene la decisión basada
solo en el OCR. La decisión final, con la extracción de campos, está en `manifest.json` y en el resultado de la ejecución.

## Clasificación de datos

Las salidas llevan un `data_classification` de `shared/data_classification.py`. El valor por defecto es `INTERNAL`;
cámbielo con `DataClassification` o sobrescríbalo por colección con `classification`. El bucket de resultados usa SSE-KMS,
bloquea el acceso público, rechaza las solicitudes que no usan TLS y se conserva al eliminar la pila.

## Extracción de campos (opcional)

Con `EnableFieldExtraction=true`, los campos indicados en `fields` de una colección (hasta 20, de 40 caracteres como máximo
cada uno) se extraen con la API Converse de Bedrock. El modelo devuelve cada valor con una cita del texto de origen, y el
código comprueba mecánicamente que la cita existe en el texto OCR (coincidencia de subcadena tras la normalización NFKC y la
eliminación de espacios). Un campo cuya cita no se encuentra es `grounded: false`, y uno solo basta para enviar el documento
a HUMAN_REVIEW. Un campo que el documento no contiene también cuenta como sin evidencia; liste en `fields` solo elementos
que figuren en todos los documentos de la colección.

## Governance Note

- La confianza del OCR es una señal de apoyo, no una decisión final. En la ejecución medida, un documento sin errores tenía
  el 22,6 % de sus caracteres en líneas con confianza inferior a 90, y una línea mal leída («括孤») tenía 98,2. No haga de la
  confianza la única condición de aprobación automática.
- Los valores de campo extraídos son salida de un LLM. La comprobación de citas reduce las invenciones, pero no garantiza la
  corrección.
- Los valores tomados del contenido de un documento son una entrada no fiable para un agente. Indique en su prompt de
  sistema que no siga instrucciones que aparezcan en un valor. No se midió el comportamiento con un documento que contenga
  instrucciones.
- Los PDF y TIFF se copian a un bucket temporal de la misma cuenta y región mientras se procesan (SSE-KMS, acceso público
  bloqueado, eliminación al terminar el trabajo, regla de ciclo de vida de 1 día como respaldo). Si su política no permite
  copias, limite los `suffixes` de la colección a imágenes.
- `GatewayAuthorizerType=NONE` permite a cualquiera que conozca la URL iniciar ejecuciones de OCR (no se devuelve texto).
  Úselo solo para un PoC; en entornos compartidos use `AWS_IAM`. El tipo de authorizer no se puede cambiar tras la creación.
- Textract no puede cancelar un trabajo iniciado. Dejar de esperar en `AsyncJobMaxSeconds` no detiene el cobro.
- Esto es una orientación de gobernanza y no sustituye una valoración jurídica ni de cumplimiento.

## Performance Considerations

- La API sync de Tokio está limitada a 1 TPS. En 20 llamadas consecutivas, un cliente sin reintentos fue limitado 4 veces con
  2 workers y 7 veces con 5; un cliente adaptive (hasta 5 intentos) lo fue 0 veces con 1, 2 y 5. `MapConcurrency` vale 2 por
  defecto.
- Un PDF de 3 páginas (async) terminó en unos 12 segundos a través del patrón.
- Eventos del historial de ejecución: 13 por documento sync y 20 + 9 × sondeos por documento async. El peor caso para 100
  documentos se estima en unos 23.200, dentro del límite Standard de 25.000.
- Para mantener el estado del Map por debajo de 256 KiB, con claves muy largas discovery selecciona menos documentos que
  `max_files` y devuelve `truncated`.
- El coste de Textract es por página. El Price List de Tokio indica 0,0015 USD por página para `text` y 0,019 USD por página
  para `structure` (Tables más Layout), vigente desde 2026-10-01; no contrastado con una factura.

## Pruebas

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## Puntos a tener en cuenta

- Forms no admite japonés. La solicitud se acepta, pero en la nota devolvió pares cortados a mitad de frase.
- `DescribeExecution` necesita `includedData: "ALL_DATA"`. `GetExecutionHistory` no se puede paginar.
- El japonés en una entrada de Gateway se convierte en `??`. Este patrón solo pasa ID ASCII.
- `max_files` toma los documentos en orden de clave, de modo que un primer documento dañado se elige cada vez.
- Los S3 Access Points del entorno de verificación no contenían imágenes ni PDF, por lo que no se confirmó un OCR correcto
  en un Access Point real (sí se confirmaron el listado, la lectura y la eliminación de la copia temporal). Consulte
  «既知の注意点» en [docs/demo-guide.md](docs/demo-guide.md).

## Referencias

- [Amazon Textract añade idiomas, entre ellos el japonés, y se lanza en Tokio (What's New)](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target (oficial)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- Patrón relacionado: [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## Lectura previa al paso a producción

Cómo se traducen en decisiones de diseño las restricciones que aparecen después del despliegue está documentado en el [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). El mismo contenido en dos lugares hace que la copia que deja de actualizarse sobreviva a la corregida.

- [Aprovechamiento de datos](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — restricciones del acceso a través de un access point (todos los patrones)
- [Seguridad y gobernanza](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — donde se concentran las decisiones de este patrón
- [Construir](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — revisar antes de producción (todos los patrones)
<!-- playbook-reading:end -->
