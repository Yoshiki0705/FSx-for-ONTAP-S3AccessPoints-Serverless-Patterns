# Detección de anomalías de registro de pozo y reporte de cumplimiento -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de detección de anomalías en datos de registro de pozo y generación de reportes de cumplimiento.

**Mensaje clave**: Detectar automáticamente anomalías en datos de registro de pozo y generar reportes de cumplimiento al instante.

**Duración prevista**: 3–5 min

---

## Workflow

```
Recopilación datos pozo → Preprocesamiento señal → Detección anomalías → Matching normativo → Reporte cumplimiento
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: Buscar anomalías manualmente en grandes volúmenes de datos es ineficiente

### Section 2 (0:45–1:30)
> Carga: Colocar archivos de registro de pozo inicia el análisis

### Section 3 (1:30–2:30)
> Detección: Análisis IA de patrones detecta anomalías automáticamente

### Section 4 (2:30–3:45)
> Resultados: Lista de anomalías detectadas y clasificación por gravedad

### Section 5 (3:45–5:00)
> Reporte cumplimiento: Resultados de comparación normativa y recomendaciones

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Signal Processor) | Preprocesamiento de señal de pozo |
| Lambda (Anomaly Detector) | Detección IA de anomalías |
| Lambda (Compliance Checker) | Verificación de cumplimiento normativo |
| Amazon Athena | Análisis agregado del historial de anomalías |

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
- 📸 **Captura UI/UX**: ✅ SUCCEEDED (Phase 8 Theme D, commit 2b958db — redesplegado tras corrección IAM S3AP, 2:59 todos los pasos exitosos)

### Capturas de pantalla existentes (de Phase 1-6)

![UC8 Gráfico Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

![UC8 Step Functions Graph (zoomed)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### Pantallas UI/UX objetivo para re-verificación (lista de capturas recomendadas)

- Bucket S3 de salida (segy-metadata/, anomalies/, reports/)
- Resultados de consulta Athena (estadísticas de metadatos SEG-Y)
- Etiquetas de imagen de registro de pozo Rekognition
- Informe de detección de anomalías

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
