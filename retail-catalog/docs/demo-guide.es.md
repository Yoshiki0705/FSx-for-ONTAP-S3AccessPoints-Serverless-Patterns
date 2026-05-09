# Etiquetado de imágenes de producto y generación de metadatos de catálogo -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de etiquetado automático de imágenes de producto y generación de metadatos de catálogo. La IA analiza fotos de productos para generar etiquetas y descripciones.

**Mensaje clave**: La IA extrae automáticamente atributos de imágenes de productos para generar metadatos de catálogo al instante y acelerar el registro de productos.

**Duración prevista**: 3–5 min

---

## Workflow

```
Carga imágenes → Análisis visual → Etiquetado atributos → Generación descripciones → Informe catálogo
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: El etiquetado manual de miles de productos es un cuello de botella

### Section 2 (0:45–1:30)
> Carga: Colocar fotos de productos inicia el procesamiento

### Section 3 (1:30–2:30)
> Análisis IA y etiquetado: Extracción automática de color, material, categoría por visión IA

### Section 4 (2:30–3:45)
> Generación metadatos: Descripciones de producto y palabras clave de búsqueda automáticas

### Section 5 (3:45–5:00)
> Informe catálogo: Estadísticas de procesamiento y resultados de validación de calidad

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Image Analyzer) | Análisis visual IA |
| Lambda (Tag Generator) | Generación de etiquetas de atributos |
| Lambda (Description Writer) | Redacción automática de descripciones |
| Amazon Athena | Análisis estadístico de catálogo |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
