# QC de secuenciación y agregación de variantes -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de control de calidad (QC) y agregación de variantes para datos de secuenciación genómica.

**Mensaje clave**: Validar automáticamente la calidad de datos de secuenciación y agregar variantes para que los investigadores se concentren en el análisis.

**Duración prevista**: 3–5 min

---

## Workflow

```
Carga FASTQ → Validación QC → Llamada variantes → Agregación estadística → Reporte QC
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: El QC manual de grandes volúmenes de datos de secuenciación consume mucho tiempo

### Section 2 (0:45–1:30)
> Carga: Colocar archivos FASTQ inicia el pipeline

### Section 3 (1:30–2:30)
> QC y análisis de variantes: Validación automática de calidad y llamada de variantes

### Section 4 (2:30–3:45)
> Resultados: Métricas QC y estadísticas de variantes

### Section 5 (3:45–5:00)
> Reporte QC: Informe de calidad completo y recomendaciones para análisis posteriores

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (QC Validator) | Validación de calidad de secuenciación |
| Lambda (Variant Caller) | Llamada de variantes |
| Lambda (Stats Aggregator) | Agregación de estadísticas de variantes |
| Amazon Athena | Análisis de métricas QC |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
