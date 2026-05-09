# Pipeline de preprocesamiento de datos de conducción autónoma -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de preprocesamiento y anotación para datos de sensores de conducción autónoma. Los datos se clasifican automáticamente para generar conjuntos de datos de entrenamiento.

**Mensaje clave**: Preprocesar automáticamente datos de sensores para generar conjuntos de datos anotados listos para entrenamiento IA.

**Duración prevista**: 3–5 min

---

## Workflow

```
Recopilación sensores → Conversión formato → Clasificación frames → Generación anotaciones → Informe dataset
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: El preprocesamiento manual de datos masivos es un cuello de botella

### Section 2 (0:45–1:30)
> Carga: Colocar archivos de logs de sensores inicia el pipeline

### Section 3 (1:30–2:30)
> Preprocesamiento y clasificación: Conversión automática y clasificación IA de frames

### Section 4 (2:30–3:45)
> Resultados de anotación: Verificación de etiquetas generadas y estadísticas de calidad

### Section 5 (3:45–5:00)
> Informe dataset: Informe de preparación para entrenamiento y métricas de calidad

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Python 3.13) | Validación de calidad de datos de sensores, clasificación de escenas, generación de catálogo |
| Lambda SnapStart | Reducción de arranque en frío (`EnableSnapStart=true` opt-in) |
| SageMaker (4-way routing) | Inferencia (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Verdadero scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Clasificación de escenas / sugerencias de anotación |
| Amazon Athena | Búsqueda y agregación de metadatos |
| CloudFormation Guard Hooks | Aplicación de políticas de seguridad en despliegue |

### Prueba local (Phase 6A)

```bash
# Prueba local con SAM CLI
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
