# Guía de evaluación de impacto en entornos existentes

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## Descripción general

Este documento evalúa el impacto en los entornos existentes al habilitar las funcionalidades de cada Phase, y proporciona procedimientos de habilitación seguros y métodos de rollback.

> **Alcance**: Phase 1–5 (este documento se actualizará al agregar nuevas fases)

Principios de diseño:
- **Phase 1 (UC1–UC5)**: Pilas CloudFormation independientes. Impacto limitado a creación de ENI
- **Phase 2 (UC6–UC14)**: Pilas independientes + llamadas API entre regiones
- **Phase 3 (Mejoras transversales)**: Extensiones de UCs existentes. Opt-in (deshabilitado por defecto)
- **Phase 4 (SageMaker producción, Multi-cuenta, Event-Driven)**: Extensiones UC9 + nuevas plantillas. Opt-in
- **Phase 5 (Serverless Inference, Costos, CI/CD, Multi-Region)**: Opt-in (deshabilitado por defecto)

---

## Phase 1–2: UCs base y extendidos

| Parámetro | Defecto | Impacto |
|-----------|---------|---------|
| EnableS3GatewayEndpoint | "true" | ⚠️ Conflicto con S3 Gateway EP existente |
| EnableVpcEndpoints | "false" | Creación de Interface VPC Endpoints |
| CrossRegion | "us-east-1" | Llamadas API entre regiones (latencia 50–200ms) |
| MapConcurrency | 10 | Afecta cuota de concurrencia Lambda |

## Phase 3: Mejoras transversales

| Parámetro | Defecto | Impacto |
|-----------|---------|---------|
| EnableStreamingMode | "false" | Nuevos recursos UC11 (polling no afectado) |
| EnableSageMakerTransform | "false" | ⚠️ Agrega ruta SageMaker al workflow UC9 |
| EnableXRayTracing | "true" | ⚠️ Transmisión de trazas X-Ray |

## Phase 4: Extensiones de producción

| Parámetro | Defecto | Impacto |
|-----------|---------|---------|
| EnableRealtimeEndpoint | "false" | ⚠️ Costo permanente (~$166/mes) |
| EnableDynamoDBTokenStore | "false" | Nueva tabla DynamoDB |

## Phase 5: Serverless Inference, Costos, CI/CD, Multi-Region

| Parámetro | Defecto | Impacto |
|-----------|---------|---------|
| InferenceType | "none" | "serverless" modifica enrutamiento |
| EnableScheduledScaling | "false" | ⚠️ Modifica escalado de endpoints existentes |
| EnableAutoStop | "false" | ⚠️ Detiene endpoints inactivos |
| EnableMultiRegion | "false" | ⚠️ **Irreversible** — DynamoDB Global Table |

---

## Orden de habilitación recomendado

| Orden | Funcionalidad | Phase | Riesgo |
|-------|--------------|-------|--------|
| 1 | Despliegue UC1 | 1 | Bajo |
| 2 | Observabilidad | 3 | Bajo |
| 3 | CI/CD | 5 | Ninguno |
| 4–6 | Streaming / SageMaker / Serverless | 3–5 | Bajo |
| 7–8 | Real-time / Scaling | 4–5 | Medio ⚠️ |
| 9 | Multi-Region | 5 | Alto ⚠️ **Irreversible** |

---

*Este documento es la guía de evaluación de impacto en entornos existentes para FSxN S3AP Serverless Patterns.*
