# OCR de albaranes de envío y análisis de inventario -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline OCR para albaranes de envío y análisis de inventario. Los documentos en papel se digitalizan automáticamente para seguimiento en tiempo real.

**Mensaje clave**: Procesar automáticamente albaranes por OCR para actualizar inventario en tiempo real y mejorar la eficiencia logística.

**Duración prevista**: 3–5 min

---

## Destino de salida: seleccionable mediante OutputDestination (Pattern B)

Este UC admite el parámetro `OutputDestination` (actualización 2026-05-10,
consulte `docs/output-destination-patterns.md`).

**Dos modos**:

- **STANDARD_S3** (predeterminado): los artefactos de IA van a un nuevo bucket S3
- **FSXN_S3AP** ("no data movement"): los artefactos de IA regresan al mismo
  volumen FSx ONTAP mediante S3 Access Point, visibles para usuarios SMB/NFS en
  la estructura de directorios existente

```bash
# Modo FSXN_S3AP
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

Para restricciones de especificación de AWS y soluciones alternativas, consulte
[README.es.md — Restricciones de especificación de AWS](../../README.es.md#restricciones-de-especificación-de-aws-y-soluciones-alternativas).

---
## Workflow

```
Carga escaneo → Extracción OCR → Parsing campos → Actualización inventario → Informe análisis
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: La entrada manual de documentos en papel es propensa a errores y consume tiempo

### Section 2 (0:45–1:30)
> Carga: Colocar imágenes escaneadas de albaranes inicia el procesamiento

### Section 3 (1:30–2:30)
> OCR y parsing: Extracción de texto y conversión a datos estructurados

### Section 4 (2:30–3:45)
> Actualización inventario: Actualización en tiempo real basada en datos extraídos

### Section 5 (3:45–5:00)
> Informe análisis: Dashboard logístico y alertas de detección de anomalías

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (OCR Engine) | Extracción de texto de albaranes |
| Lambda (Field Parser) | Parsing de datos estructurados |
| Lambda (Inventory Updater) | Actualización de datos de inventario |
| Amazon Athena | Análisis estadístico logístico |

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
- 📸 **Captura UI/UX**: ✅ SFN Graph completado (Phase 8 Theme D, commit 3c90042)

### Capturas de pantalla existentes (de Phase 1-6)

![UC12 Vista de gráfico Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Gráfico Step Functions (ampliado — detalle por paso)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### Pantallas UI/UX objetivo para re-verificación (lista de capturas recomendadas)

- Bucket S3 de salida (waybills-ocr/, inventory/, reports/)
- Resultados OCR Textract de guías de envío (Cross-Region)
- Etiquetas de imagen de almacén Rekognition
- Informe de agregación de entregas

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
