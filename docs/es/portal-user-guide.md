# Portal de archivos — Guía del usuario

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | [한국어](../ko/portal-user-guide.md) | [简体中文](../zh-CN/portal-user-guide.md) | [繁體中文](../zh-TW/portal-user-guide.md) | [Français](../fr/portal-user-guide.md) | [Deutsch](../de/portal-user-guide.md) | **Español**

Guía para usuarios finales que han sido invitados a un File Portal ya desplegado. Este documento asume que un administrador del portal ha completado el despliegue y creado su cuenta — no necesita acceso a AWS CLI ni conocimientos de despliegue.

**Qué hace este portal**: Navegar archivos NAS desde el navegador, activar análisis AI/ML, ver resultados y verificar el estado de protección de datos — todo sin VPN ni configuración de cliente SMB/NFS.

---

## Primeros pasos

### 1. Iniciar sesión

1. Abra la URL del portal proporcionada por su administrador
2. Ingrese su correo electrónico y contraseña (proporcionados o auto-registrados según la configuración)
3. Si MFA está habilitado, ingrese el código TOTP de su aplicación de autenticación
4. En el primer inicio de sesión, el **Welcome Modal** le guía por 3 funcionalidades clave:
   - 📂 Navegación de archivos — Explorar archivos NAS desde el navegador
   - ⚡ Procesamiento AI — Seleccionar archivos y activar flujos de trabajo
   - 🔒 Protección de datos — Snapshots, bloqueo y estado contra ransomware

> **Consejo**: Marque "No mostrar de nuevo" para omitir el Welcome Modal en inicios de sesión posteriores.

### 2. Diseño del portal

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 ES ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ Barra lateral │  Contenido principal                    │
│ (navegación)  │                                         │
│               │                   Panel AI Assistant →  │
└───────────────┴─────────────────────────────────────────┘
```

- **Barra lateral izquierda**: Navegación agrupada en Explorar, AI & Procesamiento, Protección de datos, Administración
- **Contenido principal**: Sección activa (cambia al hacer clic en elementos de la barra lateral)
- **Panel derecho**: AI Assistant (aparece al seleccionar un archivo en All Files)
- **Barra superior**: Selector de idioma, correo del usuario, cerrar sesión

### 3. Idioma

Haga clic en el selector de idioma 🌐 en la barra superior para cambiar entre 8 idiomas: 日本語, English, 한국어, 简体中文, 繁體中文, Français, Deutsch, Español. El cambio es instantáneo — sin recarga de página.

---

## Explorar — Trabajar con archivos

### All Files

Su navegador de archivos principal. Muestra el contenido del volumen FSx for ONTAP a través de S3 Access Point.

| Acción | Cómo |
|--------|------|
| Navegar carpetas | Hacer clic en el nombre de una carpeta |
| Subir un nivel | Hacer clic en `..` en la parte superior de la lista |
| Previsualizar imágenes | Hacer clic en el icono 🖼️ junto a archivos de imagen |
| Previsualizar PDF | Hacer clic en el icono 📕 — se abre en el visor integrado del navegador |
| Previsualizar documentos Word | Hacer clic en el icono 📝 — se renderiza en el navegador |
| Descargar un archivo | Hacer clic en el icono 📄 |
| Crear un enlace para compartir | Hacer clic en 🔗 → seleccionar TTL (5 min / 15 min / 1 hora) → copiar URL |
| Consultar AI sobre un archivo | Seleccionar un archivo → escribir una pregunta en el panel AI derecho |
| Detectar objetos en imágenes | Seleccionar una imagen → hacer clic en "Detect Objects" en el panel AI |
| Procesar esta carpeta | Hacer clic en el botón ⚡ encima de la lista de archivos |

**Carpetas protegidas PHI**: Si navega a una carpeta llamada `/dicom/`, `/phi/`, `/pii/` o similar, el botón de procesamiento AI muestra `🚫 PHI — AI Blocked`. Es una barrera de seguridad — los archivos en estas carpetas no pueden enviarse a servicios AI independientemente de sus permisos.

### Favorites

Fije archivos de acceso frecuente haciendo clic en el icono ⭐ en la lista de archivos. Los archivos fijados aparecen en la sección Favorites para acceso rápido.

### Recent

Muestra los archivos que ha visto, descargado o consultado con AI recientemente, con marcas de tiempo relativas ("hace 3 min", "hace 2 h"). Solo su propio historial es visible — la actividad de otros usuarios no se muestra.

### Upload

Carga de archivos mediante arrastrar y soltar basada en Storage Browser for S3. También soporta:
- Creación de carpetas
- Copia y eliminación de archivos
- Carga de múltiples archivos (hasta 50 GB por archivo)

---

## AI & Procesamiento

### AI Processing

Active flujos de trabajo AI/ML en una carpeta o conjunto de archivos.

1. Seleccione un patrón de procesamiento del desplegable (ej.: Legal Compliance, Financial IDP, Semiconductor EDA)
2. Configure el prefijo de entrada (pre-rellenado si hizo clic en ⚡ desde All Files)
3. Haga clic en **Start Processing**
4. Será redirigido a Job History donde el estado se actualiza cada 5 segundos

### Job History

Vea todos sus trabajos de procesamiento anteriores con estado, marcas de tiempo y datos de salida.

| Estado | Significado |
|--------|-------------|
| 🔵 RUNNING | Procesamiento en curso |
| 🟢 SUCCEEDED | Completado — haga clic para ver resultados |
| 🔴 FAILED | Error ocurrido — consulte la salida para detalles |
| ⚪ TIMED_OUT | Tiempo máximo de ejecución excedido |

Haga clic en cualquier trabajo para expandir su salida. Si los resultados se escribieron de vuelta al volumen, un enlace de navegación le lleva directamente a la carpeta de salida en All Files.

### Analytics

Ejecute consultas SQL sobre sus datos con Amazon Athena. Esto requiere tablas de Glue Data Catalog preconfiguradas (establecidas por su administrador).

---

## Protección de datos

### Snapshots

Ver snapshots de volumen — copias de sus datos en un punto en el tiempo.

- **Lista**: Ver todos los snapshots disponibles con sus marcas de tiempo de creación
- **Restaurar**: Haga clic en "Restore" para crear un FlexClone (copia instantánea y eficiente en espacio) desde cualquier snapshot. El clon obtiene su propio S3 Access Point y está disponible en segundos.

### Lock (WORM)

Ver el estado de inmutabilidad de sus datos a través de tres mecanismos:

| Pestaña | Qué muestra |
|---------|-------------|
| ONTAP SnapLock | Si el volumen usa modo Compliance o Enterprise, períodos de retención |
| S3 Object Lock | Si los buckets de salida AI tienen WORM a nivel de objeto habilitado |
| Tamperproof Snapshot | Qué snapshots están bloqueados y cuándo expiran |

> **Nota**: Configurar ajustes de bloqueo requiere el rol `storage-admin`. Los usuarios regulares tienen acceso de solo lectura a esta sección.

### ARP/AI (Protección contra ransomware)

Ver el estado de protección autónoma contra ransomware de sus volúmenes.

| Qué ve | Significado |
|--------|-------------|
| 🟢 No threats | Todos los volúmenes saludables |
| 🔴 Threat detected | ARP/AI marcó actividad sospechosa |
| Incident badge | Muestra la etapa de respuesta actual (Detected → Contained → Investigating → Resolved) |

Si se detecta una amenaza y está en el grupo `storage-admin`, puede ejecutar acciones de contención directamente desde este panel.

---

## Administración (Requiere grupo `storage-admin`)

Estas secciones solo son visibles/accionables si su cuenta está en el grupo Cognito `storage-admin`.

### Storage Dashboard

Página de inicio del administrador. Cuatro tarjetas mostrando:
- 💾 Número de volúmenes + utilización promedio de capacidad
- 🛡️ Volúmenes protegidos por ARP + amenazas activas
- 🔐 Snapshots bloqueados (a prueba de manipulación)
- 📊 Ratio de eficiencia de almacenamiento

Haga clic en cualquier tarjeta para profundizar en el panel de detalles.

### Resources

Panel de administración en cuadrícula de tarjetas con 10 áreas de gestión organizadas por categoría:

| Categoría | Paneles |
|-----------|---------|
| Almacenamiento | Volumes, Qtrees, Quotas, Efficiency |
| Control de acceso | Export Policies, CIFS Shares, QoS |
| Protección | ARP Admin, Snapshot Admin, SnapLock |

### Version Diff

Comparar contenido de archivos entre dos snapshots lado a lado.

### Audit Trail

Consultar eventos de datos CloudTrail S3 para responder "quién accedió a qué, y cuándo".

---

## Consejos y preguntas frecuentes

**P: Veo "ONTAP Connection Required" en algunos paneles.**
R: El portal está en DemoMode o el administrador aún no ha configurado la conexión VPC. La navegación de archivos y las funciones AI siguen funcionando — solo los paneles específicos de ONTAP (Snapshots, ARP, Lock) necesitan la conexión.

**P: Mi botón de procesamiento AI muestra "PHI — AI Blocked".**
R: Está en una carpeta protegida (`/dicom/`, `/phi/`, `/pii/`, etc.). Esto es intencional — los archivos en estas rutas no pueden enviarse a servicios AI. Navegue a una carpeta no protegida para usar las funciones AI.

**P: Los enlaces compartidos expiran rápido.**
R: Los enlaces compartidos usan Presigned URL con un tiempo de vida que usted elige (5 min, 15 min o 1 hora). Para compartir a largo plazo, consulte con su administrador sobre la integración con Nextcloud o ajuste las opciones de TTL.

**P: Los archivos que subí por NFS/SMB no aparecen.**
R: Deberían aparecer inmediatamente (ONTAP garantiza consistencia fuerte entre protocolos). Intente actualizar la lista de archivos. Si aún faltan, el archivo puede estar en una subcarpeta — verifique la ruta.

**P: ¿Puedo usar el portal en el móvil?**
R: Sí. La barra lateral se colapsa en pantallas estrechas. Todas las funciones operan en navegadores móviles, aunque la experiencia está optimizada para escritorio.

**P: ¿Cómo cambio mi contraseña?**
R: Use la Cognito Hosted UI o solicite a su administrador que la restablezca.

---

## Documentos relacionados

| Documento | Audiencia | Propósito |
|-----------|-----------|-----------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | Administradores | Desplegar el portal desde cero |
| [Admin Demo Guide](admin-resource-management-demo.md) | Administradores de almacenamiento | Demo E2E de operaciones de administración |
| [AI Features Quick Start](ai-features-quick-start.md) | Todos los usuarios | Probar Bedrock, Rekognition, Athena |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | Desarrolladores | Arquitectura y personalización |
| [Authorization Model](portal-authorization-model.md) | Equipos de seguridad | Grupos Cognito, IAM, acceso a nivel de archivo |
| [Compliance Guide](portal-compliance-guide.md) | Seguridad/Cumplimiento | Verificar controles regulatorios |
| [Quick Reference](portal-quick-reference.md) | Todos los roles | Hoja de referencia rápida 1 página |
