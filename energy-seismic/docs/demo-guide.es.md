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
