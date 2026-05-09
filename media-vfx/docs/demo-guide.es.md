# Control de calidad de renderizado VFX -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo muestra un pipeline de control de calidad para salidas de renderizado VFX. La verificación automática de frames permite detección temprana de artefactos.

**Mensaje clave**: Verificar automáticamente grandes volúmenes de frames renderizados, detectando problemas de calidad instantáneamente.

**Duración prevista**: 3-5 min

---

## Workflow

```
Salida renderizado (EXR/PNG) -> Análisis frames / Extracción metadatos -> Evaluación calidad -> Informe QC (por toma)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Planteamiento: Inspección visual de miles de frames es poco realista

### Section 2 (0:45-1:30)
> Activación: Finalización de render inicia QC automáticamente

### Section 3 (1:30-2:30)
> Análisis: Estadísticas de píxeles evalúan calidad cuantitativamente

### Section 4 (2:30-3:45)
> Evaluación: Clasificación automática de frames problemáticos

### Section 5 (3:45-5:00)
> Informe QC: Soporte inmediato para decisiones de re-renderizado

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo |
| Lambda (Frame Analyzer) | Extracción metadatos/estadísticas píxeles |
| Lambda (Quality Checker) | Evaluación estadística calidad |
| Lambda (Report Generator) | Generación informe QC vía Bedrock |
| Amazon Athena | Análisis agregado estadísticas frames |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
