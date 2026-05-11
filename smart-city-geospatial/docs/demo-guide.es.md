# UC17 Script de demostración (sesión de 30 minutos)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Requisitos previos

- Cuenta de AWS, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Modelo Bedrock Nova Lite v1:0 habilitado

## Cronograma

### 0:00 - 0:05 Introducción (5 minutos)

- Desafíos de los gobiernos locales: aumento del uso de datos GIS en planificación urbana, respuesta a desastres y conservación de infraestructura
- Desafíos tradicionales: el análisis GIS se centra en software especializado como ArcGIS / QGIS
- Propuesta: automatización con FSxN S3AP + serverless

### 0:05 - 0:10 Arquitectura (5 minutos)

- Importancia de la normalización CRS (fuentes de datos mixtas)
- Generación de informes de planificación urbana mediante Bedrock
- Fórmulas de cálculo del modelo de riesgo (inundación, terremoto, deslizamiento de tierra)

### 0:10 - 0:15 Despliegue (5 minutos)

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-uc17-demo \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### 0:15 - 0:22 Ejecución del procesamiento (7 minutos)

```bash
# Subir fotografía aérea de muestra (distrito de Sendai)
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# Ejecutar Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

Verificación de resultados:
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json` (información CRS)
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json` (distribución de uso del suelo)
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json` (puntuación de riesgo de desastres)
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md` (informe generado por Bedrock)

### 0:22 - 0:27 Explicación del mapa de riesgos (5 minutos)

- Verificar cambios en series temporales en la tabla DynamoDB `landuse-history`
- Mostrar el markdown del informe generado por Bedrock
- Visualización de las puntuaciones de riesgo de inundación, terremoto y deslizamiento de tierra

### 0:27 - 0:30 Cierre (3 minutos)

- Posibilidad de integración con Amazon Location Service
- Procesamiento de nubes de puntos en operación real (despliegue de LAS Layer)
- Próximos pasos: integración con MapServer, portal para ciudadanos

## Preguntas frecuentes y respuestas

**P. ¿Se realiza realmente la conversión CRS?**  
R. Solo al implementar rasterio / pyproj Layer. Fallback con verificación `PYPROJ_AVAILABLE`.

**P. ¿Criterios de selección del modelo Bedrock?**  
R. Nova Lite tiene buen equilibrio costo/precisión. Para textos largos se recomienda Claude Sonnet.
R. Nova Lite tiene alta eficiencia de costos en la generación de informes en japonés. Claude 3 Haiku es una alternativa cuando se prioriza la precisión.

---

## Acerca del destino de salida: seleccionable con OutputDestination (Patrón B)

UC17 smart-city-geospatial soporta el parámetro `OutputDestination` desde la actualización del 2026-05-11
(consulte `docs/output-destination-patterns.md`).

**Cargas de trabajo objetivo**: metadatos de normalización CRS / clasificación de uso del suelo / evaluación de infraestructura / mapas de riesgo / informes generados por Bedrock

**2 modos**:

### STANDARD_S3 (predeterminado, como antes)
Crea un nuevo bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) y
escribe los resultados de IA allí. Solo el manifest de Discovery Lambda se escribe
en el S3 Access Point (como antes).

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (otros parámetros obligatorios)
```

### FSXN_S3AP (patrón "no data movement")
Los metadatos de normalización CRS, resultados de clasificación de uso del suelo, evaluación de infraestructura, mapas de riesgo e informes de planificación urbana (Markdown) generados por Bedrock se escriben de vuelta al
**mismo volumen FSx ONTAP** que los datos GIS originales a través del FSxN S3 Access Point.
Los responsables de planificación urbana pueden consultar directamente los resultados de IA dentro de la estructura de directorios existente de SMB/NFS.
No se crea un bucket S3 estándar.

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (otros parámetros obligatorios)
```

**Notas importantes**:

- Se recomienda encarecidamente especificar `S3AccessPointName` (permitir IAM tanto en formato Alias como ARN)
- Objetos superiores a 5GB no son posibles con FSxN S3AP (especificación de AWS), se requiere carga multiparte
- ChangeDetection Lambda solo usa DynamoDB, por lo que no se ve afectado por `OutputDestination`
- Los informes de Bedrock se escriben como Markdown (`text/markdown; charset=utf-8`), por lo que pueden
  visualizarse directamente con editores de texto de clientes SMB/NFS
- Para las restricciones de las especificaciones de AWS, consulte
  [la sección "Restricciones de las especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
  y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Capturas de pantalla UI/UX verificadas

Siguiendo el mismo enfoque que las demos de Phase 7 UC15/16/17 y UC6/11/14, dirigido a
**pantallas UI/UX que los usuarios finales realmente ven en sus operaciones diarias**.
Las vistas técnicas (gráfico de Step Functions, eventos de pila CloudFormation, etc.)
están consolidadas en `docs/verification-results-*.md`.

### Estado de verificación para este caso de uso

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX**: Not yet captured

### Capturas de pantalla existentes

![UC17 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc17-demo/uc17-stepfunctions-graph.png)

### Pantallas UI/UX objetivo para re-verificación (lista de capturas recomendadas)

- Bucket S3 de salida (tiles/, land-use/, change-detection/, risk-maps/, reports/)
- Informe de planificación urbana generado por Bedrock (vista previa Markdown)
- Tabla DynamoDB landuse_history (historial de clasificación de uso del suelo)
- Vista previa JSON del mapa de riesgos (clasificación CRITICAL/HIGH/MEDIUM/LOW)
- Artefactos AI en volumen FSx ONTAP (modo FSXN_S3AP — informe Markdown visible vía SMB/NFS)

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
