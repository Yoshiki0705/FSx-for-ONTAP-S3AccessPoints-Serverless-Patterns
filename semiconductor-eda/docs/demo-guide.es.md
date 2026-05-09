# Validación de archivos de diseño EDA — Guía de demostración

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta guía define una demostración técnica dirigida a ingenieros de diseño de semiconductores. La demo muestra un flujo de trabajo de validación automática de calidad para archivos de diseño (GDS/OASIS), demostrando el valor de optimizar las revisiones de diseño previas al tapeout.

**Mensaje central de la demo**: Automatizar las verificaciones de calidad entre bloques IP que los ingenieros realizaban manualmente, completándolas en minutos y permitiendo acciones inmediatas mediante informes de revisión de diseño generados por IA.

**Duración estimada**: 3–5 minutos (video de captura de pantalla con narración)

---

## Target Audience & Persona

### Audiencia principal: Usuarios finales de EDA (Ingenieros de diseño)

| Elemento | Detalles |
|----------|----------|
| **Puesto** | Physical Design Engineer / DRC Engineer / Design Lead |
| **Tareas diarias** | Diseño de layout, ejecución de DRC, integración de bloques IP, preparación para tapeout |
| **Desafíos** | Obtener una visión transversal de la calidad en múltiples bloques IP consume mucho tiempo |
| **Entorno de herramientas** | Herramientas EDA como Calibre, Virtuoso, IC Compiler, Innovus |
| **Resultado esperado** | Detección temprana de problemas de calidad de diseño para cumplir con el cronograma de tapeout |

### Persona: Tanaka-san (Physical Design Lead)

- Gestiona más de 40 bloques IP en un proyecto SoC a gran escala
- Necesita realizar revisiones de calidad de todos los bloques 2 semanas antes del tapeout
- Verificar individualmente los archivos GDS/OASIS de cada bloque es poco práctico
- "Quiero ver un resumen de calidad de todos los bloques de un vistazo"

---

## Demo Scenario: Pre-tapeout Quality Review

### Resumen del escenario

Durante la fase de revisión de calidad previa al tapeout, el líder de diseño ejecuta una validación automática de calidad en múltiples bloques IP (más de 40 archivos) y decide las acciones a tomar basándose en los informes de revisión generados por IA.

### Flujo de trabajo general

```
Archivos de         Validación         Resultados         Revisión IA
diseño         →   automática    →    de análisis   →   Generación
(GDS/OASIS)        Flujo de            Agregación        de informe
                   trabajo             estadística       (Lenguaje
                   Activación          (Athena SQL)      natural)
```

### Valor demostrado

1. **Reducción de tiempo**: Completar revisiones transversales en minutos en lugar de días
2. **Completitud**: Validar todos los bloques IP sin omisiones
3. **Juicio cuantitativo**: Evaluación objetiva de calidad mediante detección estadística de valores atípicos (método IQR)
4. **Accionable**: La IA presenta acciones recomendadas específicas

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Pantalla**: Lista de archivos del proyecto de diseño (más de 40 archivos GDS/OASIS)

**Resumen de la narración**:
> Dos semanas antes del tapeout. Necesitamos verificar la calidad de diseño de más de 40 bloques IP.
> Abrir cada archivo individualmente en una herramienta EDA no es realista.
> Conteos de celdas anormales, valores atípicos de bounding box, violaciones de convenciones de nomenclatura — necesitamos una forma de detectarlos de manera transversal.

**Key Visual**:
- Estructura de directorio de archivos de diseño (.gds, .gds2, .oas, .oasis)
- Superposición de texto: "Revisión manual: estimada en 3–5 días"

---

### Section 2: Workflow Trigger (0:45–1:30)

**Pantalla**: El ingeniero de diseño activa el flujo de trabajo de validación de calidad

**Resumen de la narración**:
> Después de alcanzar el hito de diseño, lanzamos el flujo de trabajo de validación de calidad.
> Simplemente especificar el directorio objetivo, y la validación automática de todos los archivos de diseño comienza.

**Key Visual**:
- Pantalla de ejecución del flujo de trabajo (consola de Step Functions)
- Parámetros de entrada: ruta del volumen objetivo, filtro de archivos (.gds/.oasis)
- Confirmación de inicio de ejecución

**Acción del ingeniero**:
```
Objetivo: Todos los archivos de diseño bajo /vol/eda_designs/
Filtro: .gds, .gds2, .oas, .oasis
Acción: Iniciar flujo de trabajo de validación de calidad
```

---

### Section 3: Automated Analysis (1:30–2:30)

**Pantalla**: Visualización del progreso de ejecución del flujo de trabajo

**Resumen de la narración**:
> El flujo de trabajo ejecuta automáticamente lo siguiente:
> 1. Detección y listado de archivos de diseño
> 2. Extracción de metadatos del encabezado de cada archivo (library_name, cell_count, bounding_box, units)
> 3. Análisis estadístico de los datos extraídos (consultas SQL)
> 4. Generación de informe de revisión de diseño por IA
>
> Incluso para archivos GDS grandes (varios GB), el procesamiento es rápido porque solo se lee la parte del encabezado (64 KB).

**Key Visual**:
- Los pasos del flujo de trabajo se completan secuencialmente
- Procesamiento paralelo (Map State) mostrando múltiples archivos procesados simultáneamente
- Tiempo de procesamiento: aproximadamente 2–3 minutos (para 40 archivos)

---

### Section 4: Results Review (2:30–3:45)

**Pantalla**: Resultados de consulta Athena SQL y resumen estadístico

**Resumen de la narración**:
> Los resultados del análisis se pueden consultar libremente con SQL.
> Por ejemplo, análisis ad-hoc como "mostrar celdas con bounding boxes anormalmente grandes" es posible.

**Key Visual — Ejemplo de consulta Athena**:
```sql
-- Detección de valores atípicos de bounding box
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — Resultados de la consulta**:

| file_key | library_name | width | height | Veredicto |
|----------|-------------|-------|--------|-----------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | Atípico |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | Atípico |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | Atípico |

---

### Section 5: Actionable Insights (3:45–5:00)

**Pantalla**: Informe de revisión de diseño generado por IA

**Resumen de la narración**:
> La IA interpreta los resultados del análisis estadístico y genera automáticamente un informe de revisión para los ingenieros de diseño.
> Incluye evaluación de riesgos, acciones recomendadas específicas y elementos de acción priorizados.
> Basándose en este informe, las discusiones pueden comenzar inmediatamente en la reunión de revisión previa al tapeout.

**Key Visual — Informe de revisión IA (Extracto)**:

```markdown
# Informe de revisión de diseño

## Evaluación de riesgos: Medium

## Resumen de hallazgos
- Valores atípicos de bounding box: 3 elementos
- Violaciones de convenciones de nomenclatura: 2 elementos
- Archivos inválidos: 2 elementos

## Acciones recomendadas (por prioridad)
1. [High] Investigar la causa de los 2 archivos inválidos
2. [Medium] Considerar la optimización del layout para analog_frontend.oas
3. [Low] Unificar convenciones de nomenclatura (block-a-io → block_a_io)
```

**Cierre**:
> Las revisiones transversales que antes tomaban días manualmente ahora se completan en minutos.
> Los ingenieros de diseño pueden concentrarse en revisar los resultados y decidir las acciones.

---

## Screen Capture Plan

### Capturas de pantalla requeridas

| # | Pantalla | Sección | Notas |
|---|----------|---------|-------|
| 1 | Lista del directorio de archivos de diseño | Section 1 | Estructura de archivos en FSx ONTAP |
| 2 | Pantalla de inicio de ejecución del flujo de trabajo | Section 2 | Consola de Step Functions |
| 3 | Flujo de trabajo en progreso (procesamiento paralelo Map State) | Section 3 | Progreso visible |
| 4 | Pantalla de finalización del flujo de trabajo | Section 3 | Todos los pasos exitosos |
| 5 | Editor de consultas Athena + resultados | Section 4 | Consulta de detección de atípicos |
| 6 | Ejemplo de salida JSON de metadatos | Section 4 | Resultado de extracción para 1 archivo |
| 7 | Informe de revisión de diseño IA (texto completo) | Section 5 | Visualización Markdown renderizada |
| 8 | Correo de notificación SNS | Section 5 | Notificación de finalización del informe |

### Procedimiento de captura

1. Colocar datos de ejemplo en el entorno de demostración
2. Ejecutar manualmente el flujo de trabajo y capturar pantallas en cada paso
3. Ejecutar consultas en la consola de Athena y capturar resultados
4. Descargar el informe generado desde S3 y mostrarlo

---

## Narration Outline

### Tono y estilo

- **Perspectiva**: Primera persona del ingeniero de diseño (Tanaka-san)
- **Tono**: Práctico, orientado a la resolución de problemas
- **Idioma**: Japonés (subtítulos en inglés opcionales)
- **Velocidad**: Lenta y clara (para una demo técnica)

### Estructura de la narración

| Sección | Tiempo | Mensaje clave |
|---------|--------|---------------|
| Problem | 0:00–0:45 | "Necesitamos verificar la calidad de más de 40 bloques antes del tapeout. La revisión manual no alcanzará" |
| Trigger | 0:45–1:30 | "Solo lanzar el flujo de trabajo después del hito de diseño" |
| Analysis | 1:30–2:30 | "Análisis de encabezado → extracción de metadatos → análisis estadístico procede automáticamente" |
| Results | 2:30–3:45 | "Consultar libremente con SQL. Identificar atípicos inmediatamente" |
| Insights | 3:45–5:00 | "El informe IA presenta acciones priorizadas. Alimenta directamente las reuniones de revisión" |

---

## Sample Data Requirements

### Datos de ejemplo requeridos

| # | Archivo | Formato | Propósito |
|---|---------|---------|-----------|
| 1 | `top_chip_v3.gds` | GDSII | Chip principal (gran escala, 1000+ celdas) |
| 2 | `block_a_io.gds2` | GDSII | Bloque I/O (datos normales) |
| 3 | `memory_ctrl.oasis` | OASIS | Controlador de memoria (datos normales) |
| 4 | `analog_frontend.oas` | OASIS | Bloque analógico (atípico: BB grande) |
| 5 | `test_block_debug.gds` | GDSII | Bloque de depuración (atípico: altura anormal) |
| 6 | `legacy_io_v1.gds2` | GDSII | Bloque legacy (atípico: ancho y alto) |
| 7 | `block-a-io.gds2` | GDSII | Ejemplo de violación de convención de nomenclatura |
| 8 | `TOP CHIP (copy).gds` | GDSII | Ejemplo de violación de convención de nomenclatura |

### Política de generación de datos de ejemplo

- **Configuración mínima**: 8 archivos (lista anterior) cubriendo todos los escenarios de la demo
- **Configuración recomendada**: Más de 40 archivos (para un análisis estadístico más convincente)
- **Método de generación**: Script Python para generar archivos de prueba con encabezados GDSII/OASIS válidos
- **Tamaño**: ~100 KB por archivo es suficiente ya que solo se realiza análisis de encabezado

### Lista de verificación del entorno de demo existente

- [ ] Datos de ejemplo colocados en el volumen FSx ONTAP
- [ ] S3 Access Point configurado
- [ ] Definición de tabla de Glue Data Catalog existente
- [ ] Grupo de trabajo de Athena disponible

---

## Timeline

### Alcanzable en 1 semana

| # | Tarea | Tiempo requerido | Prerrequisitos |
|---|-------|-----------------|----------------|
| 1 | Generación de datos de ejemplo (8 archivos) | 2 horas | Entorno Python |
| 2 | Verificación de ejecución del flujo de trabajo en entorno de demo | 2 horas | Entorno desplegado |
| 3 | Adquisición de capturas de pantalla (8 pantallas) | 3 horas | Después de la tarea 2 |
| 4 | Finalización del guion de narración | 2 horas | Después de la tarea 3 |
| 5 | Edición de video (capturas + narración) | 4 horas | Después de las tareas 3, 4 |
| 6 | Revisión y correcciones | 2 horas | Después de la tarea 5 |
| **Total** | | **15 horas** | |

### Prerrequisitos (necesarios para completar en 1 semana)

- Flujo de trabajo de Step Functions desplegado y funcionando normalmente
- Funciones Lambda (Discovery, MetadataExtraction, DrcAggregation, ReportGeneration) verificadas
- Tablas y consultas de Athena ejecutables
- Acceso al modelo Bedrock habilitado

### Future Enhancements (Mejoras futuras)

| # | Mejora | Descripción | Prioridad |
|---|--------|-------------|-----------|
| 1 | Integración de herramientas DRC | Ingesta directa de archivos de resultados DRC de Calibre/Pegasus | High |
| 2 | Panel interactivo | Panel de calidad de diseño mediante QuickSight | Medium |
| 3 | Notificaciones Slack/Teams | Notificación por chat al completar el informe | Medium |
| 4 | Revisión diferencial | Detección y reporte automático de diferencias con la ejecución anterior | High |
| 5 | Definiciones de reglas personalizadas | Permitir reglas de calidad específicas del proyecto | Medium |
| 6 | Informes multilingües | Generación de informes en inglés/japonés/chino | Low |
| 7 | Integración CI/CD | Incorporar como puerta de calidad automática en el flujo de diseño | High |
| 8 | Soporte de datos a gran escala | Optimización del procesamiento paralelo para más de 1000 archivos | Medium |

---

## Technical Notes (Para creadores de demos)

### Componentes utilizados (solo implementación existente)

| Componente | Rol |
|------------|-----|
| Step Functions | Orquestación general del flujo de trabajo |
| Lambda (Discovery) | Detección y listado de archivos de diseño |
| Lambda (MetadataExtraction) | Análisis de encabezado GDSII/OASIS y extracción de metadatos |
| Lambda (DrcAggregation) | Ejecución de análisis estadístico mediante Athena SQL |
| Lambda (ReportGeneration) | Generación de informe de revisión IA mediante Bedrock |
| Amazon Athena | Consultas SQL sobre metadatos |
| Amazon Bedrock | Generación de informes en lenguaje natural (Nova Lite / Claude) |

### Soluciones de respaldo para la ejecución de la demo

| Escenario | Respuesta |
|-----------|-----------|
| Fallo en la ejecución del flujo de trabajo | Usar pantallas de ejecución pregrabadas |
| Retraso en la respuesta de Bedrock | Mostrar informe pregenerado |
| Timeout de consulta Athena | Mostrar CSV de resultados preobtenido |
| Fallo de red | Todas las pantallas precapturadas y compiladas en video |

---

*Este documento fue creado como guía de producción para un video de demostración de presentación técnica.*
