# Detección de anomalías IoT e inspección de calidad -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo muestra un flujo que detecta automáticamente anomalías en datos de sensores IoT de líneas de fabricación y genera informes de calidad.

**Mensaje clave**: Detectar automáticamente patrones anómalos en datos de sensores para detección temprana de problemas de calidad.

**Duración prevista**: 3-5 min

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
