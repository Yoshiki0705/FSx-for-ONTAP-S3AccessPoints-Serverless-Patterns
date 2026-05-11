# Pipeline de preprocesamiento de datos de conducción autónoma -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de preprocesamiento y anotación para datos de sensores de conducción autónoma. Los datos se clasifican automáticamente para generar conjuntos de datos de entrenamiento.

**Mensaje clave**: Preprocesar automáticamente datos de sensores para generar conjuntos de datos anotados listos para entrenamiento IA.

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
Recopilación sensores → Conversión formato → Clasificación frames → Generación anotaciones → Informe dataset
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: El preprocesamiento manual de datos masivos es un cuello de botella

### Section 2 (0:45–1:30)
> Carga: Colocar archivos de logs de sensores inicia el pipeline

### Section 3 (1:30–2:30)
> Preprocesamiento y clasificación: Conversión automática y clasificación IA de frames

### Section 4 (2:30–3:45)
> Resultados de anotación: Verificación de etiquetas generadas y estadísticas de calidad

### Section 5 (3:45–5:00)
> Informe dataset: Informe de preparación para entrenamiento y métricas de calidad

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Python 3.13) | Validación de calidad de datos de sensores, clasificación de escenas, generación de catálogo |
| Lambda SnapStart | Reducción de arranque en frío (`EnableSnapStart=true` opt-in) |
| SageMaker (4-way routing) | Inferencia (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Verdadero scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Clasificación de escenas / sugerencias de anotación |
| Amazon Athena | Búsqueda y agregación de metadatos |
| CloudFormation Guard Hooks | Aplicación de políticas de seguridad en despliegue |

### Prueba local (Phase 6A)

```bash
# Prueba local con SAM CLI
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

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

- Bucket S3 de salida (keyframes/, annotations/, qc/)
- Resultados de detección de objetos Rekognition en fotogramas clave
- Resumen de verificación de calidad de nube de puntos LiDAR
- JSON de anotación compatible con COCO

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
