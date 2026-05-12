# Verificación de calidad de renderizado VFX — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Resumen Ejecutivo

Esta demostración presenta un pipeline de verificación de calidad para salidas de renderizado VFX. Mediante la validación automática de frames de renderizado, se detectan tempranamente artefactos y frames con errores.

**Mensaje central de la demostración**: Validación automática de grandes volúmenes de frames de renderizado y detección instantánea de problemas de calidad. Acelera la toma de decisiones sobre re-renderizado.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Ítem | Detalle |
|------|------|
| **Cargo** | Supervisor VFX / TD de Renderizado |
| **Tareas diarias** | Gestión de trabajos de renderizado, verificación de calidad, aprobación de tomas |
| **Desafío** | La verificación visual de miles de frames requiere una cantidad enorme de tiempo |
| **Resultado esperado** | Detección automática de frames problemáticos y aceleración de decisiones de re-renderizado |

### Persona: Sr. Nakamura (Supervisor VFX)

- 1 proyecto con más de 50 tomas, cada toma con 100–500 frames
- La verificación de calidad después de completar el renderizado es un cuello de botella
- "Quiero detectar automáticamente frames negros, exceso de ruido y falta de texturas"

---

## Demo Scenario: Verificación de Calidad de Lote de Renderizado

### Visión General del Flujo de Trabajo

```
Salida de renderizado     Análisis de frames      Evaluación de calidad          Reporte QC
(EXR/PNG)            →   Extracción de       →   Detección de          →    Resumen por
                         metadatos               anomalías                  toma
                                                 (análisis estadístico)
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de narración**:
> Miles de frames generados por la granja de renderizado. Es poco realista verificar visualmente problemas como frames negros, ruido y falta de texturas.

**Key Visual**: Carpeta de salida de renderizado (gran cantidad de archivos EXR)

### Section 2: Pipeline Trigger (0:45–1:30)

**Resumen de narración**:
> Después de completar el trabajo de renderizado, el pipeline de verificación de calidad se inicia automáticamente. Procesamiento paralelo por toma.

**Key Visual**: Inicio del flujo de trabajo, lista de tomas

### Section 3: Frame Analysis (1:30–2:30)

**Resumen de narración**:
> Se calculan estadísticas de píxeles de cada frame (luminancia promedio, varianza, histograma). También se verifica la consistencia entre frames.

**Key Visual**: Procesamiento de análisis de frames, gráficos de estadísticas de píxeles

### Section 4: Quality Assessment (2:30–3:45)

**Resumen de narración**:
> Se detectan valores atípicos estadísticos e identifican frames problemáticos. Se clasifican frames negros (luminancia cero), exceso de ruido (varianza anormal), etc.

**Key Visual**: Lista de frames problemáticos, clasificación por categoría

### Section 5: QC Report (3:45–5:00)

**Resumen de narración**:
> Se genera un reporte QC por toma. Se presentan los rangos de frames que requieren re-renderizado y las causas estimadas.

**Key Visual**: Reporte QC generado por IA (resumen por toma + acciones recomendadas)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Carpeta de salida de renderizado | Section 1 |
| 2 | Pantalla de inicio del pipeline | Section 2 |
| 3 | Progreso de análisis de frames | Section 3 |
| 4 | Resultados de detección de frames problemáticos | Section 4 |
| 5 | Reporte QC | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje Clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "La verificación visual de miles de frames es poco realista" |
| Trigger | 0:45–1:30 | "QC inicia automáticamente al completar el renderizado" |
| Analysis | 1:30–2:30 | "Evaluación cuantitativa de calidad de frames mediante estadísticas de píxeles" |
| Assessment | 2:30–3:45 | "Clasificación e identificación automática de frames problemáticos" |
| Report | 3:45–5:00 | "Soporte inmediato para decisiones de re-renderizado" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Frames normales (100 unidades) | Línea base |
| 2 | Frames negros (3 unidades) | Demo de detección de anomalías |
| 3 | Frames con exceso de ruido (5 unidades) | Demo de evaluación de calidad |
| 4 | Frames con falta de texturas (2 unidades) | Demo de clasificación |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de datos de frames de muestra | 3 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Detección de artefactos mediante deep learning
- Integración con granja de renderizado (re-renderizado automático)
- Integración con sistema de seguimiento de tomas

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (Frame Analyzer) | Extracción de metadatos de frames y estadísticas de píxeles |
| Lambda (Quality Checker) | Evaluación estadística de calidad |
| Lambda (Report Generator) | Generación de reporte QC mediante Bedrock |
| Amazon Athena | Análisis agregado de estadísticas de frames |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Retraso en procesamiento de frames de gran capacidad | Cambiar a análisis de miniaturas |
| Retraso de Bedrock | Mostrar reporte pregenerado |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del Destino de Salida: FSxN S3 Access Point (Pattern A)

UC4 media-vfx está clasificado como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: Los metadatos de renderizado y la evaluación de calidad de frames se escriben completamente a través de FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los activos de renderizado originales. No se crean
buckets S3 estándar (patrón "no data movement").

**Parámetros de CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias para lectura de datos de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias para escritura de salida (puede ser el mismo que el de entrada)

**Ejemplo de despliegue**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (otros parámetros obligatorios)
```

**Visibilidad desde usuarios SMB/NFS**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # Frame de renderizado original
  └── qc/shot_001/                     # Evaluación de calidad de frames (dentro del mismo volumen)
      └── frame_0001_qc.json
```

Para restricciones de especificaciones de AWS, consulte
[la sección "Restricciones de especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Capturas de Pantalla UI/UX Verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráficos de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de Verificación de Este Caso de Uso

- ⚠️ **Verificación E2E**: Solo funcionalidad parcial (se recomienda verificación adicional en entorno de producción)
- 📸 **Captura UI/UX**: ✅ SFN Graph completado (Phase 8 Theme D, commit 3c90042)

### Capturas de Pantalla Existentes (de Phase 1-6 aplicables)

![Vista de gráfico de Step Functions UC4 (SUCCEEDED)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![Gráfico de Step Functions UC4 (vista ampliada — detalle de cada paso)](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### Pantallas UI/UX Objetivo para Re-verificación (lista de captura recomendada)

- (A definir durante re-verificación)

### Guía de Captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (existencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=media-vfx bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC4`

2. **Colocación de datos de muestra**:
   - Subir archivos de muestra al prefijo `renders/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-media-vfx-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-media-vfx-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py media-vfx-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC4`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
