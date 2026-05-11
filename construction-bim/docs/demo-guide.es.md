# Detección de cambios BIM y verificación de cumplimiento de seguridad -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de detección de cambios BIM y verificación automática de cumplimiento de seguridad. Las violaciones se detectan automáticamente durante las modificaciones.

**Mensaje clave**: Detectar automáticamente violaciones de seguridad en cambios BIM para eliminar riesgos desde la fase de diseño.

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
Carga BIM → Detección cambios → Matching normativo → Detección violaciones → Informe cumplimiento
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: La revisión manual de seguridad en cada cambio es ineficiente

### Section 2 (0:45–1:30)
> Carga BIM: Colocar archivos de modelo modificados inicia la verificación

### Section 3 (1:30–2:30)
> Detección y matching: Análisis diff automático y comparación con normas de seguridad

### Section 4 (2:30–3:45)
> Violaciones detectadas: Lista de incumplimientos y niveles de gravedad

### Section 5 (3:45–5:00)
> Informe cumplimiento: Generación del informe con recomendaciones correctivas

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Change Detector) | Detección de cambios BIM |
| Lambda (Rule Matcher) | Motor de matching normativo |
| Lambda (Report Generator) | Generación de informe de cumplimiento |
| Amazon Athena | Análisis agregado del historial de violaciones |

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

- Bucket S3 de salida (drawings-ocr/, bim-metadata/, safety-reports/)
- Resultados OCR Textract de planos (Cross-Region)
- Informe de diferencias de versión BIM
- Verificación de cumplimiento de seguridad Bedrock

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
