# Detección de Anomalías en Datos de Registro y Reporte de Cumplimiento — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un pipeline de detección de anomalías en datos de registro de pozos y generación de informes de cumplimiento. Detecta automáticamente problemas de calidad en los datos de registro y crea eficientemente informes regulatorios.

**Mensaje central de la demostración**: Detectar automáticamente anomalías en datos de registro de pozos y generar instantáneamente informes de cumplimiento que cumplan con los requisitos regulatorios.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Ítem | Detalle |
|------|---------|
| **Cargo** | Ingeniero geólogo / Analista de datos / Responsable de cumplimiento |
| **Tareas diarias** | Análisis de datos de registro, evaluación de pozos, creación de informes regulatorios |
| **Desafío** | Detectar manualmente anomalías en grandes volúmenes de datos de registro consume mucho tiempo |
| **Resultado esperado** | Verificación automática de calidad de datos y eficiencia en informes regulatorios |

### Persona: Sr. Matsumoto (Ingeniero geólogo)

- Gestiona datos de registro de más de 50 pozos
- Requiere informes periódicos a autoridades regulatorias
- "Quiero detectar automáticamente anomalías en los datos y hacer más eficiente la creación de informes"

---

## Demo Scenario: Análisis por lotes de datos de registro

### Visión general del flujo de trabajo

```
Datos de registro    Verificación       Detección de      Cumplimiento
(LAS/DLIS)      →    de datos      →   anomalías    →    Generación de
                     Control calidad    Análisis           informes
                     Formato            estadístico
                                       Detección outliers
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de narración**:
> Es necesario verificar periódicamente la calidad de los datos de registro de 50 pozos e informar a las autoridades regulatorias. El análisis manual tiene un alto riesgo de omisiones.

**Key Visual**: Lista de archivos de datos de registro (formato LAS/DLIS)

### Section 2: Data Ingestion (0:45–1:30)

**Resumen de narración**:
> Se cargan los archivos de datos de registro y se inicia el pipeline de verificación de calidad. Comienza con la validación de formato.

**Key Visual**: Inicio del flujo de trabajo, validación de formato de datos

### Section 3: Anomaly Detection (1:30–2:30)

**Resumen de narración**:
> Se ejecuta detección estadística de anomalías para cada curva de registro (GR, SP, Resistivity, etc.). Se detectan valores atípicos por intervalo de profundidad.

**Key Visual**: Procesamiento de detección de anomalías, resaltado de anomalías en curvas de registro

### Section 4: Results Review (2:30–3:45)

**Resumen de narración**:
> Se confirman las anomalías detectadas por pozo y por curva. Se clasifican los tipos de anomalías (picos, faltantes, desviaciones de rango).

**Key Visual**: Tabla de resultados de detección de anomalías, resumen por pozo

### Section 5: Compliance Report (3:45–5:00)

**Resumen de narración**:
> La IA genera automáticamente un informe de cumplimiento que cumple con los requisitos regulatorios. Incluye resumen de calidad de datos, registro de respuesta a anomalías y acciones recomendadas.

**Key Visual**: Informe de cumplimiento (conforme a formato regulatorio)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|----------|---------|
| 1 | Lista de archivos de datos de registro | Section 1 |
| 2 | Inicio de pipeline y validación de formato | Section 2 |
| 3 | Resultados de procesamiento de detección de anomalías | Section 3 |
| 4 | Resumen de anomalías por pozo | Section 4 |
| 5 | Informe de cumplimiento | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|---------|--------|---------------|
| Problem | 0:00–0:45 | "Verificar manualmente la calidad de datos de registro de 50 pozos tiene sus límites" |
| Ingestion | 0:45–1:30 | "La verificación comienza automáticamente con la carga de datos" |
| Detection | 1:30–2:30 | "Detectar anomalías en cada curva mediante métodos estadísticos" |
| Results | 2:30–3:45 | "Clasificar y confirmar anomalías por pozo y por curva" |
| Report | 3:45–5:00 | "La IA genera automáticamente informes conformes a regulaciones" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|-------|-----|
| 1 | Datos de registro normales (formato LAS, 10 pozos) | Línea base |
| 2 | Datos con anomalías de picos (3 casos) | Demo de detección de anomalías |
| 3 | Datos con intervalos faltantes (2 casos) | Demo de control de calidad |
| 4 | Datos con desviaciones de rango (2 casos) | Demo de clasificación |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|-------|------------------|
| Preparación de datos de registro de muestra | 3 horas |
| Confirmación de ejecución de pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Monitoreo de datos de perforación en tiempo real
- Automatización de correlación de estratos
- Integración con modelos geológicos 3D

---

## Technical Notes

| Componente | Rol |
|------------|-----|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (LAS Parser) | Análisis de formato de datos de registro |
| Lambda (Anomaly Detector) | Detección estadística de anomalías |
| Lambda (Report Generator) | Generación de informes de cumplimiento mediante Bedrock |
| Amazon Athena | Análisis agregado de datos de registro |

### Fallback

| Escenario | Respuesta |
|-----------|-----------|
| Fallo en análisis LAS | Usar datos previamente analizados |
| Latencia de Bedrock | Mostrar informe pregenerado |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Capturas de pantalla verificadas de UI/UX

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **pantallas de UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráficos de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (ver README raíz)
- 📸 **Recaptura de UI/UX**: ✅ Capturado en verificación de redespliegue 2026-05-10 (confirmado gráfico de Step Functions UC8, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consultar "Guía de captura" al final de este documento

### Capturado en verificación de redespliegue 2026-05-10 (centrado en UI/UX)

#### UC8 Step Functions Graph view (SUCCEEDED)

![UC8 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/uc8-stepfunctions-graph.png)

Step Functions Graph view es la pantalla más importante para usuarios finales que visualiza el estado de ejecución de cada estado Lambda / Parallel / Map mediante colores.

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

#### UC8 Step Functions Graph (SUCCEEDED — Recapturado después de corrección IAM Phase 8)

![UC8 Step Functions Graph (SUCCEEDED)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-succeeded.png)

Redesplegado después de corrección IAM S3AP. Todos los pasos SUCCEEDED (2:59).

#### UC8 Step Functions Graph (Vista ampliada — Detalle de cada paso)

![UC8 Step Functions Graph (Vista ampliada)](../../docs/screenshots/masked/uc8-demo/step-functions-graph-zoomed.png)

### Pantallas UI/UX objetivo en reverificación (lista de captura recomendada)

- Bucket de salida S3 (segy-metadata/, anomalies/, reports/)
- Resultados de consulta Athena (estadísticas de metadatos SEG-Y)
- Etiquetas de imagen de registro de pozo Rekognition
- Informe de detección de anomalías

### Guía de captura

1. **Preparación previa**:
   - Confirmar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=energy-seismic bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC8`

2. **Colocación de datos de muestra**:
   - Cargar archivos de muestra al prefijo `seismic/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-energy-seismic-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-energy-seismic-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py energy-seismic-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC8`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)
