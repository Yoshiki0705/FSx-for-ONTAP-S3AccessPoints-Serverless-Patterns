# Flujo de trabajo de anonimización DICOM -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de anonimización automática de archivos DICOM. Se eliminan los datos de identificación del paciente para compartir datos de investigación de forma segura.

**Mensaje clave**: Eliminar automáticamente la información del paciente de archivos DICOM para un intercambio seguro y conforme.

**Duración prevista**: 3–5 min

---

## Destino de salida: FSxN S3 Access Point (Pattern A)

Este UC se clasifica como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: todos los artefactos de IA/ML se escriben a través del FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los datos fuente. No se crea un bucket S3
estándar separado (patrón "no data movement").

**Parámetros CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias de salida (puede ser igual a la entrada)

Para restricciones de especificación de AWS y soluciones alternativas, consulte
[README.es.md — Restricciones de especificación de AWS](../../README.es.md#restricciones-de-especificación-de-aws-y-soluciones-alternativas).

---
## Workflow

```
Carga DICOM → Extracción de metadatos → Detección PHI → Anonimización → Informe de validación
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: El intercambio de datos de investigación requiere cumplimiento normativo

### Section 2 (0:45–1:30)
> Carga: Colocar archivos DICOM inicia el procesamiento automático

### Section 3 (1:30–2:30)
> Detección PHI y anonimización: Detección IA de información personal y enmascaramiento automático

### Section 4 (2:30–3:45)
> Resultados: Verificación de archivos anonimizados y estadísticas de procesamiento

### Section 5 (3:45–5:00)
> Informe de validación: Generación de informe de cumplimiento y aprobación de intercambio

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (DICOM Parser) | Extracción de metadatos DICOM |
| Lambda (PHI Detector) | Detección IA de información personal |
| Lambda (Anonymizer) | Ejecución de anonimización |
| Amazon Athena | Análisis agregado de resultados |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
