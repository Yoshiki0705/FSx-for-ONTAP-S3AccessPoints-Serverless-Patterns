# Detección de anomalías IoT e inspección de calidad -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo muestra un flujo que detecta automáticamente anomalías en datos de sensores IoT de líneas de fabricación y genera informes de calidad.

**Mensaje clave**: Detectar automáticamente patrones anómalos en datos de sensores para detección temprana de problemas de calidad.

**Duración prevista**: 3-5 min

---

## Destino de salida: FSxN S3 Access Point (Pattern A)

Este UC se clasifica como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: todos los artefactos de IA/ML se escriben a través del FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los datos fuente. No se crea un bucket S3
estándar separado (patrón "no data movement").

**Parámetros CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias de salida (puede ser igual a la entrada)

Para restricciones de especificación de AWS y soluciones alternativas, consulte
[README.es.md — Restricciones de especificación de AWS](../../README.es.md#restricciones-de-especificación-de-aws-y-soluciones-alternativas).

---
## Workflow

```
Datos sensores (CSV/Parquet) -> Preprocesamiento -> Detección anomalías / Análisis estadístico -> Informe calidad (IA)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Planteamiento: Alertas por umbral no capturan anomalías reales

### Section 2 (0:45-1:30)
> Ingesta: Acumulación de datos inicia análisis automáticamente

### Section 3 (1:30-2:30)
> Detección: Métodos estadísticos detectan solo anomalías significativas

### Section 4 (2:30-3:45)
> Inspección: Identificar áreas problemáticas a nivel línea/proceso

### Section 5 (3:45-5:00)
> Informe: IA presenta causas raíz candidatas y contramedidas

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo |
| Lambda (Data Preprocessor) | Normalización datos sensores |
| Lambda (Anomaly Detector) | Detección estadística anomalías |
| Lambda (Report Generator) | Generación informe vía Bedrock |
| Amazon Athena | Análisis agregado anomalías |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*

---

## Capturas de pantalla UI/UX verificadas

Siguiendo el mismo enfoque que las demos de Phase 7 UC15/16/17 y UC6/11/14, dirigido a
**pantallas UI/UX que los usuarios finales realmente ven en sus operaciones diarias**.
Las vistas técnicas (gráfico de Step Functions, eventos de pila CloudFormation, etc.)
están consolidadas en `docs/verification-results-*.md`.

### Estado de verificación para este caso de uso

- ⚠️ **E2E**: Partial (additional verification recommended)
- 📸 **UI/UX**: Not yet captured

### Capturas de pantalla existentes (de Phase 1-6)

*(Ninguna aplicable. Por favor capture durante la re-verificación.)*

### Pantallas UI/UX objetivo para re-verificación (lista de capturas recomendadas)

- Bucket S3 de salida (metrics/, anomalies/, reports/)
- Resultados de consulta Athena (detección de anomalías de sensores IoT)
- Etiquetas de imagen de inspección de calidad Rekognition
- Informe resumen de calidad de fabricación

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
