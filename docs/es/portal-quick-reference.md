# Portal de archivos — Referencia rápida

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | **Español**

Hoja de referencia de una página para las operaciones diarias del portal. Imprima o guarde en favoritos.

---

## Navegación

| Sección de la barra lateral | Función |
|:---:|------|
| 📂 All Files | Explorar, previsualizar, descargar, compartir, Q&A con AI |
| ⭐ Favorites | Archivos fijados |
| 🕐 Recent | Su historial de acceso |
| 📤 Upload | Carga por arrastrar y soltar (máx. 50 GB/archivo) |
| ⚡ AI Processing | Ejecutar flujos de trabajo AI/ML en carpetas |
| 📋 Job History | Resultados de trabajos anteriores + estado |
| 📊 Analytics | Consultas SQL de Athena |
| 📸 Snapshots | Copias puntuales + restauración FlexClone |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | Estado de protección contra ransomware |
| 🔧 Resources | Paneles de administración de almacenamiento (solo admin) |
| 🔄 Version Diff | Comparar archivos entre snapshots |
| 🔍 Audit Trail | Quién accedió a qué, cuándo |

---

## Tareas comunes (todos los usuarios)

| Quiero... | Cómo hacerlo |
|-----------|-------------|
| Explorar archivos | Barra lateral → 📂 All Files → clic en carpetas |
| Previsualizar un PDF | Clic en 📕 junto al archivo |
| Previsualizar un documento Word | Clic en 📝 junto al archivo |
| Descargar un archivo | Clic en 📄 junto al archivo |
| Compartir un enlace de archivo | Clic en 🔗 → elegir TTL → copiar URL |
| Preguntar a la AI sobre un archivo | Seleccionar archivo → escribir pregunta en el panel derecho |
| Detectar objetos en una imagen | Seleccionar imagen → "Detect Objects" en el panel derecho |
| Subir archivos | Barra lateral → 📤 Upload → arrastrar y soltar |
| Ejecutar AI en una carpeta | En All Files, clic en ⚡ sobre la lista de archivos |
| Ver resultados de un trabajo | Barra lateral → 📋 Job History → clic en un trabajo |
| Restaurar desde un snapshot | Barra lateral → 📸 Snapshots → botón "Restore" |
| Cambiar idioma | Clic en 🌐 en la barra superior |

---

## Tareas comunes (Cumplimiento / Seguridad)

| Quiero... | Cómo hacerlo |
|-----------|-------------|
| Verificar estado anti-ransomware | Barra lateral → 🛡️ ARP/AI |
| Verificar bloqueos WORM | Barra lateral → 🔒 Lock → pestaña SnapLock |
| Verificar bloqueo del bucket de salida | Barra lateral → 🔒 Lock → pestaña S3 Object Lock |
| Ver snapshots bloqueados | Barra lateral → 🔒 Lock → pestaña Tamperproof |
| Revisar auditoría de acceso | Barra lateral → 🔍 Audit Trail |
| Verificar guardián PHI | All Files → navegar a `/dicom/` → botón muestra 🚫 |

---

## Tareas comunes (Administrador de almacenamiento)

| Quiero... | Cómo hacerlo |
|-----------|-------------|
| Ver panel de estado | Barra lateral → 🔧 Resources (el panel aparece primero) |
| Gestionar volúmenes | Resources → Storage → Volumes |
| Configurar políticas de exportación | Resources → Access Control → Export Policies |
| Habilitar ARP en volúmenes | Resources → Protection → ARP Admin |
| Bloquear un snapshot | Resources → Protection → Snapshot Admin → formulario Lock |
| Bloquear un usuario comprometido | Barra lateral → 🛡️ ARP/AI → pestaña Contain → Block SMB User |
| Desbloquear tras resolución | Barra lateral → 🛡️ ARP/AI → pestaña Unblock |
| Ver alertas EMS | Resources → (eventos EMS en monitoreo) |

---

## Atajos de teclado

| Tecla | Acción |
|-------|--------|
| `Tab` | Mover entre elementos interactivos |
| `Enter` | Activar botón / abrir carpeta |
| `Escape` | Cerrar modal / cerrar panel |

---

## Indicadores de estado

| Icono | Significado |
|:---:|---------|
| 🟢 | Saludable / Sin amenazas / Resuelto |
| 🔴 | Amenaza detectada / Error |
| 🟠 | Contenido (incidente en curso) |
| 🟡 | En investigación |
| 🚫 | PHI — AI bloqueado (guardián activo) |
| ⚠️ | Advertencia (capacidad > 85 %, etc.) |

---

## Niveles de acceso

| Grupo | Puede hacer | No puede hacer |
|-------|------------|----------------|
| `authenticated` | Explorar, descargar, subir, AI, ver estado de protección | Modificar configuración de almacenamiento |
| `storage-admin` | Todo lo anterior + crear/eliminar volúmenes, bloquear snapshots, bloquear usuarios, gestionar políticas | — |

---

## Solución rápida de problemas

| Síntoma | Solución |
|---------|----------|
| "ONTAP Connection Required" | Normal en DemoMode. Pida al admin que configure VPC. |
| El botón AI muestra 🚫 | Está en una carpeta protegida de PHI. Navegue a otra ubicación. |
| Enlace compartido expirado | Genere uno nuevo (🔗). TTL máximo = 1 hora. |
| Archivo no visible tras escritura NFS | Actualice la lista de archivos. Debería aparecer inmediatamente. |
| Carga infinita | Verifique internet. Intente cerrar sesión → iniciar sesión. |

---

## Mapa de documentación

| Su rol | Comience aquí |
|--------|--------------|
| Usuario final (tareas diarias) | [Guía del usuario](portal-user-guide.md) |
| Seguridad / Cumplimiento | [Guía de cumplimiento](portal-compliance-guide.md) |
| Administrador de almacenamiento | [Guía de demostración admin](admin-resource-management-demo.md) |
| Administrador IT (despliegue) | [Guía de inicio](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| Desarrollador (personalizar) | [Guía de implementación](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
