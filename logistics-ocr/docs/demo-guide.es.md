# Guía de Demostración — OCR de Albaranes de Entrega y Análisis de Inventario

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline de procesamiento OCR de albaranes de envío y análisis de inventario. Digitaliza albaranes en papel y agrega/analiza automáticamente los datos de entrada y salida de almacén.

**Mensaje central de la demostración**: Digitalizar automáticamente los albaranes de envío para facilitar la comprensión en tiempo real del estado del inventario y la previsión de la demanda.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Gerente de logística / Administrador de almacén |
| **Tareas diarias** | Gestión de entradas/salidas, verificación de inventario, coordinación de envíos |
| **Desafíos** | Retrasos y errores por entrada manual de albaranes en papel |
| **Resultados esperados** | Automatización del procesamiento de albaranes y visualización del inventario |

### Persona: Sr. Saito (Gerente de logística)

- Procesa más de 500 albaranes de envío al día
- La información de inventario siempre está retrasada debido al desfase temporal de la entrada manual
- "Quiero que el inventario se actualice simplemente escaneando los albaranes"

---

## Demo Scenario: Procesamiento por lotes de albaranes de envío

### Visión general del flujo de trabajo

```
Albarán de envío    Procesamiento OCR    Estructuración      Análisis de
(imagen escaneada) → Extracción de texto → de datos      →   inventario
                                          Mapeo de campos    Informe agregado
                                                            Previsión de demanda
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Más de 500 albaranes de envío al día. Con la entrada manual, la actualización de la información de inventario se retrasa, aumentando el riesgo de desabastecimiento o exceso de inventario.

**Key Visual**: Imágenes de escaneo masivo de albaranes, imagen de retraso en entrada manual

### Section 2: Scan & Upload (0:45–1:30)

**Resumen de la narración**:
> Simplemente colocando las imágenes de albaranes escaneados en una carpeta, el pipeline OCR se inicia automáticamente.

**Key Visual**: Carga de imágenes de albaranes → Inicio del flujo de trabajo

### Section 3: OCR Processing (1:30–2:30)

**Resumen de la narración**:
> El OCR extrae el texto de los albaranes y la IA mapea automáticamente campos como nombre del producto, cantidad, destino, fecha, etc.

**Key Visual**: Procesamiento OCR en curso, resultados de extracción de campos

### Section 4: Inventory Analysis (2:30–3:45)

**Resumen de la narración**:
> Los datos extraídos se cotejan con la base de datos de inventario. Las entradas y salidas se agregan automáticamente y se actualiza el estado del inventario.

**Key Visual**: Resultados de agregación de inventario, tendencias de entrada/salida por artículo

### Section 5: Demand Report (3:45–5:00)

**Resumen de la narración**:
> La IA genera un informe de análisis de inventario. Presenta la tasa de rotación de inventario, artículos con riesgo de desabastecimiento y recomendaciones de pedido.

**Key Visual**: Informe de inventario generado por IA (resumen de inventario + recomendaciones de pedido)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Lista de imágenes escaneadas de albaranes | Section 1 |
| 2 | Carga e inicio del pipeline | Section 2 |
| 3 | Resultados de extracción OCR | Section 3 |
| 4 | Panel de agregación de inventario | Section 4 |
| 5 | Informe de análisis de inventario por IA | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "La información de inventario siempre está desactualizada debido al retraso en la entrada manual" |
| Upload | 0:45–1:30 | "El procesamiento automático comienza simplemente colocando el escaneo" |
| OCR | 1:30–2:30 | "La IA reconoce y estructura automáticamente los campos del albarán" |
| Analysis | 2:30–3:45 | "Agrega automáticamente entradas/salidas y actualiza el inventario de inmediato" |
| Report | 3:45–5:00 | "La IA presenta riesgos de desabastecimiento y recomendaciones de pedido" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Imágenes de albaranes de entrada (10 unidades) | Demostración de procesamiento OCR |
| 2 | Imágenes de albaranes de salida (10 unidades) | Demostración de reducción de inventario |
| 3 | Albaranes manuscritos (3 unidades) | Demostración de precisión OCR |
| 4 | Datos maestros de inventario | Demostración de cotejo |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de imágenes de albaranes de muestra | 2 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Procesamiento de albaranes en tiempo real (integración con cámara)
- Integración con sistema WMS
- Integración de modelo de previsión de demanda

---

## Technical Notes

| Componente | Función |
|--------------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (OCR Processor) | Extracción de texto de albaranes mediante Textract |
| Lambda (Field Mapper) | Mapeo de campos mediante Bedrock |
| Lambda (Inventory Updater) | Actualización y agregación de datos de inventario |
| Lambda (Report Generator) | Generación de informe de análisis de inventario |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Baja precisión OCR | Usar datos preprocesados |
| Retraso de Bedrock | Mostrar informe pregenerado |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: Seleccionable con OutputDestination (Pattern B)

UC12 logistics-ocr soporta el parámetro `OutputDestination` desde la actualización del 2026-05-10
(consulte `docs/output-destination-patterns.md`).

**Carga de trabajo objetivo**: OCR de albaranes de envío / Análisis de inventario / Informes logísticos

**2 modos**:

### STANDARD_S3 (predeterminado, comportamiento tradicional)
Crea un nuevo bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) y
escribe los resultados de IA allí.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (otros parámetros obligatorios)
```

### FSXN_S3AP (patrón "no data movement")
Escribe los resultados de IA de vuelta al **mismo volumen FSx ONTAP** que los datos originales
a través del FSxN S3 Access Point. Los usuarios de SMB/NFS pueden ver directamente los resultados
de IA dentro de la estructura de directorios que usan en su trabajo diario. No se crea un bucket S3 estándar.

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (otros parámetros obligatorios)
```

**Notas importantes**:

- Se recomienda encarecidamente especificar `S3AccessPointName` (permitir IAM tanto en formato Alias como ARN)
- Los objetos superiores a 5GB no son compatibles con FSxN S3AP (especificación de AWS), se requiere carga multiparte
- Para las restricciones de las especificaciones de AWS, consulte
  [la sección "Restricciones de especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
  y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Capturas de pantalla de UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se dirige a
**pantallas de UI/UX que los usuarios finales ven realmente en su trabajo diario**. Las vistas
orientadas a técnicos (gráfico de Step Functions, eventos de stack de CloudFormation, etc.) se
consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (consulte README raíz)
- 📸 **Recaptura de UI/UX**: ✅ Capturado en verificación de redespliegue del 2026-05-10 (confirmado gráfico de Step Functions UC12, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consulte la "Guía de captura" al final de este documento

### Capturado en verificación de redespliegue del 2026-05-10 (centrado en UI/UX)

#### UC12 Step Functions Graph view (SUCCEEDED)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para el usuario final que visualiza
el estado de ejecución de cada Lambda / Parallel / Map state con colores.

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

![UC12 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph (vista ampliada — detalle de cada paso)](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### Pantallas de UI/UX objetivo en reverificación (lista de captura recomendada)

- Bucket de salida S3 (waybills-ocr/, inventory/, reports/)
- Resultados de OCR de albaranes de Textract (Cross-Region)
- Etiquetas de imágenes de almacén de Rekognition
- Informe de agregación de envíos

### Guía de captura

1. **Preparación previa**:
   - Confirme los requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquete Lambda con `UC=logistics-ocr bash scripts/package_generic_uc.sh`
   - Despliegue con `bash scripts/deploy_generic_ucs.sh UC12`

2. **Colocación de datos de muestra**:
   - Cargue archivos de muestra al prefijo `waybills/` a través del S3 AP Alias
   - Inicie Step Functions `fsxn-logistics-ocr-demo-workflow` (entrada `{}`)

3. **Captura** (cierre CloudShell/terminal, enmascare el nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-logistics-ocr-demo-output-<account>`
   - Vista previa de JSON de salida de AI/ML (consulte el formato de `build/preview_*.html`)
   - Notificación por correo electrónico de SNS (si corresponde)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py logistics-ocr-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Elimine con `bash scripts/cleanup_generic_ucs.sh UC12`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
