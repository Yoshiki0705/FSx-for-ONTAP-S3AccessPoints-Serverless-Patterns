# Procesamiento automatizado de contratos y facturas — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo muestra un pipeline de procesamiento automatizado para contratos y facturas. Combina extracción OCR con extracción de entidades para generar datos estructurados.

**Mensaje clave**: Digitalizar automáticamente contratos y facturas en papel, extrayendo instantáneamente montos, fechas y proveedores.

**Duración prevista**: 3–5 min

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



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Planteamiento: Procesar 200+ facturas manualmente al mes es insostenible

### Section 2 (0:45–1:30)
> Carga: Colocar archivos inicia procesamiento automático

### Section 3 (1:30–2:30)
> OCR y extracción: OCR + IA para clasificación y extracción de campos

### Section 4 (2:30–3:45)
> Salida estructurada: Datos inmediatamente utilizables

### Section 5 (3:45–5:00)
> Validación e informe: Puntuación de confianza identifica elementos a revisar

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo |
| Lambda (OCR Processor) | Extracción texto vía Textract |
| Lambda (Entity Extractor) | Extracción entidades vía Bedrock |
| Lambda (Classifier) | Clasificación tipo documento |
| Amazon Athena | Análisis agregado de datos extraídos |

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
- 📸 **Captura UI/UX**: ✅ SFN Graph completado (Phase 8 Theme D, commit 081cc66)

### Capturas de pantalla existentes (de Phase 1-6)

![UC2 Vista de gráfico Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### Pantallas UI/UX objetivo para re-verificación (lista de capturas recomendadas)

- Bucket S3 de salida (textract-results/, comprehend-entities/, reports/)
- Resultados JSON de Textract OCR (campos extraídos de contratos/facturas)
- Resultados de detección de entidades Comprehend (organizaciones, fechas, montos)
- Informe resumen generado por Bedrock

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
