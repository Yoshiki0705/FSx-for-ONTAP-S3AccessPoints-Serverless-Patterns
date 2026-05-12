# Preprocesamiento y Anotación de Datos de Conducción — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración ilustra el pipeline de preprocesamiento y anotación de datos de conducción en el desarrollo de conducción autónoma. Clasifica automáticamente grandes volúmenes de datos de sensores, realiza verificaciones de calidad y construye eficientemente conjuntos de datos de entrenamiento.

**Mensaje central de la demostración**: Automatizar la verificación de calidad de datos de conducción y la asignación de metadatos para acelerar la construcción de conjuntos de datos para entrenamiento de IA.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Ingeniero de Datos / Ingeniero de ML |
| **Tareas diarias** | Gestión de datos de conducción, anotación, construcción de conjuntos de datos de entrenamiento |
| **Desafío** | No puede extraer eficientemente escenas útiles de grandes volúmenes de datos de conducción |
| **Resultado esperado** | Verificación automática de calidad de datos y eficiencia en la clasificación de escenas |

### Persona: Sr. Ito (Ingeniero de Datos)

- Acumulación diaria de datos de conducción en el orden de TB
- Verificación manual de sincronización de cámara, LiDAR y radar
- "Quiero enviar automáticamente solo datos de buena calidad al pipeline de entrenamiento"

---

## Demo Scenario: Preprocesamiento por lotes de datos de conducción

### Visión general del flujo de trabajo

```
Datos de conducción    Verificación de datos    Clasificación de escenas    Conjunto de datos
(ROS bag, etc.)    →   Verificación de calidad  →  Metadatos           →   Generación de catálogo
                       Verificación de sincronización    Asignación (IA)
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Datos de conducción que se acumulan diariamente en el orden de TB. Datos de mala calidad (pérdida de sensores, desincronización) están mezclados, y la selección manual es poco realista.

**Key Visual**: Estructura de carpetas de datos de conducción, visualización del volumen de datos

### Section 2: Pipeline Trigger (0:45–1:30)

**Resumen de la narración**:
> Cuando se cargan nuevos datos de conducción, el pipeline de preprocesamiento se inicia automáticamente.

**Key Visual**: Carga de datos → Inicio automático del flujo de trabajo

### Section 3: Quality Validation (1:30–2:30)

**Resumen de la narración**:
> Verificación de integridad de datos de sensores: detección automática de pérdida de fotogramas, sincronización de marcas de tiempo y corrupción de datos.

**Key Visual**: Resultados de verificación de calidad — Puntuación de salud por sensor

### Section 4: Scene Classification (2:30–3:45)

**Resumen de la narración**:
> La IA clasifica automáticamente las escenas: intersecciones, autopistas, mal tiempo, noche, etc. Se asigna como metadatos.

**Key Visual**: Tabla de resultados de clasificación de escenas, distribución por categoría

### Section 5: Dataset Catalog (3:45–5:00)

**Resumen de la narración**:
> Generación automática de catálogo de datos verificados en calidad. Disponible como conjunto de datos con búsqueda por condiciones de escena.

**Key Visual**: Catálogo de conjuntos de datos, interfaz de búsqueda

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Estructura de carpetas de datos de conducción | Section 1 |
| 2 | Pantalla de inicio del pipeline | Section 2 |
| 3 | Resultados de verificación de calidad | Section 3 |
| 4 | Resultados de clasificación de escenas | Section 4 |
| 5 | Catálogo de conjuntos de datos | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Imposible seleccionar manualmente escenas útiles de datos en el orden de TB" |
| Trigger | 0:45–1:30 | "El preprocesamiento comienza automáticamente con la carga" |
| Validation | 1:30–2:30 | "Detección automática de pérdida de sensores y desincronización" |
| Classification | 2:30–3:45 | "La IA clasifica automáticamente las escenas y asigna metadatos" |
| Catalog | 3:45–5:00 | "Generación automática de catálogo de conjuntos de datos con búsqueda" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Datos de conducción normal (5 sesiones) | Línea base |
| 2 | Datos con pérdida de fotogramas (2 casos) | Demostración de verificación de calidad |
| 3 | Datos de escenas diversas (intersección, autopista, noche) | Demostración de clasificación |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Preparación de datos de conducción de muestra | 3 horas |
| Verificación de ejecución del pipeline | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Generación automática de anotación 3D
- Selección de datos mediante aprendizaje activo
- Integración de versionado de datos

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación de flujo de trabajo |
| Lambda (Python 3.13) | Verificación de calidad de datos de sensores, clasificación de escenas, generación de catálogo |
| Lambda SnapStart | Reducción de arranque en frío (opt-in con `EnableSnapStart=true`) |
| SageMaker (4-way routing) | Inferencia (Batch / Serverless / Provisioned / Inference Components) |
| SageMaker Inference Components | Verdadero scale-to-zero (`EnableInferenceComponents=true`) |
| Amazon Bedrock | Clasificación de escenas y propuestas de anotación |
| Amazon Athena | Búsqueda y agregación de metadatos |
| CloudFormation Guard Hooks | Aplicación de políticas de seguridad en el despliegue |

### Prueba local (Phase 6A)

```bash
# SAM CLI でローカルテスト
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### Respaldo

| Escenario | Respuesta |
|---------|------|
| Retraso en procesamiento de datos de gran volumen | Ejecutar con subconjunto |
| Precisión de clasificación insuficiente | Mostrar resultados preclasificados |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: Seleccionable con OutputDestination (Pattern B)

UC9 autonomous-driving soporta el parámetro `OutputDestination` desde la actualización del 2026-05-10
(consulte `docs/output-destination-patterns.md`).

**Carga de trabajo objetivo**: Datos ADAS / conducción autónoma (extracción de fotogramas, QC de nubes de puntos, anotación, inferencia)

**2 modos**:

### STANDARD_S3 (predeterminado, como antes)
Crea un nuevo bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) y
escribe los artefactos de IA allí.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP (patrón "no data movement")
Escribe los artefactos de IA de vuelta al **mismo volumen FSx ONTAP** que los datos originales
a través del FSxN S3 Access Point. Los usuarios de SMB/NFS pueden ver directamente los artefactos de IA
dentro de la estructura de directorios que usan en su trabajo diario. No se crea un bucket S3 estándar.

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**Notas**:

- Se recomienda encarecidamente especificar `S3AccessPointName` (permitir IAM en formato Alias y ARN)
- Objetos superiores a 5GB no son posibles con FSxN S3AP (especificación de AWS), se requiere carga multiparte
- Para restricciones de especificación de AWS, consulte
  [la sección "AWS 仕様上の制約と回避策" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
  y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Capturas de pantalla de UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se dirigen a **pantallas de UI/UX
que los usuarios finales ven realmente en su trabajo diario**. Las vistas para técnicos (gráfico de Step Functions, eventos
de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ⚠️ **Verificación E2E**: Solo algunas funciones (se recomienda verificación adicional en entorno de producción)
- 📸 **Captura UI/UX**: ✅ SFN Graph completado (Phase 8 Theme D, commit 081cc66)

### Capturas de pantalla existentes (de Phase 1-6 aplicables)

![UC9 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### Pantallas de UI/UX objetivo para reverificación (lista de captura recomendada)

- Bucket de salida S3 (keyframes/, annotations/, qc/)
- Resultados de detección de objetos en fotogramas clave de Rekognition
- Resumen de verificación de calidad de nube de puntos LiDAR
- JSON de anotación compatible con COCO

### Guía de captura

1. **Preparación previa**:
   - Verificar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=autonomous-driving bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC9`

2. **Colocación de datos de muestra**:
   - Cargar archivos de muestra al prefijo `footage/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-autonomous-driving-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-autonomous-driving-demo-output-<account>`
   - Vista previa de JSON de salida de AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo electrónico de SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py autonomous-driving-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC9`
   - Liberación de ENI de Lambda en VPC toma 15-30 minutos (especificación de AWS)
