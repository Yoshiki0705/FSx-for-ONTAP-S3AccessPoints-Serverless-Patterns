# Procesamiento Automático de Contratos y Facturas — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline automatizado de procesamiento de contratos y facturas. Combina la extracción de texto mediante OCR y la extracción de entidades para generar automáticamente datos estructurados a partir de documentos no estructurados.

**Mensaje central de la demostración**: Digitalizar automáticamente contratos y facturas en papel, y extraer y estructurar instantáneamente información importante como montos, fechas y socios comerciales.

**Duración estimada**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Gerente del Departamento de Contabilidad / Responsable de Gestión de Contratos |
| **Tareas diarias** | Procesamiento de facturas, gestión de contratos, aprobación de pagos |
| **Desafío** | El ingreso manual de grandes volúmenes de documentos en papel consume mucho tiempo |
| **Resultado esperado** | Automatización del procesamiento de documentos y reducción de errores de entrada |

### Persona: Sr. Yamada (Líder del Departamento de Contabilidad)

- Procesa más de 200 facturas mensualmente
- Los errores y retrasos por entrada manual son un desafío
- "Quiero extraer automáticamente el monto y la fecha de vencimiento cuando llega una factura"

---

## Demo Scenario: Procesamiento por lotes de facturas

### Visión general del flujo de trabajo

```
Escaneo de          Procesamiento      Extracción de       Datos
documentos             OCR             entidades y      estructurados
(PDF/imagen)   →   Extracción de  →   clasificación  →  Salida (JSON)
                      texto            (Análisis AI)
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Más de 200 facturas llegan mensualmente. Ingresar manualmente montos, fechas y socios comerciales consume tiempo y genera errores.

**Key Visual**: Lista de numerosos archivos PDF de facturas

### Section 2: Document Upload (0:45–1:30)

**Resumen de la narración**:
> Simplemente colocando los documentos escaneados en el servidor de archivos, el pipeline de procesamiento automático se activa.

**Key Visual**: Carga de archivos → Activación automática del flujo de trabajo

### Section 3: OCR & Extraction (1:30–2:30)

**Resumen de la narración**:
> El OCR extrae el texto y la AI determina el tipo de documento. Clasifica automáticamente facturas, contratos y recibos, y extrae campos importantes de cada documento.

**Key Visual**: Progreso del procesamiento OCR, resultados de clasificación de documentos

### Section 4: Structured Output (2:30–3:45)

**Resumen de la narración**:
> Los resultados de extracción se generan como datos estructurados. Montos, fechas de vencimiento, nombres de socios comerciales, números de factura, etc., están disponibles en formato JSON.

**Key Visual**: Tabla de resultados de extracción (número de factura, monto, fecha de vencimiento, socio comercial)

### Section 5: Validation & Report (3:45–5:00)

**Resumen de la narración**:
> La AI evalúa la confiabilidad de los resultados de extracción y marca elementos de baja confianza. El informe de resumen de procesamiento permite comprender el estado general del procesamiento.

**Key Visual**: Resultados con puntuación de confianza, informe de resumen de procesamiento

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Lista de archivos PDF de facturas | Section 1 |
| 2 | Activación automática del flujo de trabajo | Section 2 |
| 3 | Procesamiento OCR y resultados de clasificación de documentos | Section 3 |
| 4 | Salida de datos estructurados (JSON/tabla) | Section 4 |
| 5 | Informe de resumen de procesamiento | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Procesar manualmente 200 facturas al mes es insostenible" |
| Upload | 0:45–1:30 | "El procesamiento automático comienza solo con colocar el archivo" |
| OCR | 1:30–2:30 | "OCR + AI para clasificación de documentos y extracción de campos" |
| Output | 2:30–3:45 | "Disponible inmediatamente como datos estructurados" |
| Report | 3:45–5:00 | "La evaluación de confianza identifica áreas que requieren verificación humana" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | PDF de facturas (10 archivos) | Objetivo principal de procesamiento |
| 2 | PDF de contratos (3 archivos) | Demostración de clasificación de documentos |
| 3 | Imágenes de recibos (3 archivos) | Demostración de OCR de imágenes |
| 4 | Escaneos de baja calidad (2 archivos) | Demostración de evaluación de confianza |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de documentos de muestra | 3 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Integración automática con sistemas contables
- Integración de flujo de trabajo de aprobación
- Soporte de documentos multilingües (inglés, chino)

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (OCR Processor) | Extracción de texto de documentos mediante Textract |
| Lambda (Entity Extractor) | Extracción de entidades mediante Bedrock |
| Lambda (Classifier) | Clasificación de tipo de documento |
| Amazon Athena | Análisis agregado de datos extraídos |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Baja precisión de OCR | Usar texto preprocesado |
| Latencia de Bedrock | Mostrar resultados pregenerados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: FSxN S3 Access Point (Pattern A)

UC2 financial-idp está clasificado como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: Los resultados de OCR de facturas, metadatos estructurados y resúmenes de BedRock se escriben todos a través del FSxN S3 Access Point
en el **mismo volumen FSx ONTAP** que los PDF de facturas originales. No se
crean buckets S3 estándar (patrón "no data movement").

**Parámetros de CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias para lectura de datos de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias para escritura de salida (puede ser el mismo que el de entrada)

**Ejemplo de despliegue**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (otros parámetros obligatorios)
```

**Vista desde usuarios SMB/NFS**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # Factura original
  └── summaries/2026/05/                # Resumen generado por AI (dentro del mismo volumen)
      └── invoice_001.json
```

Para las limitaciones de las especificaciones de AWS, consulte
[la sección "Limitaciones de las especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Capturas de pantalla de UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas de UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráfico de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ⚠️ **Verificación E2E**: Solo funciones parciales (se recomienda verificación adicional en entorno de producción)
- 📸 **Captura de UI/UX**: ✅ SFN Graph completado (Phase 8 Theme D, commit 081cc66)

### Capturado en la verificación de redespliegue del 2026-05-10 (centrado en UI/UX)

#### Vista de gráfico de Step Functions de UC2 (SUCCEEDED)

![Vista de gráfico de Step Functions de UC2 (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

La vista de gráfico de Step Functions es la pantalla más importante para el usuario final, que visualiza con colores el estado de ejecución de cada estado Lambda / Parallel / Map.

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

![Vista de gráfico de Step Functions de UC2 (SUCCEEDED)](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### Pantallas de UI/UX objetivo durante la reverificación (lista de capturas recomendadas)

- Bucket de salida S3 (textract-results/, comprehend-entities/, reports/)
- JSON de resultados de OCR de Textract (campos extraídos de contratos y facturas)
- Resultados de detección de entidades de Comprehend (nombres de organizaciones, fechas, montos)
- Informe de resumen generado por Bedrock

### Guía de captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=financial-idp bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC2`

2. **Colocación de datos de muestra**:
   - Cargar archivos de muestra al prefijo `invoices/` a través del S3 AP Alias
   - Iniciar Step Functions `fsxn-financial-idp-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-financial-idp-demo-output-<account>`
   - Vista previa de JSON de salida de AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo electrónico de SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py financial-idp-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC2`
   - Liberación de ENI de Lambda en VPC toma 15-30 minutos (especificación de AWS)
