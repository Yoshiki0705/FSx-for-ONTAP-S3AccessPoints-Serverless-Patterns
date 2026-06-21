# Secuenciación QC・Agregación de variantes — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración ilustra un pipeline de control de calidad y agregación de variantes para datos de secuenciación de próxima generación (NGS). Valida automáticamente la calidad de la secuenciación y agrega y genera informes de los resultados de llamado de variantes.

**Mensaje central de la demostración**: Automatizar el QC de datos de secuenciación y generar instantáneamente informes de agregación de variantes. Garantizar la confiabilidad del análisis.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Ítem | Detalle |
|------|---------|
| **Cargo** | Bioinformático / Investigador de análisis genómico |
| **Tareas diarias** | QC de datos de secuenciación, llamado de variantes, interpretación de resultados |
| **Desafío** | Verificar manualmente el QC de grandes volúmenes de muestras consume mucho tiempo |
| **Resultado esperado** | Automatización del QC y eficiencia en la agregación de variantes |

### Persona: Kato-san (Bioinformático)

- Procesa datos de secuenciación de más de 100 muestras por semana
- Necesita detección temprana de muestras que no cumplen los criterios de QC
- "Quiero enviar automáticamente solo las muestras que pasan el QC al análisis downstream"

---

## Demo Scenario: QC de lote de secuenciación

### Visión general del flujo de trabajo

```
Archivos FASTQ/BAM    Análisis QC    Evaluación de calidad    Agregación de variantes
(100+ muestras)    →  Cálculo de   →  Filtro Pass/Fail    →   Generación de informes
                      métricas
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de narración**:
> Más de 100 muestras de datos de secuenciación por semana. Si muestras de baja calidad se mezclan en el análisis downstream, la confiabilidad de los resultados completos disminuye.

**Key Visual**: Lista de archivos de datos de secuenciación

### Section 2: Pipeline Trigger (0:45–1:30)

**Resumen de narración**:
> Después de completar la ejecución de secuenciación, el pipeline de QC se inicia automáticamente. Todas las muestras se procesan en paralelo.

**Key Visual**: Inicio del flujo de trabajo, lista de muestras

### Section 3: QC Metrics (1:30–2:30)

**Resumen de narración**:
> Cálculo de métricas de QC para cada muestra: número de lecturas, tasa Q30, tasa de mapeo, profundidad de cobertura, tasa de duplicación.

**Key Visual**: Procesamiento de cálculo de métricas de QC, lista de métricas

### Section 4: Quality Filtering (2:30–3:45)

**Resumen de narración**:
> Evaluación Pass/Fail basada en criterios de QC. Clasificación de causas de muestras Fail (lecturas de baja calidad, baja cobertura, etc.).

**Key Visual**: Resultados de evaluación Pass/Fail, clasificación de causas Fail

### Section 5: Variant Summary (3:45–5:00)

**Resumen de narración**:
> Agregación de resultados de llamado de variantes de muestras que pasan el QC. Comparación entre muestras, distribución de variantes, generación de informe de resumen con IA.

**Key Visual**: Informe de agregación de variantes (resumen estadístico + interpretación con IA)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|----------|---------|
| 1 | Lista de datos de secuenciación | Section 1 |
| 2 | Pantalla de inicio del pipeline | Section 2 |
| 3 | Resultados de métricas de QC | Section 3 |
| 4 | Resultados de evaluación Pass/Fail | Section 4 |
| 5 | Informe de agregación de variantes | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|---------|--------|---------------|
| Problem | 0:00–0:45 | "La mezcla de muestras de baja calidad compromete la confiabilidad del análisis completo" |
| Trigger | 0:45–1:30 | "El QC comienza automáticamente al completar la ejecución" |
| Metrics | 1:30–2:30 | "Cálculo de métricas de QC principales para todas las muestras" |
| Filtering | 2:30–3:45 | "Evaluación automática Pass/Fail basada en criterios" |
| Summary | 3:45–5:00 | "Generación instantánea de agregación de variantes y resumen con IA" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|-------|-----|
| 1 | Métricas FASTQ de alta calidad (20 muestras) | Línea base |
| 2 | Muestras de baja calidad (Q30 < 80%, 3 casos) | Demostración de detección Fail |
| 3 | Muestras de baja cobertura (2 casos) | Demostración de clasificación |
| 4 | Resultados de llamado de variantes (resumen VCF) | Demostración de agregación |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|-------|------------------|
| Preparación de datos de QC de muestras | 3 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Monitoreo de secuenciación en tiempo real
- Generación automática de informes clínicos
- Análisis integrado multiómico

---

## Technical Notes

| Componente | Rol |
|------------|-----|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (QC Calculator) | Cálculo de métricas de QC de secuenciación |
| Lambda (Quality Filter) | Evaluación y clasificación Pass/Fail |
| Lambda (Variant Aggregator) | Agregación de variantes |
| Lambda (Report Generator) | Generación de informe de resumen mediante Bedrock |

### Fallback

| Escenario | Respuesta |
|-----------|-----------|
| Retraso en procesamiento de datos de gran volumen | Ejecutar con subconjunto |
| Retraso de Bedrock | Mostrar informe pregenerado |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Capturas de pantalla UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráficos de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (ver README raíz)
- 📸 **Recaptura UI/UX**: ✅ Capturado en verificación de redespliegue 2026-05-10 (confirmado gráfico de Step Functions UC7, ejecución exitosa de Lambda)
- 📸 **Captura UI/UX (Phase 8 Theme D)**: ✅ Captura SUCCEEDED completada (commit 2b958db — redesplegado después de corrección IAM S3AP, todos los pasos exitosos en 3:03)
- 🔄 **Método de reproducción**: Consultar "Guía de captura" al final de este documento

### Capturado en verificación de redespliegue 2026-05-10 (centrado en UI/UX)

#### UC7 Step Functions Graph view (SUCCEEDED)

![UC7 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para el usuario final que visualiza el estado de ejecución de cada Lambda / Parallel / Map state mediante colores.

#### UC7 Step Functions Graph (SUCCEEDED — Recaptura Phase 8 Theme D)

![UC7 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

Redesplegado después de corrección IAM S3AP. Todos los pasos SUCCEEDED (3:03).

#### UC7 Step Functions Graph (Vista ampliada — Detalle de cada paso)

![UC7 Step Functions Graph (Vista ampliada)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

#### UC7 Resultados de análisis genómico de Comprehend Medical (Cross-Region us-east-1)

![UC7 Resultados de análisis genómico de Comprehend Medical (Cross-Region us-east-1)](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### Pantallas UI/UX objetivo durante reverificación (lista de captura recomendada)

- Bucket de salida S3 (fastq-qc/, variant-summary/, entities/)
- Resultados de consulta Athena (agregación de frecuencia de variantes)
- Entidades médicas de Comprehend Medical (Genes, Diseases, Mutations)
- Informe de investigación generado por Bedrock

### Guía de captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (existencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=genomics-pipeline bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC7`

2. **Colocación de datos de muestra**:
   - Subir archivos de muestra al prefijo `fastq/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-genomics-pipeline-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-genomics-pipeline-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo electrónico SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py genomics-pipeline-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC7`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
