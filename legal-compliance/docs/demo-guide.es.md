# Auditoría de Permisos del Servidor de Archivos — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

> Nota: Esta traducción ha sido producida por Amazon Bedrock Claude. Las contribuciones para mejorar la calidad de la traducción son bienvenidas.

## Executive Summary

Esta demostración presenta un flujo de trabajo de auditoría que detecta automáticamente permisos de acceso excesivos en servidores de archivos. Analiza las ACL de NTFS, identifica entradas que violan el principio de privilegio mínimo y genera automáticamente informes de cumplimiento.

**Mensaje central de la demostración**: Automatizar la auditoría de permisos de servidores de archivos que manualmente tomaría semanas, visualizando instantáneamente los riesgos de permisos excesivos.

**Tiempo estimado**: 3–5 minutos

---

## Target Audience & Persona

| Elemento | Detalle |
|------|------|
| **Cargo** | Responsable de Seguridad de la Información / Administrador de Cumplimiento de TI |
| **Tareas diarias** | Revisión de permisos de acceso, respuesta a auditorías, gestión de políticas de seguridad |
| **Desafío** | Verificar manualmente los permisos de miles de carpetas es poco práctico |
| **Resultado esperado** | Detección temprana de permisos excesivos y automatización de evidencia de cumplimiento |

### Persona: Sr. Sato (Administrador de Seguridad de la Información)

- Necesita revisar los permisos de todas las carpetas compartidas para la auditoría anual
- Desea detectar instantáneamente configuraciones peligrosas como "Everyone Full Control"
- Quiere crear eficientemente informes para presentar a la firma de auditoría

---

## Demo Scenario: Automatización de la auditoría anual de permisos

### Vista general del flujo de trabajo

```
Servidor de archivos     Recopilación ACL    Análisis de permisos    Generación de informes
(Compartido NTFS)   →   Extracción de   →   Detección de      →    Informe de auditoría
                        metadatos           violaciones             (Resumen AI)
                                           (Coincidencia de reglas)
```

---

## Storyboard (5 secciones / 3–5 minutos)

### Section 1: Problem Statement (0:00–0:45)

**Resumen de la narración**:
> Es época de auditoría anual. Se necesita revisar los permisos de miles de carpetas compartidas, pero la verificación manual tomaría semanas. Si se dejan permisos excesivos sin atender, aumenta el riesgo de fuga de información.

**Key Visual**: Estructura de carpetas masiva con superposición de "Auditoría manual: estimado 3–4 semanas"

### Section 2: Workflow Trigger (0:45–1:30)

**Resumen de la narración**:
> Se especifica el volumen objetivo de auditoría y se inicia el flujo de trabajo de auditoría de permisos.

**Key Visual**: Pantalla de ejecución de Step Functions, especificación de ruta objetivo

### Section 3: ACL Analysis (1:30–2:30)

**Resumen de la narración**:
> Se recopilan automáticamente las ACL de NTFS de cada carpeta y se detectan violaciones con las siguientes reglas:
> - Permisos excesivos para Everyone / Authenticated Users
> - Acumulación de herencia innecesaria
> - Persistencia de cuentas de empleados retirados

**Key Visual**: Progreso del escaneo de ACL mediante procesamiento paralelo

### Section 4: Results Review (2:30–3:45)

**Resumen de la narración**:
> Se consultan los resultados detectados con SQL. Se verifica el número de violaciones y la distribución por nivel de riesgo.

**Key Visual**: Resultados de consulta de Athena — tabla de lista de violaciones

### Section 5: Compliance Report (3:45–5:00)

**Resumen de la narración**:
> La IA genera automáticamente el informe de auditoría. Presenta evaluación de riesgos, respuestas recomendadas y acciones priorizadas.

**Key Visual**: Informe de auditoría generado (resumen de riesgos + recomendaciones de respuesta)

---

## Screen Capture Plan

| # | Pantalla | Sección |
|---|------|-----------|
| 1 | Estructura de carpetas del servidor de archivos | Section 1 |
| 2 | Inicio de ejecución del flujo de trabajo | Section 2 |
| 3 | Procesamiento paralelo de escaneo de ACL | Section 3 |
| 4 | Resultados de consulta de detección de violaciones de Athena | Section 4 |
| 5 | Informe de auditoría generado por IA | Section 5 |

---

## Narration Outline

| Sección | Tiempo | Mensaje clave |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Realizar manualmente la auditoría de permisos de miles de carpetas es poco práctico" |
| Trigger | 0:45–1:30 | "Especificar el volumen objetivo e iniciar la auditoría" |
| Analysis | 1:30–2:30 | "Recopilar automáticamente las ACL y detectar violaciones de políticas" |
| Results | 2:30–3:45 | "Comprender instantáneamente el número de violaciones y el nivel de riesgo" |
| Report | 3:45–5:00 | "Generar automáticamente el informe de auditoría y presentar prioridades de respuesta" |

---

## Sample Data Requirements

| # | Datos | Uso |
|---|--------|------|
| 1 | Carpetas con permisos normales (50+) | Línea base |
| 2 | Configuración Everyone Full Control (5 casos) | Violación de alto riesgo |
| 3 | Persistencia de cuentas de empleados retirados (3 casos) | Violación de riesgo medio |
| 4 | Carpetas con herencia excesiva (10 casos) | Violación de bajo riesgo |

---

## Timeline

### Alcanzable en 1 semana

| Tarea | Tiempo requerido |
|--------|---------|
| Generación de datos de ACL de muestra | 2 horas |
| Verificación de ejecución del flujo de trabajo | 2 horas |
| Captura de pantallas | 2 horas |
| Creación de guion de narración | 2 horas |
| Edición de video | 4 horas |

### Future Enhancements

- Detección automática de empleados retirados mediante integración con Active Directory
- Monitoreo en tiempo real de cambios de permisos
- Ejecución automática de acciones correctivas

---

## Technical Notes

| Componente | Rol |
|--------------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (ACL Collector) | Recopilación de metadatos de ACL de NTFS |
| Lambda (Policy Checker) | Coincidencia de reglas de violación de políticas |
| Lambda (Report Generator) | Generación de informes de auditoría mediante Bedrock |
| Amazon Athena | Análisis SQL de datos de violaciones |

### Fallback

| Escenario | Respuesta |
|---------|------|
| Fallo en recopilación de ACL | Usar datos previamente obtenidos |
| Retraso de Bedrock | Mostrar informe pregenerado |

---

*Este documento es una guía de producción de video de demostración para presentaciones técnicas.*

---

## Acerca del destino de salida: FSxN S3 Access Point (Pattern A)

UC1 legal-compliance está clasificado como **Pattern A: Native S3AP Output**
(consulte `docs/output-destination-patterns.md`).

**Diseño**: Los metadatos de contratos, registros de auditoría e informes de resumen se escriben todos de vuelta al **mismo volumen de FSx ONTAP** que los datos de contratos originales a través de FSxN S3 Access Point. No se crea un bucket S3 estándar (patrón "no data movement").

**Parámetros de CloudFormation**:
- `S3AccessPointAlias`: S3 AP Alias para lectura de datos de contratos de entrada
- `S3AccessPointOutputAlias`: S3 AP Alias para escritura de salida (puede ser el mismo que el de entrada)

**Ejemplo de despliegue**:
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (otros parámetros obligatorios)
```

**Vista desde usuarios SMB/NFS**:
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # Contrato original
  └── summaries/2026/05/                # Resumen generado por IA (dentro del mismo volumen)
      └── contract_ABC.json
```

Para las restricciones de las especificaciones de AWS, consulte
[la sección "Restricciones de especificaciones de AWS y soluciones alternativas" del README del proyecto](../../README.md#aws-仕様上の制約と回避策)
y [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md).

---

## Capturas de pantalla de UI/UX verificadas

Siguiendo la misma política que las demostraciones de Phase 7 UC15/16/17 y UC6/11/14, se enfocan en **las pantallas de UI/UX que los usuarios finales ven realmente en sus tareas diarias**. Las vistas para técnicos (gráficos de Step Functions, eventos de stack de CloudFormation, etc.) se consolidan en `docs/verification-results-*.md`.

### Estado de verificación de este caso de uso

- ✅ **Ejecución E2E**: Confirmado en Phase 1-6 (consulte README raíz)
- 📸 **Recaptura de UI/UX**: ✅ Capturado en verificación de redespliegue del 2026-05-10 (confirmado gráfico de Step Functions de UC1, ejecución exitosa de Lambda)
- 🔄 **Método de reproducción**: Consulte la "Guía de captura" al final de este documento

### Capturado en verificación de redespliegue del 2026-05-10 (centrado en UI/UX)

#### Vista de gráfico de Step Functions de UC1 (SUCCEEDED)

![Vista de gráfico de Step Functions de UC1 (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

La vista de gráfico de Step Functions es la pantalla más importante para el usuario final que visualiza con colores el estado de ejecución de cada estado Lambda / Parallel / Map.

#### Gráfico de Step Functions de UC1 (SUCCEEDED — Verificación de Phase 8 Theme D/E/N, 2:38:20)

![Gráfico de Step Functions de UC1 (SUCCEEDED)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-succeeded.png)

Ejecutado con Phase 8 Theme E (event-driven) + Theme N (observability) habilitados.
549 iteraciones de ACL, 3871 eventos, todos los pasos SUCCEEDED en 2:38:20.

#### Gráfico de Step Functions de UC1 (Vista ampliada — Detalle de cada paso)

![Gráfico de Step Functions de UC1 (Vista ampliada)](../../docs/screenshots/masked/uc1-demo/step-functions-graph-zoomed.png)

#### S3 Access Points para FSx ONTAP de UC1 (Visualización de consola)

![S3 Access Points para FSx ONTAP de UC1](../../docs/screenshots/masked/uc1-demo/s3-access-points-for-fsx.png)

#### Detalle de S3 Access Point de UC1 (Vista de resumen)

![Detalle de S3 Access Point de UC1](../../docs/screenshots/masked/uc1-demo/s3ap-detail-overview.png)

### Capturas de pantalla existentes (partes aplicables de Phase 1-6)

#### Despliegue de stack de CloudFormation de UC1 completado (verificación del 2026-05-02)

![Despliegue de stack de CloudFormation de UC1 completado (verificación del 2026-05-02)](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### Step Functions de UC1 SUCCEEDED (ejecución E2E exitosa)

![Step Functions de UC1 SUCCEEDED (ejecución E2E exitosa)](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### Pantallas de UI/UX objetivo en reverificación (lista de captura recomendada)

- Bucket de salida S3 (prefijos audit-reports/, acl-audits/, athena-results/)
- Resultados de consulta de Athena (SQL de detección de violaciones de ACL)
- Informe de auditoría generado por Bedrock (resumen de violaciones de cumplimiento)
- Correo electrónico de notificación SNS (alerta de auditoría)

### Guía de captura

1. **Preparación previa**:
   - Confirmar requisitos previos con `bash scripts/verify_phase7_prerequisites.sh` (presencia de VPC/S3 AP común)
   - Empaquetar Lambda con `UC=legal-compliance bash scripts/package_generic_uc.sh`
   - Desplegar con `bash scripts/deploy_generic_ucs.sh UC1`

2. **Colocación de datos de muestra**:
   - Subir archivos de muestra al prefijo `contracts/` a través de S3 AP Alias
   - Iniciar Step Functions `fsxn-legal-compliance-demo-workflow` (entrada `{}`)

3. **Captura** (cerrar CloudShell/terminal, enmascarar nombre de usuario en la parte superior derecha del navegador):
   - Vista general del bucket de salida S3 `fsxn-legal-compliance-demo-output-<account>`
   - Vista previa de JSON de salida AI/ML (referencia al formato `build/preview_*.html`)
   - Notificación por correo electrónico SNS (si aplica)

4. **Procesamiento de enmascaramiento**:
   - Enmascaramiento automático con `python3 scripts/mask_uc_demos.py legal-compliance-demo`
   - Enmascaramiento adicional según `docs/screenshots/MASK_GUIDE.md` (si es necesario)

5. **Limpieza**:
   - Eliminar con `bash scripts/cleanup_generic_ucs.sh UC1`
   - Liberación de ENI de Lambda VPC en 15-30 minutos (especificación de AWS)

---

## Estimación de tiempo de ejecución (resultados de verificación de Phase 8)

El tiempo de procesamiento de UC1 es proporcional al número de archivos en el volumen ONTAP.

| Paso | Contenido del procesamiento | Valor medido (549 archivos) |
|---------|---------|---------------------|
| Discovery | Obtener lista de archivos mediante ONTAP REST API | 8 minutos |
| AclCollection (Map) | Recopilar ACL de NTFS de cada archivo | 2 horas 20 minutos |
| AthenaAnalysis | Consulta de Glue Data Catalog + Athena | 5 minutos |
| ReportGeneration | Generación de informe con Bedrock Nova Lite | 5 minutos |
| **Total** | | **2 horas 38 minutos** |

### Tiempo de procesamiento estimado por número de archivos

| Número de archivos | Tiempo total estimado | Uso recomendado |
|-----------|------------|---------|
| 10 | ~5 minutos | Demostración rápida |
| 50 | ~15 minutos | Demostración estándar |
| 100 | ~30 minutos | Verificación detallada |
| 500+ | ~2.5 horas | Prueba equivalente a producción |

### Consejos de optimización de rendimiento

- **Map state MaxConcurrency**: Aumentar de predeterminado 40 → 100 puede reducir el tiempo de AclCollection
- **Memoria de Lambda**: Se recomienda 512MB o más para Discovery Lambda (aceleración de adjunto de VPC ENI)
- **Timeout de Lambda**: Se recomienda 900s para entornos con gran cantidad de archivos (predeterminado 300s es insuficiente)
- **SnapStart**: Python 3.13 + SnapStart puede reducir el arranque en frío en 50-80%

### Nuevas funciones de Phase 8

- **Activador event-driven** (`EnableEventDriven=true`): Inicio automático al agregar archivos a S3AP
- **CloudWatch Alarms** (`EnableCloudWatchAlarms=true`): Notificación automática de fallos de SFN + errores de Lambda
- **Notificación de fallos de EventBridge**: Notificación push a SNS Topic en caso de fallo de ejecución
