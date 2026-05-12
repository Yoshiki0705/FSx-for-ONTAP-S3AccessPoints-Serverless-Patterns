# Etiquetado de imágenes de productos y generación de metadatos de catálogo — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline de etiquetado automático de imágenes de productos y generación de metadatos de catálogo. Mediante análisis de imágenes con IA, se extraen automáticamente los atributos de productos y se construye un catálogo con capacidad de búsqueda.

**Mensaje central de la demostración**: La IA extrae automáticamente atributos (color, material, categoría, etc.) de las imágenes de productos y genera instantáneamente metadatos de catálogo.

**Duración estimada**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Operador de sitio de comercio electrónico / Administrador de catálogo / Responsable de MD |
| **Tareas diarias** | Registro de productos, gestión de imágenes, actualización de catálogo |
| **Desafío** | La entrada de atributos y el etiquetado de nuevos productos consume mucho tiempo |
| **Resultados esperados** | Automatización del registro de productos y mejora de la capacidad de búsqueda |

### Persona: Yoshida-san (Administrador de catálogo de comercio electrónico)

- Registra más de 200 nuevos productos por semana
- Introduce manualmente más de 10 etiquetas de atributos por cada producto
- "Quiero generar etiquetas automáticamente con solo cargar las imágenes de productos"

---

## Demo Scenario: Registro de lote de nuevos productos

### Visión general del flujo de trabajo

```
Imagen de producto    Análisis de imagen    Extracción de atributos    Actualización de catálogo
(JPEG/PNG)         →   Análisis IA      →   Generación de etiquetas →  Metadatos
                       Detección de objetos  Clasificación de categoría  Registro
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Más de 200 nuevos productos por semana. Introducir manualmente etiquetas de color, material, categoría, estilo, etc. para cada producto es un trabajo enorme. También se producen errores de entrada e inconsistencias.

**Key Visual**: Carpeta de imágenes de productos, pantalla de entrada manual de etiquetas

### Section 2: Image Upload (0:45–1:30)

**Resumen de la narración**:
> Con solo colocar las imágenes de productos en una carpeta, se activa automáticamente el pipeline de etiquetado.

**Key Visual**: Carga de imágenes → Activación automática del flujo de trabajo

### Section 3: AI Analysis (1:30–2:30)

**Resumen de la narración**:
> La IA analiza cada imagen y determina automáticamente la categoría del producto, color, material, patrón y estilo. Extrae múltiples atributos simultáneamente.

**Key Visual**: Procesamiento de análisis de imágenes, resultados de extracción de atributos

### Section 4: Tag Generation (2:30–3:45)

**Resumen de la narración**:
> Los atributos extraídos se convierten en etiquetas estandarizadas. Se garantiza la coherencia con el sistema de etiquetas existente.

**Key Visual**: Lista de etiquetas generadas, distribución por categoría

### Section 5: Catalog Update (3:45–5:00)

**Resumen de la narración**:
> Los metadatos se registran automáticamente en el catálogo. Contribuye a mejorar la capacidad de búsqueda y la precisión de las recomendaciones de productos. Se genera un informe resumen del procesamiento.

**Key Visual**: Resultados de actualización del catálogo, informe resumen de IA

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Carpeta de imágenes de productos | Section 1 |
| 2 | Pantalla de activación del pipeline | Section 2 |
| 3 | Resultados de análisis de imágenes con IA | Section 3 |
| 4 | Lista de resultados de generación de etiquetas | Section 4 |
| 5 | Resumen de actualización del catálogo | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "El etiquetado manual de 200 productos por semana es un trabajo enorme" |
| Upload | 0:45–1:30 | "El etiquetado automático comienza con solo colocar las imágenes" |
| Analysis | 1:30–2:30 | "La IA determina automáticamente color, material y categoría" |
| Tags | 2:30–3:45 | "Generación automática de etiquetas estandarizadas" |
| Catalog | 3:45–5:00 | "Registro automático en el catálogo, mejora la capacidad de búsqueda" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Imágenes de productos de ropa (10 imágenes) | Objetivo principal de procesamiento |
| 2 | Imágenes de productos de muebles (5 imágenes) | Demostración de clasificación de categorías |
| 3 | Imágenes de accesorios (5 imágenes) | Demostración de extracción de múltiples atributos |
| 4 | Maestro de sistema de etiquetas existente | Demostración de estandarización |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de imágenes de productos de muestra | 2 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Búsqueda de productos similares
- Generación automática de descripciones de productos
- Integración con análisis de tendencias

---

## Technical Notes

| Componente | Función |
|--------------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Image Analyzer) | Análisis de imágenes mediante Bedrock/Rekognition |
| Lambda (Tag Generator) | Generación y estandarización de etiquetas de atributos |
| Lambda (Catalog Updater) | Registro de metadatos del catálogo |
| Lambda (Report Generator) | Generación de informe resumen del procesamiento |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Precisión insuficiente del análisis de imágenes | Usar resultados de análisis previo |
| Latencia de Bedrock | Mostrar etiquetas pregeneradas |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Capturas de pantalla de UI/UX verificadas (Verificación AWS 2026-05-10)

Con la misma política que Phase 7, se capturan **pantallas de UI/UX que los responsables de comercio electrónico utilizan realmente en sus tareas diarias**.
Se excluyen las pantallas orientadas a técnicos (gráficos de Step Functions, etc.).

### Selección de destino de salida: S3 estándar vs FSxN S3AP

UC11 soporta el parámetro `OutputDestination` desde la actualización del 2026-05-10.
Al **escribir los resultados de IA de vuelta al mismo volumen FSx**, los usuarios de SMB/NFS pueden
visualizar los JSON de etiquetas generadas automáticamente dentro de la estructura de directorios de imágenes de productos
(patrón "no data movement").

```bash
# Modo STANDARD_S3 (predeterminado, como antes)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# Modo FSXN_S3AP (escribir resultados de IA de vuelta al volumen FSx ONTAP)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

Para las restricciones de especificación de AWS y soluciones alternativas, consulte [la sección "Restricciones de especificación de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策).

### 1. Resultados de etiquetado automático de imágenes de productos

Resultados de análisis de IA que recibe el administrador de comercio electrónico al registrar nuevos productos. Rekognition detectó 7 etiquetas de la imagen real
(`Oval` 99.93%, `Food`, `Furniture`, `Table`, `Sweets`, `Cocoa`, `Dessert`).

<!-- SCREENSHOT: uc11-product-tags.png
     内容: 商品画像 + AI 検出タグ一覧（信頼度つき）
     マスク: アカウント ID、バケット名 -->
![UC11: Etiquetas de productos](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. Bucket de salida S3 — Vista general de resultados de etiquetas y verificación de calidad

Pantalla donde el responsable de operaciones de comercio electrónico verifica los resultados del procesamiento por lotes.
Se generan JSON por producto en 2 prefijos: `tags/` y `quality/`.

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     内容: S3 コンソールで tags/, quality/ プレフィックス
     マスク: アカウント ID -->
![UC11: Bucket de salida S3](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### Valores medidos (Verificación de despliegue AWS 2026-05-10)

- **Ejecución de Step Functions**: SUCCEEDED, procesamiento paralelo de 4 imágenes de productos
- **Rekognition**: Detección de 7 etiquetas en imagen real (confianza máxima 99.93%)
- **JSON generados**: tags/*.json (~750 bytes), quality/*.json (~420 bytes)
- **Stack real**: `fsxn-retail-catalog-demo` (ap-northeast-1, verificación del 2026-05-10)
