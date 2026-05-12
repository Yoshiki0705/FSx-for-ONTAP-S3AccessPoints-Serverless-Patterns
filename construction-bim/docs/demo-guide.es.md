# Detección de cambios en modelos BIM y cumplimiento de seguridad — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline de detección de cambios en modelos BIM y verificación de cumplimiento de seguridad. Detecta automáticamente cambios de diseño y verifica la conformidad con los estándares de construcción.

**Mensaje central de la demostración**: Seguimiento automático de cambios en modelos BIM y detección instantánea de violaciones de estándares de seguridad. Acorta el ciclo de revisión de diseño.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Gerente BIM / Ingeniero de diseño estructural |
| **Tareas diarias** | Gestión de modelos BIM, revisión de cambios de diseño, verificación de cumplimiento |
| **Desafío** | Difícil rastrear cambios de diseño de múltiples equipos y confirmar conformidad con estándares |
| **Resultado esperado** | Eficiencia en detección automática de cambios y verificación de estándares de seguridad |

### Persona: Sr. Kimura (Gerente BIM)

- Proyecto de construcción a gran escala con 20+ equipos de diseño trabajando en paralelo
- Necesita confirmar que los cambios de diseño diarios no afecten los estándares de seguridad
- "Quiero ejecutar verificaciones de seguridad automáticamente cuando haya cambios"

---

## Demo Scenario: Detección automática de cambios de diseño y verificación de seguridad

### Visión general del flujo de trabajo

```
Actualización modelo BIM     Detección cambios        Cumplimiento     Reporte de revisión
(IFC/RVT)              →   Análisis diferencias    →   Cotejo reglas     →    Generación AI
                           Comparación elementos        Verificación estándares seguridad
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de narración**:
> En un proyecto a gran escala, 20 equipos actualizan modelos BIM en paralelo. La verificación manual no puede seguir el ritmo para confirmar que los cambios no violen los estándares de seguridad.

**Key Visual**: Lista de archivos de modelos BIM, historial de actualizaciones de múltiples equipos

### Section 2: Change Detection (0:45–1:30)

**Resumen de narración**:
> Detecta actualizaciones de archivos de modelo y analiza automáticamente las diferencias con la versión anterior. Identifica elementos modificados (componentes estructurales, ubicación de equipos, etc.).

**Key Visual**: Activación de detección de cambios, inicio de análisis de diferencias

### Section 3: Compliance Check (1:30–2:30)

**Resumen de narración**:
> Coteja automáticamente las reglas de estándares de seguridad contra los elementos modificados. Verifica conformidad con estándares sísmicos, compartimentación contra incendios, rutas de evacuación, etc.

**Key Visual**: Procesamiento de cotejo de reglas, lista de elementos de verificación

### Section 4: Results Analysis (2:30–3:45)

**Resumen de narración**:
> Confirma resultados de verificación. Muestra lista de elementos de violación, alcance de impacto y nivel de importancia.

**Key Visual**: Tabla de resultados de detección de violaciones, clasificación por nivel de importancia

### Section 5: Review Report (3:45–5:00)

**Resumen de narración**:
> La IA genera un reporte de revisión de diseño. Presenta detalles de violaciones, propuestas de corrección y otros elementos de diseño afectados.

**Key Visual**: Reporte de revisión generado por IA

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Lista de archivos de modelos BIM | Section 1 |
| 2 | Detección de cambios y visualización de diferencias | Section 2 |
| 3 | Progreso de verificación de cumplimiento | Section 3 |
| 4 | Resultados de detección de violaciones | Section 4 |
| 5 | Reporte de revisión de IA | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "El seguimiento de cambios en trabajo paralelo y la confirmación de seguridad no pueden seguir el ritmo" |
| Detection | 0:45–1:30 | "Detecta automáticamente actualizaciones de modelo y analiza diferencias" |
| Compliance | 1:30–2:30 | "Coteja automáticamente reglas de estándares de seguridad" |
| Results | 2:30–3:45 | "Comprende instantáneamente elementos de violación y alcance de impacto" |
| Report | 3:45–5:00 | "La IA presenta propuestas de corrección y análisis de impacto" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Modelo BIM base (formato IFC) | Origen de comparación |
| 2 | Modelo después de cambios (con cambios estructurales) | Demostración de detección de diferencias |
| 3 | Modelo con violaciones de estándares de seguridad (3 casos) | Demostración de cumplimiento |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de datos BIM de muestra | 3 horas |
| Confirmación de ejecución de pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Integración con visualización 3D
- Notificación de cambios en tiempo real
- Verificación de consistencia con fase de construcción

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (Change Detector) | Análisis de diferencias de modelo BIM |
| Lambda (Compliance Checker) | Cotejo de reglas de estándares de seguridad |
| Lambda (Report Generator) | Generación de reporte de revisión mediante Bedrock |
| Amazon Athena | Agregación de historial de cambios y datos de violaciones |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Fallo de análisis IFC | Usar datos pre-analizados |
| Retraso en cotejo de reglas | Mostrar resultados pre-verificados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: Seleccionable con OutputDestination (Pattern B)

UC10 construction-bim soporta el parámetro `OutputDestination` desde la actualización del 2026-05-10
(consulte `docs/output-destination-patterns.md`).

**Cargas de trabajo objetivo**: BIM de construcción / OCR de planos / Verificación de cumplimiento de seguridad

**2 modos**:

### STANDARD_S3 (predeterminado, como antes)
Crea un nuevo bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) y
escribe los resultados de IA allí.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (otros parámetros requeridos)
```

### FSXN_S3AP (patrón "no data movement")
Escribe los resultados de IA de vuelta al **mismo volumen FSx ONTAP** que los datos originales
a través del S3 Access Point de FSxN. Los usuarios de SMB/NFS pueden
ver directamente los resultados de IA dentro de la estructura de directorios que usan en su trabajo diario.
No se crea un bucket S3 estándar.

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (otros parámetros requeridos)
```

**Notas importantes**:

- Se recomienda encarecidamente especificar `S3AccessPointName` (permitir IAM tanto en formato Alias como ARN)
- Objetos mayores a 5GB no son posibles con FSxN S3AP (especificación AWS), se requiere carga multiparte
- Las restricciones de especificación AWS se encuentran en
  [la sección "Restricciones de especificación AWS y soluciones" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
  y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Capturas de pantalla UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas UI/UX
que los usuarios finales ven realmente en su trabajo diario**. Las vistas para técnicos (gráfico de Step Functions, eventos
de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (consulte README raíz)
- 📸 **Re-captura UI/UX**: ✅ Capturado en verificación de re-despliegue 2026-05-10 (confirmado gráfico Step Functions UC10, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consulte "Guía de captura" al final de este documento

### Capturado en verificación de re-despliegue 2026-05-10 (centrado en UI/UX)

#### UC10 Step Functions Graph view (SUCCEEDED)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para usuarios finales que visualiza
el estado de ejecución de cada Lambda / Parallel / Map state con colores.

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

![UC10 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph (vista ampliada — detalle de cada paso)](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### Pantallas UI/UX objetivo en re-verificación (lista de captura recomendada)

- Bucket de salida S3 (drawings-ocr/, bim-metadata/, safety-reports/)
- Resultados OCR de planos Textract (Cross-Region)
- Reporte de diferencias de versión BIM
- Verificación de cumplimiento de seguridad Bedrock

### Guía de captura

1. **Preparación previa**:
   - Confirme requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (existencia de VPC/S3 AP común)
   - Empaquete Lambda con `UC=construction-bim bash scripts/package_generic_uc.sh`
   - Despliegue con `bash scripts/deploy_generic_ucs.sh UC10`

2. **Colocación de datos de muestra**:
   - Suba archivos de muestra al prefijo `drawings/` a través de S3 AP Alias
   - Inicie Step Functions `fsxn-construction-bim-demo-workflow` (entrada `{}`)

3. **Captura** (cierre CloudShell/terminal, enmascare nombre de usuario en la esquina superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-construction-bim-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia formato `build/preview_*.html`)
   - Notificación de correo SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascare automáticamente con `python3 scripts/mask_uc_demos.py construction-bim-demo`
   - Enmascare adicionalmente según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Elimine con `bash scripts/cleanup_generic_ucs.sh UC10`
   - Liberación de ENI de Lambda VPC toma 15-30 minutos (especificación AWS)
