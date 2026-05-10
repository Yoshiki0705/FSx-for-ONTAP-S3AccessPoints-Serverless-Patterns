# Auditoría de permisos del servidor de archivos — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo muestra un flujo de auditoría automatizado que detecta permisos excesivos en servidores de archivos. Analiza ACL NTFS y genera informes de cumplimiento.

**Mensaje clave**: Automatizar auditorías de permisos que tomarían semanas, visualizando riesgos instantáneamente.

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



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Planteamiento: Auditoría manual de miles de carpetas es poco realista

### Section 2 (0:45–1:30)
> Activación: Especificar volumen objetivo e iniciar auditoría

### Section 3 (1:30–2:30)
> Análisis ACL: Recopilar ACL y detectar violaciones

### Section 4 (2:30–3:45)
> Revisión de resultados: Captar violaciones y niveles de riesgo

### Section 5 (3:45–5:00)
> Informe de cumplimiento: Generar informe con acciones priorizadas

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo |
| Lambda (ACL Collector) | Recopilación metadatos ACL NTFS |
| Lambda (Policy Checker) | Coincidencia reglas de violación |
| Lambda (Report Generator) | Generación informe vía Bedrock |
| Amazon Athena | Análisis SQL de violaciones |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
