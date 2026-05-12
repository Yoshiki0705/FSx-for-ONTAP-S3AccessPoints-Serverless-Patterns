# Validación de Archivos de Diseño EDA — Guía de Demostración

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Resumen Ejecutivo

Esta guía define una demostración técnica dirigida a ingenieros de diseño de semiconductores. La demostración muestra un flujo de trabajo automatizado de validación de calidad para archivos de diseño (GDS/OASIS), ilustrando el valor de optimizar las revisiones de diseño previas al tapeout.

**Mensaje central de la demostración**: Completar en minutos las verificaciones de calidad entre bloques IP que los ingenieros de diseño realizaban manualmente, permitiendo tomar acciones inmediatas con informes de revisión de diseño generados por IA.

**Tiempo estimado**: 3–5 minutos (video de captura de pantalla con narración)

---

## Target Audience & Persona

### Primary Audience: Usuarios finales de EDA (ingenieros de diseño)

| Ítem | Detalle |
|------|---------|
| **Cargo** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tareas diarias** | Diseño de layout, ejecución de DRC, integración de bloques IP, preparación de tapeout |
| **Desafío** | Lleva tiempo comprender transversalmente la calidad de múltiples bloques IP |
| **Entorno de herramientas** | Herramientas EDA como Calibre, Virtuoso, IC Compiler, Innovus, etc. |
| **Resultado esperado** | Detectar problemas de calidad de diseño tempranamente y cumplir con el cronograma de tapeout |

### Persona: Tanaka-san (Physical Design Lead)

- Gestiona más de 40 bloques IP en un proyecto SoC a gran escala
- Necesita realizar una revisión de calidad de todos los bloques 2 semanas antes del tapeout
- Es poco realista verificar individualmente los archivos GDS/OASIS de cada bloque
- "Quiero comprender de un vistazo el resumen de calidad de todos los bloques"

---

## Demo Scenario: Pre-tapeout Quality Review

### Descripción del escenario

En la fase de revisión de calidad previa al tapeout, el líder de diseño ejecuta una validación de calidad automatizada sobre múltiples bloques IP (más de 40 archivos) y toma decisiones de acción basadas en informes de revisión generados por IA.

### Visión general del flujo de trabajo

```
Conjunto de archivos    Validación         Resultados de      Revisión por IA
de diseño              automatizada        análisis           Generación de
(GDS/OASIS)       →    Activación de   →   Agregación     →   informe
                       flujo de trabajo    estadística        (lenguaje natural)
                                          (Athena SQL)
```

### Valor demostrado en la demo

1. **Reducción de tiempo**: Completar en minutos una revisión transversal que manualmente tomaría días
2. **Exhaustividad**: Validar todos los bloques IP sin omisiones
3. **Juicio cuantitativo**: Evaluación objetiva de calidad mediante detección de valores atípicos estadísticos (método IQR)
4. **Accionable**: La IA presenta recomendaciones de respuesta concretas

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Pantalla**: Lista de archivos del proyecto de diseño (más de 40 archivos GDS/OASIS)

**Resumen de narración**:
> Dos semanas antes del tapeout. Es necesario verificar la calidad de diseño de más de 40 bloques IP.
> No es realista abrir y verificar cada archivo individualmente con herramientas EDA.
> Anomalías en el número de celdas, valores atípicos en bounding box, violaciones de convenciones de nomenclatura — se necesita un método para detectarlos transversalmente.

**Key Visual**:
- Estructura de directorios de archivos de diseño (.gds, .gds2, .oas, .oasis)
- Superposición de texto "Revisión manual: estimado 3–5 días"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Pantalla**: Operación del ingeniero de diseño activando el flujo de trabajo de validación de calidad

**Resumen de narración**:
> Después de alcanzar el hito de diseño, se inicia el flujo de trabajo de validación de calidad.
> Simplemente especificando el directorio objetivo, comienza la validación automática de todos los archivos de diseño.

**Key Visual**:
- Pantalla de ejecución del flujo de trabajo (consola de Step Functions)
- Parámetros de entrada: ruta del volumen objetivo, filtro de archivos (.gds/.oasis)
- Confirmación de inicio de ejecución

**Acción del ingeniero**:
```
Objetivo: Todos los archivos de diseño bajo /vol/eda_designs/
Filtro: .gds, .gds2, .oas, .oasis
Ejecución: Inicio del flujo de trabajo de validación de calidad
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Pantalla**: Visualización del progreso durante la ejecución del flujo de trabajo

**Resumen de narración**:
> El flujo de trabajo ejecuta automáticamente lo siguiente:
> 1. Detección y listado de archivos de diseño
> 2. Extracción de metadatos del encabezado de cada archivo (library_name, cell_count, bounding_box, units)
> 3. Análisis estadístico de los datos extraídos (consulta SQL)
> 4. Generación de informe de revisión de diseño por IA
>
> Incluso con archivos GDS de gran capacidad (varios GB), se procesan rápidamente al leer solo la parte del encabezado (64KB).

**Key Visual**:
- Cada paso del flujo de trabajo completándose secuencialmente
- Visualización de procesamiento paralelo (Map State) procesando múltiples archivos simultáneamente
- Tiempo de procesamiento: aproximadamente 2–3 minutos (para 40 archivos)

---

### Section 4: Results Review (2:30–3:45)

**Pantalla**: Resultados de consulta SQL de Athena y resumen estadístico

**Resumen de narración**:
> Los resultados del análisis se pueden consultar libremente con SQL.
> Por ejemplo, es posible realizar análisis ad hoc como "mostrar celdas con bounding box anormalmente grande".

**Key Visual — Ejemplo de consulta Athena**:
```sql
-- Detección de valores atípicos en bounding box
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Resultados de consulta**:

| file_key | library_name | width | height | Juicio |
|----------|-------------|-------|--------|--------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Valor atípico |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Valor atípico |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Valor atípico |

---

### Section 5: Actionable Insights (3:45–5:00)

**Pantalla**: Informe de revisión de diseño generado por IA

**Resumen de narración**:
> La IA interpreta los resultados del análisis estadístico y genera automáticamente un informe de revisión para ingenieros de diseño.
> Incluye evaluación de riesgos, recomendaciones de respuesta concretas y elementos de acción priorizados.
> Basándose en este informe, se puede iniciar inmediatamente la discusión en la reunión de revisión previa al tapeout.

**Key Visual — Informe de revisión por IA (extracto)**:

```markdown
# Informe de Revisión de Diseño

## Evaluación de Riesgo: Medium

## Resumen de Hallazgos
- Valores atípicos en bounding box: 3 casos
- Violaciones de convenciones de nomenclatura: 2 casos
- Archivos inválidos: 2 casos

## Respuestas Recomendadas (por prioridad)
1. [High] Investigar la causa de 2 archivos inválidos
2. [Medium] Considerar optimización de layout de analog_frontend.oas
3. [Low] Unificar convenciones de nomenclatura (block-a-io → block_a_io)
```

**Cierre**:
> La revisión transversal que tomaba días manualmente se completa en minutos.
> Los ingenieros de diseño pueden concentrarse en confirmar los resultados del análisis y decidir acciones.

---

## Screen Capture Plan

### Lista de capturas de pantalla necesarias

| # | Pantalla | Sección | Notas |
|---|----------|---------|-------|
| 1 | Lista de directorios de archivos de diseño | Section 1 | Estructura de archivos en FSx ONTAP |
| 2 | Pantalla de inicio de ejecución del flujo de trabajo | Section 2 | Consola de Step Functions |
| 3 | Flujo de trabajo en ejecución (procesamiento paralelo Map State) | Section 3 | Estado con progreso visible |
| 4 | Pantalla de flujo de trabajo completado | Section 3 | Todos los pasos exitosos |
| 5 | Editor de consultas Athena + resultados | Section 4 | Consulta de detección de valores atípicos |
| 6 | Ejemplo de salida JSON de metadatos | Section 4 | Resultado de extracción de 1 archivo |
| 7 | Informe completo de revisión de diseño por IA | Section 5 | Visualización renderizada en Markdown |
| 8 | Correo de notificación SNS | Section 5 | Notificación de finalización de informe |

### Procedimiento de captura

1. Colocar datos de muestra en el entorno de demostración
2. Ejecutar manualmente el flujo de trabajo y capturar pantalla en cada paso
3. Ejecutar consulta en la consola de Athena y capturar resultados
4. Descargar el informe generado desde S3 y mostrarlo

---

## Capturas de pantalla verificadas de UI/UX (reverificación 2026-05-10)

Siguiendo la misma política que Phase 7 UC15/16/17, se capturan **pantallas de UI/UX que los ingenieros de diseño ven realmente en su trabajo diario**.
Se excluyen vistas técnicas como el gráfico de Step Functions (detalles en
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md)).

### 1. FSx for NetApp ONTAP Volumes — Volumen para archivos de diseño

Lista de volúmenes de ONTAP vista por los ingenieros de diseño. Archivos GDS/OASIS colocados en `eda_demo_vol`
gestionados con NTFS ACL.

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     内容: FSx コンソールで ONTAP Volumes 一覧（eda_demo_vol 等）、Status=Created、Type=ONTAP
     マスク: アカウント ID、SVM ID の実値、ファイルシステム ID -->
![UC6: Lista de FSx Volumes](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. S3 出力バケット — 設計ドキュメント・分析結果の一覧

Pantalla donde el responsable de revisión de diseño confirma los resultados después de completar el flujo de trabajo.
Organizado en 3 prefijos: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容: S3 コンソールで bucket の top-level prefix を確認
     マスク: アカウント ID、バケット名プレフィックス -->
![UC6: Bucket de salida S3](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. S3 出力バケット — 設計ドキュメント・分析結果の一覧

Pantalla donde el responsable de revisión de diseño confirma los resultados después de completar el flujo de trabajo.
Organizado en 3 prefijos: `metadata/` / `athena-results/` / `reports/`.

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容: S3 コンソールで bucket の top-level prefix を確認
     マスク: アカウント ID、バケット名プレフィックス -->
![UC6: Bucket de salida S3](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Athena クエリ結果 — EDA メタデータの SQL 分析

Pantalla donde el líder de diseño explora información DRC de forma ad hoc.
Workgroup es `fsxn-eda-uc6-workgroup`, base de datos es `fsxn-eda-uc6-db`.

<!-- SCREENSHOT: uc6-athena-query-result.png
     内容: EDA メタデータ表の SELECT 結果（file_key、library_name、cell_count、bounding_box）
     マスク: アカウント ID -->
![UC6: Resultados de consulta Athena](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Bedrock 生成の設計レビューレポート

**Función destacada de UC6**: Basándose en los resultados de agregación DRC de Athena, Bedrock Nova Lite genera
un informe de revisión en japonés dirigido al Physical Design Lead.

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     内容: エグゼクティブサマリー + セル数分析 + 命名規則違反一覧 + リスク評価 (High/Medium/Low)
     実サンプル内容:
       ## 設計レビューサマリー
       ### エグゼクティブサマリー
       今回のDRC集計結果に基づき、設計品質の全体評価を以下に示します。
       設計ファイルは合計2件で、セル数分布は安定しており、バウンディングボックス外れ値は確認されませんでした。
       しかし、命名規則違反が6件見つかりました。
       ...
       ### リスク評価
       - **High**: なし
       - **Medium**: 命名規則違反が6件確認されました。
       - **Low**: セル数分布やバウンディングボックス外れ値に問題はありません。
     マスク: アカウント ID -->
![UC6: Informe de revisión de diseño de Bedrock](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### Valores medidos (verificación de despliegue AWS 2026-05-10)

- **Tiempo de ejecución de Step Functions**: ~30 segundos (Discovery + Map(2 archivos) + DRC + Report)
- **Informe generado por Bedrock**: 2,093 bytes (formato markdown en japonés)
- **Consulta Athena**: 0.02 KB escaneados, tiempo de ejecución 812 ms
- **Stack real**: `fsxn-eda-uc6` (ap-northeast-1, en operación al 2026-05-10)

---

## Narration Outline

### Tono y estilo

- **Perspectiva**: Primera persona del ingeniero de diseño (Tanaka-san)
- **Tono**: Práctico, orientado a la resolución de problemas
- **Idioma**: Japonés (opción de subtítulos en inglés)
- **Velocidad**: Lenta y clara (por ser una demostración técnica)

### Estructura de narración

| Sección | Tiempo | Mensaje clave |
|---------|--------|---------------|
| Problem | 0:00–0:45 | "Necesito verificar la calidad de más de 40 bloques antes del tapeout. Manualmente no llegaré a tiempo" |
| Trigger | 0:45–1:30 | "Solo necesito iniciar el flujo de trabajo después del hito de diseño" |
| Analysis | 1:30–2:30 | "Análisis de encabezado → extracción de metadatos → análisis estadístico procede automáticamente" |
| Results | 2:30–3:45 | "Consulta libremente con SQL. Identificación inmediata de valores atípicos" |
| Insights | 3:45–5:00 | "Informe de IA presenta acciones priorizadas. Conecta directamente con la reunión de revisión" |

---

## Sample Data Requirements

### Datos de muestra necesarios

| # | Archivo | Formato | Propósito |
|---|---------|---------|-----------|
| 1 | `top_chip_v3.gds` | GDSII | Chip principal (gran escala, más de 1000 celdas) |
| 2 | `block_a_io.gds2` | GDSII | Bloque I/O (datos normales) |
| 3 | `memory_ctrl.oasis` | OASIS | Controlador de memoria (datos normales) |
| 4 | `analog_frontend.oas` | OASIS | Bloque analógico (valor atípico: BB grande) |
| 5 | `test_block_debug.gds` | GDSII | Para depuración (valor atípico: altura anormal) |
| 6 | `legacy_io_v1.gds2` | GDSII | Bloque legacy (valor atípico: ancho y altura) |
| 7 | `block-a-io.gds2` | GDSII | Muestra de violación de convención de nomenclatura |
| 8 | `TOP CHIP (copy).gds` | GDSII | Muestra de violación de convención de nomenclatura |

### Política de generación de datos de muestra

- **Configuración mínima**: 8 archivos (lista anterior) cubren todos los escenarios de la demo
- **Configuración recomendada**: Más de 40 archivos (mejora la persuasión del análisis estadístico)
- **Método de generación**: Script Python genera archivos de prueba con encabezados GDSII/OASIS válidos
- **Tamaño**: Aproximadamente 100KB por archivo es suficiente, ya que solo se analiza el encabezado

### Puntos de verificación del entorno de demostración existente

- [ ] ¿Están colocados los datos de muestra en el volumen FSx ONTAP?
- [ ] ¿Está configurado el S3 Access Point?
- [ ] ¿Existe la definición de tabla en Glue Data Catalog?
- [ ] ¿Está disponible el workgroup de Athena?

---

## Timeline

### Alcanzable en 1 semana

| # | Tarea | Tiempo requerido | Prerrequisitos |
|---|-------|------------------|----------------|
| 1 | Generación de datos de muestra (8 archivos) | 2 horas | Entorno Python |
| 2 | Confirmación de ejecución del flujo de trabajo en entorno de demo | 2 horas | Entorno desplegado |
| 3 | Obtención de capturas de pantalla (8 pantallas) | 3 horas | Después de completar tarea 2 |
| 4 | Finalización del guion de narración | 2 horas | Después de completar tarea 3 |
| 5 | Edición de video (capturas + narración) | 4 horas | Después de completar tareas 3, 4 |
| 6 | Revisión y correcciones | 2 horas | Después de completar tarea 5 |
| **Total** | | **15 horas** | |

### Prerrequisitos (necesarios para lograr en 1 semana)

- Flujo de trabajo de Step Functions desplegado y funcionando normalmente
- Funciones Lambda (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) verificadas en funcionamiento
- Tabla y consultas de Athena ejecutables
- Acceso al modelo Bedrock habilitado

### Future Enhancements (expansiones futuras)

| # | Ítem de expansión | Descripción | Prioridad |
|---|------------------|-------------|-----------|
| 1 | Integración con herramientas DRC | Importación directa de archivos de resultados DRC de Calibre/Pegasus | High |
| 2 | Dashboard interactivo | Dashboard de calidad de diseño mediante QuickSight | Medium |
| 3 | Notificación Slack/Teams | Notificación por chat al completar informe de revisión | Medium |
| 4 | Revisión diferencial | Detección y reporte automático de diferencias con ejecución anterior | High |
| 5 | Definición de reglas personalizadas | Permitir configuración de reglas de calidad específicas del proyecto | Medium |
| 6 | Informes multilingües | Generación de informes en inglés/japonés/chino | Low |
| 7 | Integración CI/CD | Incorporar como puerta de calidad automática dentro del flujo de diseño | High |
| 8 | Soporte para datos a gran escala | Optimización de procesamiento paralelo para más de 1000 archivos | Medium |

---

## Technical Notes (para creadores de la demo)

### Componentes utilizados (solo implementación existente)

| Componente | Rol |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo completo |
| Lambda (Discovery) | Detección y listado de archivos de diseño |
| Lambda (MetadataExtraction) | Análisis de encabezados GDSII/OASIS y extracción de metadatos |
| Lambda (DrcAggregation) | Ejecución de análisis estadístico mediante Athena SQL |
| Lambda (ReportGeneration) | Generación de informe de revisión por IA mediante Bedrock |
| Amazon Athena | Consultas SQL sobre metadatos |
| Amazon Bedrock | Generación de informes en lenguaje natural (Nova Lite / Claude) |

### Respaldo durante la ejecución de la demo

| Escenario | Respuesta |
|-----------|-----------|
| Fallo en ejecución del flujo de trabajo | Usar pantalla de ejecución pregrabada |
| Retraso en respuesta de Bedrock | Mostrar informe pregenerado |
| Timeout de consulta Athena | Mostrar CSV de resultados obtenidos previamente |
| Fallo de red | Convertir a video todas las pantallas capturadas previamente |

---

*Este documento fue creado como guía de producción de video de demostración para presentaciones técnicas.*
