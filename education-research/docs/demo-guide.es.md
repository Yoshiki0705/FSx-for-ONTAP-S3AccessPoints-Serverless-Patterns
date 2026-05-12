# Análisis de clasificación de artículos y red de citas — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline de clasificación automática de artículos académicos y análisis de redes de citación. Extrae metadatos de grandes volúmenes de PDFs de artículos y visualiza tendencias de investigación.

**Mensaje central de la demostración**: Al clasificar automáticamente colecciones de artículos y analizar relaciones de citación, se obtiene instantáneamente una visión general del campo de investigación y se identifican los artículos clave.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Rol** | Investigador / Especialista en biblioteconomía / Administrador de investigación |
| **Tareas diarias** | Revisión bibliográfica, análisis de tendencias de investigación, gestión de artículos |
| **Desafío** | No puede descubrir eficientemente investigaciones relacionadas de grandes volúmenes de artículos |
| **Resultado esperado** | Mapeo del campo de investigación e identificación automática de artículos clave |

### Persona: Sr. Watanabe (Investigador)

- Realizando revisión bibliográfica de un nuevo tema de investigación
- Ha recopilado PDFs de más de 500 artículos, pero no puede captar la visión general
- "Quiero clasificar automáticamente por campo e identificar artículos importantes con muchas citaciones"

---

## Demo Scenario: Análisis automático de colección bibliográfica

### Visión general del flujo de trabajo

```
PDFs de artículos    Extracción de metadatos    Clasificación/Análisis    Informe de visualización
(500+ documentos) →  Título/Autor           →   Clasificación por tema →  Red
                     Información de citación    Análisis de citación      Generación de mapa
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de narración**:
> Se han recopilado más de 500 PDFs de artículos. Se desea comprender la distribución por campo, artículos importantes y tendencias de investigación, pero es imposible leerlos todos.

**Key Visual**: Lista de archivos PDF de artículos (gran volumen)

### Section 2: Metadata Extraction (0:45–1:30)

**Resumen de narración**:
> Extracción automática de título, autor, resumen y lista de citaciones de cada PDF de artículo.

**Key Visual**: Procesamiento de extracción de metadatos, muestra de resultados extraídos

### Section 3: Classification (1:30–2:30)

**Resumen de narración**:
> La IA analiza los resúmenes y clasifica automáticamente los temas de investigación. El clustering forma grupos de artículos relacionados.

**Key Visual**: Resultados de clasificación por tema, número de artículos por categoría

### Section 4: Citation Analysis (2:30–3:45)

**Resumen de narración**:
> Analiza las relaciones de citación e identifica artículos importantes con alto número de citas. Analiza la estructura de la red de citación.

**Key Visual**: Estadísticas de red de citación, ranking de artículos importantes

### Section 5: Research Map (3:45–5:00)

**Resumen de narración**:
> La IA genera una visión general del campo de investigación como informe resumen. Presenta tendencias, brechas y direcciones futuras de investigación.

**Key Visual**: Informe de mapa de investigación (análisis de tendencias + bibliografía recomendada)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Colección de PDFs de artículos | Section 1 |
| 2 | Resultados de extracción de metadatos | Section 2 |
| 3 | Resultados de clasificación por tema | Section 3 |
| 4 | Estadísticas de red de citación | Section 4 |
| 5 | Informe de mapa de investigación | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Quiero comprender la visión general de 500 artículos" |
| Extraction | 0:45–1:30 | "Extracción automática de metadatos de PDFs" |
| Classification | 1:30–2:30 | "La IA clasifica automáticamente por tema" |
| Citation | 2:30–3:45 | "Identificación de artículos importantes mediante red de citación" |
| Map | 3:45–5:00 | "Visualización de la visión general y tendencias del campo de investigación" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | PDFs de artículos (30 documentos, 3 campos) | Objeto principal de procesamiento |
| 2 | Datos de relaciones de citación (con citación mutua) | Demostración de análisis de red |
| 3 | Artículos altamente citados (5 documentos) | Demostración de identificación de artículos importantes |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de datos de artículos de muestra | 3 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Visualización interactiva de red de citación
- Sistema de recomendación de artículos
- Clasificación automática periódica de nuevos artículos

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (PDF Parser) | Extracción de metadatos de PDFs de artículos |
| Lambda (Classifier) | Clasificación por tema mediante Bedrock |
| Lambda (Citation Analyzer) | Construcción y análisis de red de citación |
| Amazon Athena | Agregación y búsqueda de metadatos |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Fallo en análisis de PDF | Usar datos pre-extraídos |
| Precisión de clasificación insuficiente | Mostrar resultados pre-clasificados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Capturas de pantalla verificadas de UI/UX

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas de UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráficos de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (ver README raíz)
- 📸 **Re-captura de UI/UX**: ✅ Capturado en verificación de re-despliegue 2026-05-10 (confirmado gráfico de Step Functions UC13, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consultar "Guía de captura" al final de este documento

### Capturado en verificación de re-despliegue 2026-05-10 (centrado en UI/UX)

#### UC13 Step Functions Graph view (SUCCEEDED)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para el usuario final que visualiza
el estado de ejecución de cada Lambda / Parallel / Map state mediante colores.

### Capturas de pantalla existentes (correspondientes de Phase 1-6)

![UC13 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions Graph (vista general completa)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions Graph (vista ampliada — detalle de cada paso)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### Pantallas de UI/UX objetivo en re-verificación (lista de captura recomendada)

- Bucket de salida S3 (papers-ocr/, citations/, reports/)
- Resultados de OCR de artículos Textract (Cross-Region)
- Detección de entidades Comprehend (autor, citación, palabras clave)
- Informe de análisis de red de investigación

### Guía de captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=education-research bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC13`

2. **Colocación de datos de muestra**:
   - Subir archivos de muestra al prefijo `papers/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-education-research-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-education-research-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py education-research-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC13`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
