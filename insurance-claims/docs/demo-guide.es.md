# Evaluación de daños por foto de accidente e informe de reclamación -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de evaluación de daños basado en fotos de accidentes y generación automática de informes de reclamación.

**Mensaje clave**: La IA analiza automáticamente los daños en fotos de accidentes para generar informes de reclamación al instante.

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
Carga fotos → Detección zonas dañadas → Evaluación gravedad → Estimación costos → Informe reclamación
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: La evaluación manual de daños por foto consume mucho tiempo

### Section 2 (0:45–1:30)
> Carga: Colocar fotos del accidente inicia la evaluación

### Section 3 (1:30–2:30)
> Análisis IA: Detección automática de zonas dañadas y clasificación de gravedad

### Section 4 (2:30–3:45)
> Resultados: Estimación de costos por zona y evaluación global

### Section 5 (3:45–5:00)
> Informe reclamación: Informe generado automáticamente con recomendaciones de procesamiento

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Damage Detector) | Detección IA de zonas dañadas |
| Lambda (Severity Assessor) | Evaluación de gravedad |
| Lambda (Cost Estimator) | Estimación de costos de reparación |
| Amazon Athena | Análisis agregado del historial de reclamaciones |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
