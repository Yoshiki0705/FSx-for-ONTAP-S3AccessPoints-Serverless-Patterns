# Detección de anomalías de sensores IoT e inspección de calidad — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración muestra un flujo de trabajo que detecta automáticamente anomalías en datos de sensores IoT de líneas de fabricación y genera informes de inspección de calidad.

**Mensaje central de la demostración**: Detectar automáticamente patrones anómalos en datos de sensores para lograr la detección temprana de problemas de calidad y el mantenimiento preventivo.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Gerente de Departamento de Fabricación / Ingeniero de Control de Calidad |
| **Tareas diarias** | Monitoreo de líneas de producción, inspección de calidad, planificación de mantenimiento de equipos |
| **Desafío** | Pasar por alto anomalías en datos de sensores, permitiendo que productos defectuosos fluyan a procesos posteriores |
| **Resultados esperados** | Detección temprana de anomalías y visualización de tendencias de calidad |

### Persona: Sr. Suzuki (Ingeniero de Control de Calidad)

- Monitorea más de 100 sensores en 5 líneas de fabricación
- Las alertas basadas en umbrales generan muchas falsas alarmas y tienden a pasar por alto anomalías reales
- "Quiero detectar solo anomalías estadísticamente significativas"

---

## Demo Scenario: Análisis por lotes de detección de anomalías en sensores

### Visión general del flujo de trabajo

```
Datos de sensores    Recopilación       Detección          Informe de calidad
(CSV/Parquet)    →   de datos      →   de anomalías   →   Generación AI
                     Preprocesamiento   Análisis estadístico
                     Normalización      (Detección de valores atípicos)
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Más de 100 sensores en las líneas de fabricación generan grandes cantidades de datos diariamente. Las alertas de umbral simples producen muchas falsas alarmas y existe el riesgo de pasar por alto anomalías reales.

**Key Visual**: Gráfico de series temporales de datos de sensores, situación de exceso de alertas

### Section 2: Data Ingestion (0:45–1:30)

**Resumen de la narración**:
> Cuando los datos de sensores se acumulan en el servidor de archivos, el pipeline de análisis se inicia automáticamente.

**Key Visual**: Colocación de archivos de datos → Inicio del flujo de trabajo

### Section 3: Anomaly Detection (1:30–2:30)

**Resumen de la narración**:
> Se calculan puntuaciones de anomalía para cada sensor mediante métodos estadísticos (media móvil, desviación estándar, IQR). También se ejecuta análisis de correlación entre múltiples sensores.

**Key Visual**: Algoritmo de detección de anomalías en ejecución, mapa de calor de puntuaciones de anomalía

### Section 4: Quality Inspection (2:30–3:45)

**Resumen de la narración**:
> Las anomalías detectadas se analizan desde la perspectiva de inspección de calidad. Se identifica en qué línea y en qué proceso está ocurriendo el problema.

**Key Visual**: Resultados de consulta Athena — Distribución de anomalías por línea y proceso

### Section 5: Report & Action (3:45–5:00)

**Resumen de la narración**:
> La IA genera un informe de inspección de calidad. Presenta candidatos de causa raíz de anomalías y acciones recomendadas.

**Key Visual**: Informe de calidad generado por IA (resumen de anomalías + acciones recomendadas)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Lista de archivos de datos de sensores | Section 1 |
| 2 | Pantalla de inicio de flujo de trabajo | Section 2 |
| 3 | Progreso de procesamiento de detección de anomalías | Section 3 |
| 4 | Resultados de consulta de distribución de anomalías | Section 4 |
| 5 | Informe de inspección de calidad AI | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Las alertas de umbral pasan por alto anomalías reales" |
| Ingestion | 0:45–1:30 | "El análisis comienza automáticamente con la acumulación de datos" |
| Detection | 1:30–2:30 | "Detectar solo anomalías significativas mediante métodos estadísticos" |
| Inspection | 2:30–3:45 | "Identificar ubicaciones problemáticas a nivel de línea y proceso" |
| Report | 3:45–5:00 | "La IA presenta candidatos de causa raíz y contramedidas" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Datos de sensores normales (5 líneas × 7 días) | Línea base |
| 2 | Datos de anomalía de temperatura (2 casos) | Demostración de detección de anomalías |
| 3 | Datos de anomalía de vibración (3 casos) | Demostración de análisis de correlación |
| 4 | Patrón de degradación de calidad (1 caso) | Demostración de generación de informes |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Generación de datos de sensores de muestra | 3 horas |
| Verificación de ejecución de pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Análisis de streaming en tiempo real
- Generación automática de programación de mantenimiento preventivo
- Integración con gemelo digital

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (Data Preprocessor) | Normalización y preprocesamiento de datos de sensores |
| Lambda (Anomaly Detector) | Detección estadística de anomalías |
| Lambda (Report Generator) | Generación de informes de calidad mediante Bedrock |
| Amazon Athena | Agregación y análisis de datos de anomalías |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Volumen de datos insuficiente | Usar datos pregenerados |
| Precisión de detección insuficiente | Mostrar resultados con parámetros ajustados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics está clasificado como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: Los resultados de análisis de datos de sensores, informes de detección de anomalías y resultados de inspección de imágenes se escriben todos a través de FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los CSV de sensores originales y las imágenes de inspección. No se
crean buckets S3 estándar (patrón "no data movement").

**Parámetros de CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias para lectura de datos de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias para escritura de salida (puede ser el mismo que el de entrada)

**Ejemplo de despliegue**:
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (otros parámetros obligatorios)
```

**Vista desde usuarios SMB/NFS**:
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # Datos de sensores originales
  └── analysis/2026/05/                 # Resultados de detección de anomalías AI (dentro del mismo volumen)
      └── line_A_report.json
```

Para restricciones de especificaciones de AWS, consulte
[la sección "Restricciones de especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Capturas de pantalla de UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas de UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráfico de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (consulte README raíz)
- 📸 **Recaptura de UI/UX**: ✅ Capturado en verificación de redespliegue 2026-05-10 (confirmado gráfico de Step Functions UC3, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consulte la "Guía de captura" al final de este documento

### Capturado en verificación de redespliegue 2026-05-10 (centrado en UI/UX)

#### UC3 Step Functions Graph view (SUCCEEDED)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para usuarios finales que visualiza
el estado de ejecución de cada Lambda / Parallel / Map state mediante colores.

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

![UC3 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-succeeded.png)

![UC3 Step Functions Graph (vista expandida)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-expanded.png)

![UC3 Step Functions Graph (vista ampliada — detalle de cada paso)](../../docs/screenshots/masked/uc3-demo/step-functions-graph-zoomed.png)

### Pantallas de UI/UX objetivo en reverificación (lista de captura recomendada)

- Bucket de salida S3 (metrics/, anomalies/, reports/)
- Resultados de consulta Athena (detección de anomalías de sensores IoT)
- Etiquetas de imágenes de inspección de calidad de Rekognition
- Informe resumen de calidad de fabricación

### Guía de captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=manufacturing-analytics bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC3`

2. **Colocación de datos de muestra**:
   - Subir archivos de muestra al prefijo `sensors/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-manufacturing-analytics-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-manufacturing-analytics-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo electrónico SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC3`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
