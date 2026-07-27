# Portal de archivos — Guía de seguridad y cumplimiento

> 🌐 Language: [English](../en/portal-compliance-guide.md) | [日本語](../ja/portal-compliance-guide.md) | [한국어](../ko/portal-compliance-guide.md) | [简体中文](../zh-CN/portal-compliance-guide.md) | [繁體中文](../zh-TW/portal-compliance-guide.md) | [Français](../fr/portal-compliance-guide.md) | [Deutsch](../de/portal-compliance-guide.md) | **Español**

Guía para oficiales de seguridad, analistas de cumplimiento y personal de protección de datos que necesitan **verificar** los controles regulatorios a través del portal sin realizar administración de almacenamiento. No necesita privilegios de `storage-admin` — todas las tareas a continuación utilizan acceso de solo lectura.

---

## Su rol en el portal

| Lo que puede hacer | Ubicación en el portal |
|-------------------|------------------------|
| Verificar el estado de protección contra ransomware | Barra lateral → 🛡️ ARP/AI |
| Confirmar bloqueo de snapshots y períodos de retención | Barra lateral → 🔒 Lock |
| Revisar la pista de auditoría (quién accedió a qué) | Barra lateral → 🔍 Audit Trail |
| Verificar la aplicación del guardián PHI | Barra lateral → 📂 All Files (navegar a `/dicom/` o `/phi/`) |
| Verificar S3 Object Lock en buckets de salida | Barra lateral → 🔒 Lock → pestaña S3 Object Lock |
| Ver alertas EMS (eventos del sistema ONTAP) | Admin → Resources (solo lectura si no es `storage-admin`) |

> **Nota**: No puede cambiar configuraciones (ajustes de bloqueo, estado ARP, políticas de exportación). Si necesita cambios, solicítelos a un usuario `storage-admin`.

---

## Tarea 1: Verificar la protección contra ransomware (ARP/AI)

**Contexto regulatorio**: FISC, NIST CSF DE.CM-4, ISO 27001 A.12.2

1. Haga clic en **🛡️ ARP/AI** en la barra lateral
2. Confirme que cada volumen monitoreado muestra un estado verde (🟢 Sin amenazas)
3. Si aparece un indicador de amenaza (🔴), anote el nombre del volumen y la marca de tiempo de detección
4. Verifique el **indicador del ciclo de vida del incidente** para la etapa de respuesta actual:
   - 🔴 Detectado — Amenaza identificada, esperando contención
   - 🟠 Contenido — Acceso del atacante bloqueado, snapshot preservado
   - 🟡 En investigación — Análisis forense en curso
   - 🟢 Resuelto — Incidente cerrado

**Evidencia para auditores**: Capture pantalla del panel ARP mostrando el estado de protección de todos los volúmenes + indicadores de incidentes activos con marcas de tiempo.

---

## Tarea 2: Confirmar la inmutabilidad de snapshots (WORM)

**Contexto regulatorio**: SEC 17a-4, FISC 7 años de retención, HIPAA 6 años, SOX 5 años, NARA

1. Haga clic en **🔒 Lock** en la barra lateral
2. Revise tres pestañas:

### Pestaña A: ONTAP SnapLock
- Verifique el tipo de volumen: **Compliance** (nadie puede eliminar, incluido root) o **Enterprise** (el administrador puede liberar)
- Compruebe que los períodos de retención coinciden con su política:
  - Período mínimo ≥ requisito regulatorio
  - Compliance Clock está inicializado y en ejecución

### Pestaña B: S3 Object Lock
- Verifique que Object Lock está habilitado en el bucket de salida
- Confirme el modo: **Compliance** para archivos regulatorios, **Governance** para salidas de AI
- Compruebe que los días de retención predeterminados coinciden con su requisito

### Pestaña C: Tamperproof Snapshots
- Revise la tabla de snapshots bloqueados: nombre, hora de creación, hora de expiración
- Verifique que las fechas de expiración se alinean con la retención regulatoria:

| Regulación | Retención requerida | Expiración esperada |
|-----------|--------------------|--------------------|
| FISC | 7 años (2.557 días) | Creación + 7 años |
| HIPAA | 6 años (2.192 días) | Creación + 6 años |
| SOX/J-SOX | 5 años (1.825 días) | Creación + 5 años |
| NARA | 3-75 años (variable) | Según calendario de retención |

**Evidencia para auditores**: Capture pantalla de cada pestaña mostrando el estado de bloqueo + períodos de retención.

---

## Tarea 3: Revisar la pista de auditoría

**Contexto regulatorio**: FISC, SOX Section 302/404, HIPAA §164.312(b), PCI DSS 10.x

1. Haga clic en **🔍 Audit Trail** en la barra lateral
2. El panel muestra los eventos de datos S3 de CloudTrail para el S3 Access Point
3. Campos clave a revisar:
   - **Quién**: Principal IAM (identidad de usuario Cognito)
   - **Cuándo**: Marca de tiempo del evento (UTC)
   - **Qué**: Acción API (`GetObject`, `PutObject`, `ListObjectsV2`)
   - **Qué archivo**: Clave S3 (ruta del archivo)
4. Filtre por rango de fechas o usuario si investiga un incidente específico

**Evidencia para auditores**: Exporte o capture la pista de auditoría filtrada por el período de revisión.

---

## Tarea 4: Verificar el guardián PHI

**Contexto regulatorio**: HIPAA §164.502 (mínimo necesario), 45 CFR 164.514

1. Haga clic en **📂 All Files** en la barra lateral
2. Navegue a una carpeta llamada `/dicom/`, `/phi/`, `/pii/` o `/hipaa/`
3. Observe que el botón de procesamiento AI muestra: **🚫 PHI — AI Blocked**
4. Verifique que el botón está deshabilitado (no se puede hacer clic independientemente del rol)

**Significado**: Los archivos en estas rutas protegidas están estructuralmente impedidos de ser enviados a servicios AI externos (Bedrock, Rekognition, Textract, Comprehend). Esto se aplica en la capa de interfaz de usuario mediante coincidencia de patrones de ruta y no puede ser anulado por ningún usuario.

**Limitación**: Este guardián depende de las convenciones de nomenclatura de carpetas. Los archivos con contenido PHI colocados en rutas no protegidas NO se bloquean. Asegúrese de que las políticas de estructura de carpetas de la organización se apliquen aguas arriba.

**Evidencia para auditores**: Captura de pantalla mostrando el botón AI deshabilitado en una carpeta `/dicom/`.

---

## Tarea 5: Verificar S3 Object Lock en salidas de AI

**Contexto regulatorio**: SEC 17a-4(f), CFTC 1.31, FINRA 4511

1. Haga clic en **🔒 Lock** → pestaña **S3 Object Lock**
2. Verifique:
   - Object Lock está **habilitado** en el bucket de salida
   - El modo es apropiado: **Compliance** (inmutable) para archivos regulatorios o **Governance** (anulable con permiso) para salidas de AI
   - El período de retención predeterminado coincide con su calendario de retención
3. Si Object Lock no está configurado, escale a un usuario `storage-admin`

**Por qué es importante**: Los resultados de procesamiento AI (etiquetas de clasificación, texto extraído, informes de cumplimiento) almacenados en S3 pueden ser en sí mismos registros regulatorios. Object Lock asegura que estas salidas no puedan ser alteradas o eliminadas durante el período de retención.

---

## Tarea 6: Verificación de respuesta a incidentes

Cuando se detecta un incidente de ransomware:

1. Vaya a **🛡️ ARP/AI** → verifique el estado del indicador de incidente
2. Verifique que la contención se ejecutó:
   - Snapshot tomado (evidencia preservada)
   - Usuario/IP sospechoso bloqueado
3. Vaya a **🔍 Audit Trail** → filtre eventos alrededor de la marca de tiempo de detección
4. Documente la línea de tiempo: detección → contención → inicio de investigación
5. Después de la resolución, verifique que el indicador muestre 🟢 Resuelto

**Referencia SLA de la línea de tiempo del incidente**:

| Fase | Duración típica | Su SLA |
|------|:---:|:---:|
| Detección → Contención | < 5 minutos (automatizado) | _____ |
| Contención → Inicio de investigación | < 1 hora | _____ |
| Investigación → Resolución | Según el caso | _____ |

---

## Mapeo regulatorio

| Función del portal | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|-------------------|:---:|:---:|:---:|:---:|:---:|
| Detección de ransomware ARP/AI | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (modo Compliance) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Guardián PHI | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| Seguimiento del ciclo de vida de incidentes | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## Lo que no puede hacer (y quién puede)

| Acción | Grupo requerido | A quién contactar |
|--------|:---:|---------|
| Cambiar el estado de ARP/AI | `storage-admin` | Administrador de almacenamiento |
| Bloquear/desbloquear snapshots | `storage-admin` | Administrador de almacenamiento |
| Configurar S3 Object Lock | `storage-admin` | Administrador de almacenamiento |
| Bloquear/desbloquear usuarios (contención) | `storage-admin` | Operaciones de seguridad + admin de almacenamiento |
| Crear/eliminar volúmenes | `storage-admin` | Administrador de almacenamiento |
| Modificar políticas de exportación | `storage-admin` | Administrador de almacenamiento |

---

## Documentos relacionados

| Documento | Propósito |
|-----------|-----------|
| [Guía del usuario](portal-user-guide.md) | Operaciones diarias del usuario |
| [Modelo de autorización](portal-authorization-model.md) | Matriz completa de permisos |
| [Guía de demostración admin](admin-resource-management-demo.md) | Operaciones de administración de almacenamiento |
| [Playbook de respuesta a incidentes](../../docs/incident-response-playbook.md) | Procedimientos completos de respuesta a incidentes |
| [Referencia rápida](portal-quick-reference.md) | Resumen de 1 página |
