# Evaluación de Daños por Fotografías de Accidentes e Informe de Indemnización de Seguros — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline automatizado de evaluación de daños y generación de informes de reclamaciones de seguros a partir de fotografías de accidentes. Mediante análisis de imágenes con IA y generación automática de informes, se optimiza el proceso de evaluación.

**Mensaje central de la demostración**: La IA analiza automáticamente fotografías de accidentes, evalúa el grado de daño y genera instantáneamente informes de reclamaciones de seguros.

**Duración estimada**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Responsable de evaluación de daños / Ajustador de reclamaciones |
| **Tareas diarias** | Verificación de fotografías de accidentes, evaluación de daños, cálculo de indemnizaciones, creación de informes |
| **Desafío** | Necesidad de procesar rápidamente un gran volumen de casos de reclamación |
| **Resultados esperados** | Agilización del proceso de evaluación y garantía de consistencia |

### Persona: Sr. Kobayashi (Responsable de evaluación de daños)

- Procesa más de 100 reclamaciones de seguros al mes
- Evalúa el grado de daño a partir de fotografías y crea informes
- "Quiero automatizar la evaluación inicial para concentrarme en casos complejos"

---

## Demo Scenario: Evaluación de daños en accidentes automovilísticos

### Visión general del flujo de trabajo

```
Fotografías         Análisis de        Evaluación          Informe de
de accidente    →   imágenes      →    de daños       →    reclamación
(múltiples)         Detección           Determinación       Generado por IA
                    de daños            de grado
                    Identificación      Estimación
                    de partes           de costos
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Más de 100 reclamaciones de seguros al mes. En cada caso se deben verificar múltiples fotografías de accidentes, evaluar el grado de daño y crear informes. El procesamiento manual no puede seguir el ritmo.

**Key Visual**: Lista de casos de reclamaciones de seguros, muestras de fotografías de accidentes

### Section 2: Photo Upload (0:45–1:30)

**Resumen de la narración**:
> Cuando se cargan fotografías de accidentes, se activa automáticamente el pipeline de evaluación. Procesamiento por caso.

**Key Visual**: Carga de fotografías → Activación automática del flujo de trabajo

### Section 3: Damage Detection (1:30–2:30)

**Resumen de la narración**:
> La IA analiza las fotografías y detecta áreas dañadas. Identifica el tipo de daño (abolladuras, rasguños, roturas) y la parte afectada (parachoques, puerta, guardabarros, etc.).

**Key Visual**: Resultados de detección de daños, mapeo de partes

### Section 4: Assessment (2:30–3:45)

**Resumen de la narración**:
> Evalúa el grado de daño, determina si requiere reparación/reemplazo y calcula el costo estimado. También compara con casos similares anteriores.

**Key Visual**: Tabla de resultados de evaluación de daños, estimación de costos

### Section 5: Claims Report (3:45–5:00)

**Resumen de la narración**:
> La IA genera automáticamente el informe de reclamación de seguros. Incluye resumen de daños, costo estimado y acciones recomendadas. El evaluador solo necesita revisar y aprobar.

**Key Visual**: Informe de reclamación generado por IA (resumen de daños + estimación de costos)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Lista de casos de reclamación | Section 1 |
| 2 | Carga de fotografías y activación del pipeline | Section 2 |
| 3 | Resultados de detección de daños | Section 3 |
| 4 | Evaluación de daños y estimación de costos | Section 4 |
| 5 | Informe de reclamación de seguros | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Evaluar manualmente 100 reclamaciones al mes es insostenible" |
| Upload | 0:45–1:30 | "La carga de fotografías inicia la evaluación automática" |
| Detection | 1:30–2:30 | "La IA detecta automáticamente áreas y tipos de daño" |
| Assessment | 2:30–3:45 | "Estimación automática del grado de daño y costo de reparación" |
| Report | 3:45–5:00 | "Generación automática del informe de reclamación, solo requiere revisión y aprobación" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Fotografías de daños leves (5 casos) | Demostración de evaluación básica |
| 2 | Fotografías de daños moderados (3 casos) | Demostración de precisión de evaluación |
| 3 | Fotografías de daños graves (2 casos) | Demostración de determinación de pérdida total |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de datos de fotografías de muestra | 2 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Detección de daños a partir de videos
- Cotejo automático con presupuestos de talleres de reparación
- Detección de reclamaciones fraudulentas

---

## Technical Notes

| Componente | Función |
|--------------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Image Analyzer) | Detección de daños mediante Bedrock/Rekognition |
| Lambda (Damage Assessor) | Evaluación del grado de daño y estimación de costos |
| Lambda (Report Generator) | Generación de informes de reclamación mediante Bedrock |
| Amazon Athena | Consulta y comparación de datos de casos anteriores |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Precisión insuficiente del análisis de imágenes | Usar resultados pre-analizados |
| Latencia de Bedrock | Mostrar informes pre-generados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Capturas de pantalla UI/UX verificadas (Verificación AWS 2026-05-10)

Siguiendo la misma política que Phase 7, se capturan **pantallas UI/UX que los responsables de evaluación de seguros utilizan realmente en sus tareas diarias**.
Se excluyen pantallas orientadas a técnicos (gráficos de Step Functions, etc.).

### Selección de destino de salida: S3 estándar vs FSxN S3AP

UC14 soporta el parámetro `OutputDestination` desde la actualización del 2026-05-10.
**Al escribir los resultados de IA de vuelta al mismo volumen FSx**, los responsables de procesamiento de reclamaciones
pueden ver el JSON de evaluación de daños, resultados OCR e informes de reclamación dentro de la estructura de directorios del caso de reclamación
(patrón "no data movement", también ventajoso desde la perspectiva de protección de PII).

```bash
# Modo STANDARD_S3 (predeterminado, como antes)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# Modo FSXN_S3AP (escribir resultados de IA de vuelta al volumen FSx ONTAP)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

Para restricciones de especificación AWS y soluciones alternativas, consulte [la sección "Restricciones de especificación AWS y soluciones alternativas"
del README del proyecto](../../README.md#aws-仕様上の制約と回避策).

### 1. Informe de reclamación de seguros — Resumen para evaluadores

Informe integrado de análisis Rekognition de fotografías de accidentes + OCR Textract de presupuestos + determinación de evaluación recomendada.
Con determinación `MANUAL_REVIEW` + confianza 75%, el evaluador revisa elementos que no pueden automatizarse.

<!-- SCREENSHOT: uc14-claims-report.png
     内容: 保険金請求レポート（請求 ID、損害サマリー、見積相関、推奨判定）
            + Rekognition 検出ラベル一覧 + Textract OCR 結果
     マスク: アカウント ID、バケット名 -->
![UC14: Informe de reclamación de seguros](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. Bucket S3 de salida — Vista general de artefactos de evaluación

Pantalla donde los evaluadores verifican artefactos por caso de reclamación.
`assessments/` (análisis Rekognition) + `estimates/` (OCR Textract) + `reports/` (informe integrado).

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     内容: S3 コンソールで assessments/, estimates/, reports/ プレフィックス
     マスク: アカウント ID -->
![UC14: Bucket S3 de salida](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### Valores medidos (Verificación de despliegue AWS 2026-05-10)

- **Ejecución de Step Functions**: SUCCEEDED
- **Rekognition**: Detectó `Maroon` 90.79%, `Business Card` 84.51%, etc. en fotografías de accidentes
- **Textract**: OCR de PDF de presupuesto vía cross-region us-east-1, extrayendo `Total: 1270.00 USD`, etc.
- **Artefactos generados**: assessments/*.json, estimates/*.json, reports/*.txt
- **Stack real**: `fsxn-insurance-claims-demo` (ap-northeast-1, verificación 2026-05-10)
