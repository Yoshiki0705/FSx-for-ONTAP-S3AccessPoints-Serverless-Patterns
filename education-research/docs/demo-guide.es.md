# Clasificación de publicaciones y análisis de red de citas -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de clasificación automática de publicaciones y análisis de red de citas. Las publicaciones se clasifican por tema y se visualizan las relaciones de citación.

**Mensaje clave**: Clasificar automáticamente publicaciones con IA y analizar la red de citas para identificar tendencias de investigación al instante.

**Duración prevista**: 3–5 min

---

## Workflow

```
Carga publicaciones → Extracción metadatos → Clasificación IA → Construcción red citas → Informe análisis
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: Clasificar manualmente miles de publicaciones es poco realista

### Section 2 (0:45–1:30)
> Carga: Colocar archivos PDF inicia el pipeline de análisis

### Section 3 (1:30–2:30)
> Clasificación IA y construcción de red: Clasificación temática y extracción de citas

### Section 4 (2:30–3:45)
> Resultados: Clusters temáticos e identificación de publicaciones clave

### Section 5 (3:45–5:00)
> Informe de tendencias: Análisis de tendencias por área y lista de publicaciones recomendadas

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (PDF Parser) | Extracción de metadatos de publicaciones |
| Lambda (Topic Classifier) | Clasificación IA temática |
| Lambda (Citation Analyzer) | Construcción de red de citas |
| Amazon Athena | Análisis agregado de tendencias |

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

- Bucket S3 de salida (papers-ocr/, citations/, reports/)
- Resultados OCR Textract de artículos (Cross-Region)
- Detección de entidades Comprehend (autores, citas, palabras clave)
- Informe de análisis de red de investigación

### Guía de captura

1. **Preparación**: Ejecutar `bash scripts/verify_phase7_prerequisites.sh` para verificar prerrequisitos
2. **Datos de ejemplo**: Subir archivos vía S3 AP Alias, luego iniciar el workflow de Step Functions
3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la esquina superior derecha del navegador)
4. **Enmascaramiento**: Ejecutar `python3 scripts/mask_uc_demos.py <uc-dir>` para enmascaramiento OCR automático
5. **Limpieza**: Ejecutar `bash scripts/cleanup_generic_ucs.sh <UC>` para eliminar la pila
