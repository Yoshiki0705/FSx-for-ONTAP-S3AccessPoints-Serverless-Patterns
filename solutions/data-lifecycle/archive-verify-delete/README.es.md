# archive-verify-delete: archivado solo con llamadas a la API de S3, copia, verificación y borrado tras la aprobación
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español
📚 **Documentación**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Descripción general
Este patrón mueve a clases de almacenamiento S3 Glacier los archivos que se leen pocas veces de un volumen de Amazon FSx for NetApp ONTAP (FSx for ONTAP). La lectura, la escritura y el borrado de archivos usan la API de S3 de S3 Access Points; para eso no se monta NFS. Dos cosas sí necesitan algo más: seleccionar por hora del último acceso (`selection=ATIME`) y capturar atributos usan la API REST de ONTAP (una función Lambda dentro de la VPC, credenciales de ONTAP, el punto de enlace de administración), y devolver propietario, modo y hora de modificación después de una restauración requiere un host que monte el volumen por NFS.
Cada archivo sigue los pasos siguientes. Un archivo cuyas condiciones dejan de cumplirse en cualquier paso sale del conjunto que se va a borrar.
1. Registrar su tamaño, ETag, SHA-256 y CRC64NVME en el libro de registro (una tabla de DynamoDB)
2. Copiarlo al bucket de archivo con `CopyObject`, indicando la clase de almacenamiento (clave `<prefix><runId>/<original key>`)
3. Comparar la suma de comprobación que devuelve el bucket con el libro de registro
4. Una persona aprueba la lista de archivos que coinciden. La aprobación se registra en el libro de registro como `APPROVED` y se rechaza cuando quien aprueba es la misma entidad principal que inició la ejecución (valor por defecto)
5. Solo se borran los archivos que el libro de registro muestra como `APPROVED`, tras comprobar que el ETag y el tamaño en el Access Point siguen siendo iguales a los del libro de registro

Para restaurar, el patrón busca los archivos en el libro de registro, solicita la restauración en el bucket, espera a que termine, copia los archivos de vuelta al Access Point con `CopyObject` y después lee cada archivo restaurado y lo compara con el SHA-256 y el CRC64NVME del libro de registro.
Este patrón no usa S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock ni el bloqueo de instantáneas, y la plantilla no contiene ninguno. No se establece ningún período de retención, de modo que los objetos del bucket de archivo pueden ser borrados por quien tenga permiso.
Las premisas de este patrón y su comparación con otros enfoques están en [Comparación de 8 mecanismos para mover archivos a clases de archivo](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md).
## Qué se midió y qué no
| Categoría | Contenido |
|---|---|
| Componentes comprobados una vez cada uno en un entorno real (registrados en la comparación anterior; 2026-11-24 y 2026-11-26, ap-northeast-1, primera generación `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, volumen de estilo UNIX, el usuario del Access Point es UNIX root) | Con `ChecksumAlgorithm=SHA256` en `CopyObject`, el `ChecksumSHA256` del bucket fue `FULL_OBJECT` e igual al SHA-256 del archivo (hasta 8 MiB). En una copia multiparte de 5,5 GiB, el SHA-256 pasó a ser `COMPOSITE` y el CRC64NVME fue `FULL_OBJECT` e igual. `--copy-source-if-match` con un ETag antiguo devolvió `PreconditionFailed`. El `DeleteObject` del Access Point no admite `If-Match`. Una integración SDK de Step Functions aceptó el alias del Access Point como `Bucket` |
| Comprobado en este repositorio | Pruebas unitarias con moto y pruebas de la estructura de la máquina de estados y de IAM. Sin conexión a AWS. Seis defectos encontrados en las ejecuciones de extremo a extremo (permiso de invocación de la función de la API REST de ONTAP, verificación TLS, nombre del error de una solicitud de restauración duplicada, permiso de registro de las máquinas de estados, el 403 de `HeadObject`, permiso de publicación de las alarmas) se corrigieron con pruebas que los reproducen |
| Comprobado una vez cada uno en una ejecución de extremo a extremo en un entorno real (2026-11-26, mismo entorno que arriba, `selection=ATIME`, `GLACIER`, 7 archivos) | Selección por `accessed_time` y captura de uid, gid, mode, mtime y atime mediante la API REST de ONTAP (la raíz es la raíz del volumen y la ruta no lleva barra inicial; `unix_permissions` vuelve como el entero `640`). El `ItemReader` y el `ResultWriter` de Distributed Map. Una copia multiparte de 5,5 GiB con Fargate (con `CopySourceIfMatch`; CRC64NVME igual al del libro de registro). El cálculo del hash de un archivo de 5,3 GB (unos 4,94 GiB) en Lambda (69,8 s, 2048 MB configurados, 152 MB usados). La segunda copia. El borrado tras la aprobación. Un archivo reescrito por NFS mientras la ejecución esperaba la aprobación pasó a `CHANGED` y no se borró. Una aprobación rechazada no borró nada. La restauración con `Expedited` (incluido el archivo de 5,5 GiB) y un SHA-256 igual en los 6 archivos restaurados (el séptimo de los 7 archivos se había reescrito, así que no se borró ni se restauró). La recuperación de uid, gid, mode y mtime con `reapply.sh` |
| Comprobado una vez cada uno en una segunda ejecución de extremo a extremo (2026-11-26, mismo entorno, `GLACIER`, segunda copia activada. Ejecución de prueba con `selection=ATIME`, ejecución real con `selection=MTIME` y atributos de la API REST de ONTAP. Archivos de 64 B a 1 MiB y un archivo disperso de 51 GiB) | El comportamiento cambió tras la revisión. Con `maxFiles=50`, tres archivos de 64 B y uno de 131.071 B quedaron por debajo del tamaño mínimo y uno de 131.073 B se mantuvo. Se excluyeron `*.vmdk` y un prefijo de retención legal. El archivo disperso de 51 GiB se registró como `SKIPPED_TOO_LARGE` y no se copió. Un `runId` reutilizado y una entrada de ejecución real sin `requestedBy` se detuvieron como errores de entrada. Una aprobación con el mismo ARN que quien inició la ejecución terminó como `APPROVAL_REFUSED` y no se borró nada. Invocar directamente la función `delete` sin aprobación devolvió `NOT_APPROVED` y no borró nada. Con otro aprobador se borraron 3 archivos y el archivo reescrito durante la espera quedó como `CHANGED`. En elementos puestos en `DELETING` para simular una interrupción, un reintento de la misma ejecución registró `DELETED` (`already gone on retry`), otra ejecución fue rechazada y `reconcile` registró `DELETED`. Tras la restauración, 3 archivos quedaron como `RESTORE_VERIFIED`. Las alarmas se publicaron en el tema cifrado con KMS (tras una corrección) |
### Entorno y resultado de cada paso
El entorno es ap-northeast-1, FSx for ONTAP de primera generación `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, un volumen con estilo de seguridad UNIX y un Access Point cuyo usuario del sistema de archivos es UNIX root. La fecha es 2026-11-26 (horas en hora estándar de Japón) y cada paso se ejecutó una sola vez. La configuración fue `selection=ATIME`, `GLACIER`, una segunda copia y Fargate en arm64 con 2 vCPU y 8 GiB. Los datos fueron 6 archivos pequeños (tres de 64 B y tres de 8 MiB, propietario 1234:5678, modo 640, mtime y atime del 2020-01-02) y un archivo de 5.905.580.032 B.
| Paso | Resultado | Duración |
|---|---|---|
| 1. Desplegar | Correcto. Dos defectos descubiertos al ejecutar se corrigieron y se volvió a desplegar | Unos 30 minutos desde la preparación hasta el despliegue (16:19 a 16:50) |
| 2. Ejecución de prueba (`dryRun=true`) | Correcta tras las correcciones. Los 7 archivos en `VERIFIED` (SHA-256 igual en 6, CRC64NVME igual en 1) y la segunda copia también en `VERIFIED`. 0 bytes borrados y los 7 archivos siguieron presentes por NFS | 244 s (incluidos unos 70 s de espera de la aprobación) |
| 3. Reescritura durante la espera de la aprobación | Un archivo se sobrescribió por NFS con 4 KiB del mismo tamaño (mtime actualizado). Tras la aprobación pasó a `CHANGED` (el ETag o el tamaño difieren) y no se borró | |
| 4. Ejecución real (`dryRun=false`) y aprobación | 6 archivos en `DELETED` y 1 en `CHANGED`. `bytesDeleted` fue 5.922.357.440. Por NFS desaparecieron los 6 archivos y solo quedó el reescrito | 310 s (172 s hasta la solicitud de aprobación, unos 6 s de la aprobación al final) |
| 5. Restauración (`tier=Expedited`, `days=1`) | 6 archivos en `RESTORED` (incluido el de 5,5 GiB). SHA-256 igual en los 6 al valor registrado por NFS antes del paso 1. El archivo `CHANGED` no era destino | 287 s (los 5 archivos pequeños en unos 2,5 minutos; la copia de 5,5 GiB con Fargate tardó 2 min 38 s) |
| 6. Aprobación rechazada (`send-task-failure`) | La ejecución terminó como `REJECTED_OR_TIMED_OUT`, 3 archivos siguieron en `VERIFIED`, `deletedBy` estaba vacío y los 3 archivos siguieron presentes por NFS | 16 s |
| Adicional: hash de 5,3 GB (unos 4,94 GiB) en Lambda | `VERIFIED` (SHA-256 igual al valor de NFS) y la segunda copia también `VERIFIED` | Función `record` 69,8 s (2048 MB configurados, 152 MB usados) |
| Adicional: solicitud de restauración duplicada | La segunda solicitud devolvió HTTP 409 `RestoreAlreadyInProgress`. La integración SDK de Step Functions lo devuelve como `S3.S3Exception` | |
Después se eliminaron todos los recursos y la eliminación se confirmó leyéndolos de nuevo.
### Consumo (una ejecución de cada tipo, no es una factura)
| Ejecución | Archivos | Duración | Transiciones de estado (padre + ejecuciones hijas del Map) | Tareas de Fargate |
|---|---|---|---|---|
| De prueba | 7 | 244 s | 12 + 107 = 119 | 2 (hash y copia 96 s, segunda copia 35 s) |
| Real | 7 | 310 s | 13 + 114 = 127 | 2 (94 s, 35 s) |
| Restauración | 6 | 287 s | 4 + 103 = 107 | 1 (156 s) |
| Rechazo | 3 | 16 s | 10 + 45 = 55 | 0 |
- Duración total de las funciones Lambda (CloudWatch; incluye las invocaciones fallidas y excluye la ejecución de 4,94 GiB): `select` 13 invocaciones 5,9 s, `ontap_rest` 11 invocaciones 13,4 s (2 fallidas), `record` 17 invocaciones 11,7 s, `ledger` 34 invocaciones 9,1 s, `approval` 6 invocaciones 4,3 s, `delete` 7 invocaciones 5,6 s, `summarize` 5 invocaciones 5,1 s, `restore` 26 invocaciones 9,2 s
- Fargate: 5 tareas, unos 416 s en total (2 vCPU, 8 GiB, arm64). DynamoDB (bajo demanda): 68,5 RCU leídas y 74 WCU escritas, sumadas en todas las ejecuciones
- No se midió el número de solicitudes a S3 (las métricas de solicitudes no estaban activadas)
Transiciones de estado en la segunda ejecución (2026-11-26, archivos pequeños, segunda copia activada, `MapConcurrency=2`), una ejecución de cada tipo; varían con el tamaño de los archivos y la ruta.

| Ejecución | Archivos | Duración | Transiciones de estado (padre + ejecuciones hijas del Map) | Por archivo |
|---|---|---|---|---|
| de prueba `e2e2-dry1` | 4 | 66 s (incluidos unos 20 s de espera de la aprobación) | 12 + 60 = 72 | 18 |
| real `e2e2-real2` (3 borrados, 1 `CHANGED`) | 4 | 45 s (incluida la espera de la aprobación) | 14 + 64 = 78 | 19,5 |
| restauración `e2e2-rest2` (Expedited, con verificación, 1 `EXISTS`) | 4 | 192 s | 4 + 52 = 56 | 14 |
### Defectos encontrados y corregidos en las ejecuciones de extremo a extremo
Cada uno se corrigió con una prueba que lo reproduce.
| # | Síntoma | Causa y corrección |
|---|---|---|
| 1 | Una ejecución con `selection=ATIME` falló en el paso de selección | Al rol de la máquina de estados de archivo le faltaba `lambda:InvokeFunction` sobre la función de la API REST de ONTAP. Se añadió el permiso |
| 2 | La función de la API REST de ONTAP falló con `CERTIFICATE_VERIFY_FAILED` | Siempre verificaba TLS, pero el certificado del punto de enlace de administración de FSx for ONTAP no está firmado por una CA pública. Se añadió el parámetro `OntapVerifySsl` (por defecto `false`) |
| 3 | Una solicitud de restauración duplicada se convirtió en un fallo de archivo | La integración SDK de Step Functions devuelve `RestoreAlreadyInProgress` como `S3.S3Exception`, de modo que el `Catch` de `S3.RestoreAlreadyInProgressException` no coincidía. Ahora una restauración en curso se dirige al bucle de espera |
La segunda ejecución (2026-11-26) encontró y corrigió otros tres.

| # | Síntoma | Causa y corrección |
|---|---|---|
| 4 | El despliegue falló con `The state machine IAM Role is not authorized to access the Log Destination` | A los roles de las máquinas de estados les faltaban `logs:CreateLogDelivery` y los permisos relacionados que necesita el registro de ejecuciones. Se añadieron |
| 5 | Un reintento de borrado y `reconcile` recibieron 403 de `HeadObject` sobre un archivo ya borrado | Para quien llama sin `s3:ListBucket`, `HeadObject` sobre una clave inexistente devuelve 403 y no 404. Se añadió `s3:ListBucket` a las funciones `delete` y `restore`, en IAM y en la política del Access Point |
| 6 | Las notificaciones de las alarmas de CloudWatch fallaron con `CloudWatch Alarms is not authorized to perform: SNS:Publish` | La política de la clave permitía a CloudWatch, pero la política del tema solo permitía a EventBridge. Se añadió una instrucción para `cloudwatch.amazonaws.com` |
### Comportamientos vistos en la ejecución de extremo a extremo
Estos comportamientos no se trataron como defectos.
- Con `selection=ATIME`, las propias lecturas del patrón actualizan `accessed_time`. Tras una ejecución con `dryRun=true`, la lectura del cálculo del hash deja el atime de cada archivo en la hora de ejecución, así que la misma entrada con `dryRun=false` no selecciona nada (terminó con 0 archivos cuando la ejecución real siguió a la de prueba). Para ejecutar la pasada real sobre los mismos candidatos justo después de una ejecución de prueba, use `selection=MTIME` (`LastModified` no cambia al leer)
- Sobre el ETag, la redacción oficial y la medición de aquí son las siguientes. La página oficial ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), leída el 2026-11-26) dice "The ETag reflects changes only to the contents of an object, not its metadata". En una medición en este entorno, tres archivos con el mismo tamaño y el mismo mtime y contenidos distintos devolvieron el mismo ETag. Por eso el patrón considera que la comprobación de ETag y tamaño antes del borrado no detecta un cambio de contenido que conserve el tamaño y el mtime. Una reescritura del mismo tamaño que actualizó el mtime durante la espera de la aprobación sí se detectó (paso 3 de la primera ejecución y la segunda ejecución real)
- Al borrar por el Access Point el último archivo de un directorio, también desaparece el directorio padre que queda vacío (visto con `arc-e2e/large/`). El `CopyObject` de la restauración lo vuelve a crear
- Los archivos restaurados tenían propietario 0:1, modo 644 y, como mtime, la hora de la restauración. Al ejecutar como root el `reapply.sh` generado, en un host que monta el volumen por NFS, se recuperaron los uid, gid, mode y mtime originales (1234:5678, 640, 2020-01-02 03:04:05) sin cambiar el SHA-256 del contenido
- La máquina de estados de restauración también selecciona un archivo que quedó como `CHANGED` cuando el bucket de archivo conserva su copia. Si el Access Point ya tiene la clave, queda como `EXISTS` y no se sobrescribe (visto una vez en la segunda restauración)
- La solicitud de restauración `Expedited` del archivo de 5,5 GiB fue aceptada y terminó en unos 4 minutos o menos
### Puntos no comprobados
- Duración y coste con muchos archivos. Rendimiento del sistema de archivos y latencia de los clientes con otros ajustes de concurrencia
- Finalización de las restauraciones `Standard` y `Bulk` (solo se ejecutó `Expedited`)
- Reintento ante `S3.SlowDownException` (no se observó el nombre que devuelve la integración SDK; puede darse una discrepancia del mismo tipo que el defecto 3)
- Borrados y aprobaciones en los eventos de datos de CloudTrail. Los eventos de datos de S3 (`DeleteObject` y otros) se registran solo cuando un trail tiene activados los eventos de datos. En esta ejecución no se comprobó si el trail de la cuenta incluye los eventos de datos de este Access Point. `SendTaskSuccess` es un evento de administración; tampoco se comprobó su registro
- El rechazo y la aceptación de una aprobación se compararon con la misma entidad principal de SSO declarando ARN distintos en la salida de la aprobación. El valor de `approver` es declarado, así que otra entidad principal de IAM debería dar el mismo resultado, pero no se usó una segunda entidad principal real
- Copia y restauración de archivos de más de 50 GiB (solo se comprobó que quedan fuera de la selección, con un archivo disperso)
- Volúmenes NTFS, usuarios distintos de root, segunda generación, Multi-AZ
- En la restauración, la ruta `EXISTS` aparte de no seleccionar archivos `CHANGED` (un archivo con el mismo nombre en NFS)
- Esperar hasta que `ApprovalPendingAlarm` pase realmente a `ALARM` (solo se comprobó que la métrica se publica)
- Queda sin explicación un caso de cero candidatos. Una ejecución unos 10 segundos después de restablecer el atime con `touch -d` no encontró candidatos. Una comprobación unos 17 minutos después devolvió los valores de 2020, y otras comprobaciones también devolvieron 6 archivos. No se identificó la causa y no se repitió
### Ventana de escritura que queda antes del borrado
En la comprobación previa al borrado queda una ventana de escritura. El `DeleteObject` del Access Point no admite el borrado condicional, por lo que una escritura entre la comprobación con `HeadObject` y el borrado no se detecta. La ventana equivale a una ida y vuelta de llamada a la API.
## Flujo
### Archivado
`olderThanDays` es obligatorio. `dryRun` es `true` por defecto. Una ejecución con `dryRun=false` necesita el ARN de la entidad principal que la inicia en `requestedBy` cuando `RequireSeparateApprover=true` (valor por defecto).
| Paso | Procesamiento | Implementación |
|---|---|---|
| 1. Seleccionar | `MTIME`: `LastModified` del `ListObjectsV2` del Access Point. `ATIME`: `accessed_time` de la API REST de ONTAP (Lambda dentro de la VPC). Aplicar las exclusiones (tabla siguiente) | `select`, `ontap_rest` |
| 2. Registrar | Tamaño, ETag, SHA-256, CRC64NVME y, si están disponibles, uid, gid, mode, mtime, atime, en el libro de registro. Lambda hasta 5 GiB, Fargate por encima | `record`, tarea de Fargate |
| 3. Copiar | Hasta 5 GiB: `copyObject` de la integración SDK (`SHA256`, el ETag del libro de registro como `CopySourceIfMatch`). Por encima: copia multiparte con Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Verificar | Comparar el tamaño y la suma de comprobación del `HeadObject` del bucket (`ChecksumMode=ENABLED`) con el libro de registro. Una diferencia queda como `MISMATCH` y el archivo sale del conjunto que se va a borrar | `ledger` |
| 5. Segunda copia (opcional) | Copiar desde el Access Point a otro bucket de la misma región y verificar de la misma forma. Una diferencia saca el archivo del conjunto que se va a borrar | Step Functions, `ledger` |
| 6. Aprobar | Escribir la lista de coincidencias en `manifests/<runId>.json`, notificar por SNS y esperar con `waitForTaskToken`. La notificación indica cuándo solo hay una copia y cuándo los archivos no se pueden restaurar | `approval` |
| 7. Registrar la aprobación | Solo con `dryRun=false`. Rechazar cuando quien aprueba es quien inició la ejecución. En caso contrario, pasar cada archivo de la lista de `VERIFIED` a `APPROVED` en el libro de registro y escribir `manifests/<runId>-approval.json` | `approval` |
| 8. Borrar | Solo los archivos que el libro de registro muestra como `APPROVED`. Comprobar ETag y tamaño por archivo; `DeleteObject` si no han cambiado y, si no, mantener como `CHANGED` | `delete` |
| 9. Registrar | `manifests/<runId>-result.json` y métricas EMF (recuentos, bytes, exclusiones). `COMPLETED_WITH_ERRORS` cuando quedan elementos `DELETING` o `APPROVED` | `summarize` |
Con `dryRun=true` la ejecución llega igualmente hasta el paso 6. Se realizan las copias y se factura el almacenamiento de la clase de archivo (con una duración mínima de almacenamiento). Para probar, use un `maxFiles` pequeño. No se borra nada.
Los estados del libro de registro avanzan en el orden `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED`, con las salidas laterales `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE` y `RESTORE_MISMATCH`. Solo se pueden borrar los archivos `APPROVED` (y, cuando se exige una segunda copia, aquellos cuya segunda copia también está verificada).

Un `runId` que ya se usó es un error de entrada. Para continuar una ejecución interrumpida, indique el mismo `runId` con `"resume": true` (véase «Recuperación tras un borrado interrumpido» más abajo). La clave de archivo lleva el `runId`, de modo que una ejecución de prueba y una real, o un nuevo archivado tras una reescritura, no se sobrescriben entre sí. Sin control de versiones, una sobrescritura borra el objeto anterior, lo que puede suponer un cargo por borrado anticipado en las clases con duración mínima de almacenamiento.

Lo que la selección deja fuera:

| Condición | Valor por defecto | Motivo |
|---|---|---|
| Más de 50 GiB | Se deja fuera y se registra como `SKIPPED_TOO_LARGE` en el libro de registro. `allowOversize: true` los incluye | La página oficial ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), leída el 2026-11-26) dice "Maximum object size is 50 GiB for uploads, but you can download objects larger than that". Una restauración escribe a través del Access Point, por lo que este patrón no puede restaurar allí un archivo mayor (se puede descargar directamente del bucket) |
| Menos de `MinFileSizeBytes` | 131.072 bytes (128 KiB). El `minSizeBytes` de la entrada lo cambia | Según [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare) (leída el 2026-11-26), Standard-IA y Glacier Instant Retrieval facturan al menos 128 KB por objeto, y Glacier Flexible Retrieval y Deep Archive añaden 40 KB de metadatos por objeto (32 KB a la tarifa de esa clase y 8 KB a la tarifa de Standard). En archivos pequeños eso supera a los propios datos |
| `ExcludePatterns` (globs), `ExcludePrefixes` | Vacío | Los valores de la pila siempre se aplican; `excludePatterns` y `excludePrefixes` de la entrada solo pueden añadir. Ponga aquí los prefijos con retención legal |

Excluya siempre los archivos de datos de tablas Iceberg, Delta o Hive, los archivos de una base de datos en ejecución y las imágenes de disco de máquinas virtuales (`*.vmdk`, `*.vhd`, `*.qcow2` y similares). El patrón mueve los archivos uno a uno y no sabe nada de los metadatos de las tablas ni del proceso que mantiene abierto un archivo. Ordene una tabla con las funciones propias de la tabla (desasociar particiones, expirar instantáneas) y tome como destino solo las rutas que queden después. Si algo está bajo retención legal lo decide su equipo jurídico; el patrón no lo decide.
### Restauración
La entrada es `runId` y exactamente uno de `keys` o `prefix`. `tier` (`Bulk` por defecto) y `days` (7 por defecto) son opcionales.
1. Seleccionar en el libro de registro los archivos `DELETED`. También se seleccionan los archivos `DELETING` y `CHANGED` cuando el bucket de archivo conserva su copia (así se pueden restaurar los elementos que dejó un borrado interrumpido)
2. Si el Access Point ya tiene la misma clave, dejarla como `EXISTS` y no sobrescribir
3. Solicitar `RestoreObject` para los objetos de S3 Glacier Flexible Retrieval y S3 Glacier Deep Archive (no es necesario para S3 Glacier Instant Retrieval)
4. La espera se hace por sondeo (cada `RestorePollMinutes` se lee el encabezado `Restore` de `HeadObject`, y se abandona tras `RestoreMaxWaitHours`). No se usa el evento `Object Restore Completed` de EventBridge; las notificaciones de EventBridge del bucket están activadas, por lo que se puede cambiar más adelante
5. `CopyObject` del bucket de vuelta al Access Point (Fargate por encima de 5 GiB). El libro de registro pasa a `RESTORED`
6. Leer el archivo restaurado a través del Access Point, calcular su hash y compararlo con el SHA-256, el CRC64NVME y el tamaño del libro de registro (Fargate por encima de 5 GiB). Si coincide, `RESTORE_VERIFIED`; si difiere, `RESTORE_MISMATCH`
7. Escribir el script para reaplicar atributos `manifests/<runId>-reapply.sh`, solo para los archivos `RESTORE_VERIFIED`

Los archivos restaurados tenían propietario 0:1, modo 644 y, como mtime, la hora de la restauración (comprobado en el entorno anterior). `CopyObject` no restaura los valores originales.
### Recuperación tras un borrado interrumpido
Una función Lambda que se detiene a mitad de un borrado o agota los reintentos puede dejar elementos como `DELETING` o `APPROVED` en el libro de registro. El resultado lo muestra como `COMPLETED_WITH_ERRORS`, `stuckDeleting` y `notDeleted`, y se activa `FilesStuckDeletingAlarm`. Al iniciar la máquina de estados de archivo con el mismo `runId` y `"resume": true`, se ejecuta `reconcile`, que resuelve los elementos como se indica abajo y después pide una nueva aprobación para los archivos que quedan.
| Libro de registro | Access Point | Resultado |
|---|---|---|
| `DELETING` | Sin archivo | `DELETED` (el borrado se había realizado; `reconciled: true`) |
| `DELETING`, `APPROVED` | Archivo presente, ETag y tamaño iguales a los del libro de registro | De vuelta a `VERIFIED`; para borrar hace falta una nueva aprobación |
| `DELETING`, `APPROVED` | Archivo presente, distinto del libro de registro | `CHANGED` |
| Cualquiera | La ejecución que tiene el elemento sigue en curso | No se toca |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
Cuando hay que recuperar un elemento que quedó como `DELETING`, la máquina de estados de restauración lo restaura desde la copia del bucket de archivo.
## Aprobación
La notificación no contiene el token de la tarea. El token está en un SecureString de AWS Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). Quien aprueba es alguien con permiso para leer ese parámetro y para llamar a `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# Reject:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
Tras la aprobación, la función `approval` compara `approver` con el `requestedBy` de la entrada de inicio (`RequireSeparateApprover=true`, valor por defecto). Si es la misma entidad principal, la ejecución termina como `APPROVAL_REFUSED` sin marcar nada como `APPROVED`. El ARN de un rol y el ARN de una sesión de ese rol cuentan como la misma entidad principal. En caso contrario, cada archivo de la lista pasa a `APPROVED` en el libro de registro con `approvedBy`, `approvedAt` y el ARN de la ejecución. La función `delete` borra solo los archivos con este registro; invocarla directamente no borra nada que carezca de él.

`approver` y `requestedBy` son valores que declaran quienes llaman. El `deletedBy` del libro de registro se toma de su `approvedBy`. Las entidades principales que realmente iniciaron y aprobaron figuran en los eventos `StartExecution` y `SendTaskSuccess` de CloudTrail. Para garantizar la separación de funciones por entidad principal, separe en IAM los roles que inician y los que aprueban.
## Reaplicación de atributos
Al final de una restauración se escribe `manifests/<runId>-reapply.sh`. Ejecútelo como root en un host que monte el volumen por NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
El script contiene solo `chown`, `chmod` y `touch -d`. Los valores del libro de registro se comprueban con formatos estrictos, y cada clave se convierte en una sola palabra de shell mediante comillas. Un valor que no coincide pasa a ser un comentario y no se ejecuta. No se ha verificado si la API REST de ONTAP puede establecer propietario, grupo, modo y hora de modificación, por lo que esa vía no está implementada.
## Despliegue
### Requisitos previos
- El alias y el ARN del Access Point (IAM necesita ambas formas; una política solo con el alias puede desplegarse y, aun así, ser denegada en tiempo de ejecución)
- Una política del Access Point. La plantilla no puede asociarla, así que se asocia después del despliegue como se muestra abajo. Sin ella, la primera llamada a S3 se deniega en tiempo de ejecución
- Un nombre para el bucket de archivo (la pila lo crea con `DeletionPolicy: Retain`, Block Public Access, SSE-S3 por defecto, KMS opcional, notificaciones de EventBridge habilitadas y TLS obligatorio)
- Solo para `selection=ATIME` y la captura de atributos: una VPC, subredes, un secreto con las credenciales de ONTAP, el punto de enlace de administración, el UUID del volumen y `OntapVerifySsl`. El certificado del punto de enlace de administración de FSx for ONTAP no está firmado por una CA pública, por lo que el valor por defecto es `false` (sin verificación). En ese modo las credenciales de ONTAP viajan por una conexión cuyo extremo no se autentica (la ruta queda dentro de la VPC). Con `true` la verificación falla y la ejecución se detiene en la selección (observado en un sistema real). La función Lambda de la VPC necesita una ruta a Secrets Manager y S3 (puntos de enlace de VPC o NAT)
- Solo para archivos de más de 5 GiB: una imagen en ECR. El Access Point tiene origen en Internet, por lo que las subredes de Fargate necesitan una puerta de enlace NAT o una IP pública
- Una suscripción de notificaciones confirmada. Una suscripción de correo de SNS no hace nada hasta que el destinatario hace clic en el enlace de confirmación; sin ella, nadie ve la solicitud de aprobación
### Pasos
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # replace every <PLACEHOLDER>
sam build && sam deploy
```
Después del despliegue, asocie la política del Access Point. El script genera, a partir de los ARN de los roles de las salidas de la pila, una política que concede `s3:DeleteObject` solo al rol de la función `delete` y `s3:PutObject` solo a los roles de restauración.
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # no PendingConfirmation left
```
Si el Access Point ya tiene una política, esto la reemplaza; combine antes las instrucciones existentes.
Para usar Fargate, construya la imagen desde la raíz del repositorio, súbala a su propio repositorio de ECR e indíquela en `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Ejecute primero sin indicar `dryRun` (es decir, `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
Para borrar, pase `"dryRun": false` como booleano JSON e indique en `requestedBy` la entidad principal que inicia la ejecución. La cadena `"false"` es un error de entrada y no se borra nada.
## Estructura de directorios
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, ledger, 9 Lambda functions, 2 state machines, Fargate (optional), alarms
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
La lógica de dominio (sumas de comprobación, validación de entradas, libro de registro, verificación tras la restauración) está en [`shared/archive_verify/`](../../../shared/archive_verify/) y se prueba en `shared/tests/`. Las lecturas y escrituras hacia el Access Point pasan por `shared/s3ap_helper.py`.
## Pruebas locales
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Para confirmar que se detecta una decisión de borrado incorrecta, `test_does_not_delete_when_etag_changed` y `test_does_not_delete_when_size_differs_but_etag_equal` se ejecutaron una vez contra un stub sin la comparación de ETag; ambas fallaron con `assert 'DELETED' == 'CHANGED'`. La comprobación del registro de aprobación y la exclusión de 50 GiB se escribieron primero como pruebas y se ejecutaron una vez contra el código anterior, fallando con `assert 'DELETED' != 'DELETED'` y `KeyError: 'skippedTooLarge'`, antes de implementarlas.
## Success Metrics
### Outcome
Mover a clases de almacenamiento S3 Glacier los archivos que se leen pocas veces, tras la verificación y la aprobación humana, reducir el uso del volumen y poder encontrar y restaurar los archivos movidos a partir del libro de registro.
### Metrics
Los valores objetivo los fija el operador; aquí no se dan cifras.
| Categoría | Indicador | Definición |
|---|---|---|
| Business Outcome | Capacidad liberada | Diferencia del espacio usado del volumen antes y después de la ejecución (una vez ordenadas las instantáneas). `bytesDeleted` (`-result.json`) es el tamaño total de los archivos borrados, no el espacio liberado: mientras existan instantáneas el uso del volumen no baja, y con datos comprimidos o deduplicados se libera menos espacio que el tamaño lógico |
| Business Outcome | Ahorro mensual esperado de almacenamiento | (GB que salen del grupo de capacidad × diferencia de precio) − (almacenamiento de la clase de archivo, sobrecarga por objeto, cargos de recuperación). Precios: véase «Estimación de costes» más abajo |
| Technical KPI | Tasa de coincidencia de la verificación | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Archivos no borrados | Total de `CHANGED`, `MISMATCH` y `FAILED` |
| Technical KPI | Tasa de coincidencia de la verificación tras la restauración | `RESTORE_VERIFIED` ÷ (`RESTORE_VERIFIED` + `RESTORE_MISMATCH`) |
| Quality KPI | Archivos borrados sin aprobación | Debe ser 0. Contar los elementos `DELETED` con `approvedBy` o `approvedAt` vacíos |
| Cost KPI | Por ejecución: Lambda, Fargate, DynamoDB, solicitudes de S3, transiciones de estado y almacenamiento de la clase de archivo | Estimar con la fórmula de «Estimación de costes» a partir de una ejecución `dryRun=true` medida con un `maxFiles` pequeño |
| Go / No-Go | Técnico: en una ejecución en el entorno real, todos los archivos copiados pasan a `VERIFIED`, un archivo `CHANGED` creado a propósito no se borra, se rechaza la autoaprobación de quien inicia la ejecución y los archivos restaurados quedan como `RESTORE_VERIFIED`. De negocio: el ahorro esperado supera el coste de operación (esfuerzo de aprobación, atención de las solicitudes de restauración); están decididos el punto de entrada y el tiempo de respuesta objetivo de las solicitudes de restauración (incluido el tiempo de restauración de la clase); se ha informado a los usuarios | No usar `dryRun=false` en un volumen de producción hasta que se cumpla todo. Antes, nombre quién decide cada punto (propietario de los datos, aprobador, responsable de operaciones) |

La planificación de una prueba de concepto y las comprobaciones previas a producción están en la [lista de comprobación previa a producción](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md) y el [inventario previo a la migración](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md) del FSx for ONTAP Adoption Playbook (ambos en japonés). Para la prueba de concepto de este patrón, subir `maxFiles` a 20, 200 y 2.000 mientras se registran la duración de la ejecución padre, las transiciones de estado y los segundos de Fargate permite obtener valores por archivo.
### Measurement Method
Historial y registros de ejecución de Step Functions (`/aws/vendedlogs/states/<stack>-archive` y `-restore`, sin datos de ejecución), `manifests/<runId>-result.json`, `manifests/<runId>-approval.json`, métricas EMF de CloudWatch (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `FilesStuckDeleting`, `BytesVerified`, `BytesDeleted`, `RestoreVerified`, `RestoreMismatch`, `ApprovalPendingHours`) y el libro de registro.

Alarmas (todas hacia el tema de notificación):

| Alarma | Condición |
|---|---|
| `ArchiveExecutionsFailedAlarm`, `RestoreExecutionsFailedAlarm` | Una o más ejecuciones fallidas, con tiempo de espera agotado o abortadas en 5 minutos |
| `ApprovalPendingAlarm` | Una solicitud de aprobación lleva esperando más de `ApprovalAlarmHours` (24 por defecto) |
| `FilesStuckDeletingAlarm` | Una ejecución terminó con elementos `DELETING` o `APPROVED` |
| `FilesMismatchAlarm` | Una copia archivada no coincidió (`MISMATCH`) |
| `RestoreMismatchAlarm` | Un archivo restaurado no coincidió con el libro de registro |
El tema de notificación está cifrado con una clave KMS administrada por el cliente. La clave administrada por AWS (`alias/aws/sns`) tiene una política de clave que no se puede editar, y EventBridge y las alarmas de CloudWatch solo pueden publicar en un tema cifrado con una clave administrada por el cliente que permita a las entidades principales de servicio `kms:GenerateDataKey*` y `kms:Decrypt` ([Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html), leída el 2026-11-26). La segunda ejecución confirmó que llegan las notificaciones de fallo de EventBridge y las notificaciones de las alarmas.
## Performance Considerations
La concurrencia por defecto se basa en la medición siguiente. El resto son factores de diseño y no se midieron.
- El archivo de origen se lee dos veces: una a través del Access Point para calcular el hash y otra en el lado del servidor por `CopyObject`. Se facturan las solicitudes de lectura y, para los datos que están en el grupo de capacidad, también la lectura del grupo de capacidad
- La concurrencia es `MapConcurrency` (2 por defecto, tanto en archivo como en restauración). En una medición, una función Lambda leyó 5,3 GB (unos 4,94 GiB) a través del Access Point en 69,8 segundos, unos 76 MB/s en un solo flujo, que es aproximadamente el 60 % de la capacidad de rendimiento de 128 MBps de este entorno. Cada archivo se lee dos veces y el mismo volumen atiende a sus usuarios, por lo que el valor por defecto es 2. Use 1 para archivos grandes o un volumen ocupado y, antes de subirlo, observe `DataReadBytes` del sistema de archivos y la latencia de los clientes durante una ejecución. No se midieron ejecuciones en paralelo
- El valor por defecto de 5 GiB de `LargeFileThresholdBytes` se deriva del límite de `CopyObject` en una sola solicitud. A la velocidad anterior, los 15 minutos de Lambda cubrirían unos 63 GiB, pero es un único dato
- El listado carga todos los resultados de `ListObjectsV2` en la memoria de una sola función Lambda. Por encima de unos pocos millones de objetos, divida el trabajo con `prefix`
- `selection=ATIME` recorre los directorios en profundidad. El límite de análisis es de 200.000 entradas (`ONTAP_SCAN_LIMIT`); al superarlo se devuelven resultados parciales
- El tiempo de espera de una restauración depende de la clase y de `tier`. AWS documenta para S3 Glacier Deep Archive menos de 12 horas en Standard y menos de 48 horas en Bulk. El valor por defecto de `RestoreMaxWaitHours` es 72. Para las clases con esperas largas, un `RestorePollMinutes` mayor supone menos transiciones de sondeo
- Las tareas de Fargate están limitadas por `FargateTimeoutSeconds` (7200 s por defecto). Todas las tareas (Task) tienen un `TimeoutSeconds`, y un tiempo de espera agotado se reintenta
## Estimación de costes
No se midió ninguna factura. A continuación figuran valores de uso medidos y condiciones publicadas por objeto para estimar.
Transiciones de estado por archivo en las dos ejecuciones (una de cada tipo):

| Ejecución | Transiciones de estado por archivo | Fuente |
|---|---|---|
| Archivo, ejecución de prueba | 17 (119 ÷ 7), 18 (72 ÷ 4) | Primera y segunda ejecución |
| Archivo, ejecución real (con borrados) | 18 (127 ÷ 7), 19,5 (78 ÷ 4) | Igual |
| Restauración (`Expedited`; la segunda con verificación) | 18 (107 ÷ 6), 14 (56 ÷ 4) | Igual |
Las clases con esperas largas añaden transiciones con cada sondeo.
Condiciones de almacenamiento por objeto ([Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare), leída el 2026-11-26):

| Clase | Duración mínima de almacenamiento | Sobrecarga por objeto, tamaño mínimo facturable |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 días | Tamaño mínimo facturable por objeto de 128 KB |
| S3 Glacier Flexible Retrieval | 90 días | 40 KB de metadatos (32 KB a la tarifa de esta clase y 8 KB a la tarifa de S3 Standard) |
| S3 Glacier Deep Archive | 180 días | 40 KB de metadatos (mismo reparto) |
Fórmula: coste mensual ≈ archivos × transiciones por archivo × precio por transición + duración de Lambda y Fargate × precio + archivos × (precios de las solicitudes `CopyObject`, `HeadObject`, `DeleteObject` y similares) + almacenamiento (datos + archivos × sobrecarga) × precio de la clase + cargos de recuperación al restaurar. Tome los precios de [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) y [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) para su región y fecha; aquí no se escribe ninguno.
## Governance Note
> Este patrón ofrece orientación sobre arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Consulte a profesionales cualificados.
- El resultado de la verificación y la aprobación son señales de apoyo para la decisión final de una persona. No se usa IA
- El patrón no cumple requisitos de retención ni de inmutabilidad. No se usa Object Lock ni funciones similares, por lo que quien tenga permiso puede borrar
- Clasificación de las salidas: el libro de registro y los manifiestos contienen rutas de archivos, tamaños, hashes y atributos. Una ruta puede contener el nombre de una persona o un identificador de paciente o de caso, por lo que las salidas llevan por defecto `data_classification` `RESTRICTED` ("Restricted — Limited access" en `shared/data_classification.py`). Cuando la clasificación propia de los datos es más estricta, indíquela en el parámetro `DataClassification`. La clasificación la decide usted. El contenido de los archivos va al bucket de archivo; trátelo con la misma clasificación que los datos originales
- Human Review: la aprobación es obligatoria en cada ejecución. No hay aprobación automática basada en un valor de confianza. Por defecto, no se borra nada cuando quien inicia la ejecución y quien aprueba son la misma entidad principal
- IAM: solo el rol de la función `delete` tiene `s3:DeleteObject` sobre el Access Point, y solo la máquina de estados de restauración y el rol de la tarea de Fargate de restauración tienen allí `s3:PutObject`. La tarea de Fargate de archivo solo copia y no puede borrar ni sobrescribir los archivos de origen. Ninguna entidad principal puede borrar elementos del libro de registro
- Auditoría: las aprobaciones y los borrados quedan registrados en el libro de registro (`approvedBy`, `approvedAt`, `requestedBy`, `deletedBy`, `deletedAt`), en `manifests/<runId>-approval.json` y en el historial y los registros de Step Functions. CloudTrail registra los borrados solo cuando un trail tiene activados los eventos de datos de S3; esto no se comprobó en la ejecución
- Número de copias: sin segunda copia, el objeto del bucket de archivo es la única copia después del borrado. La notificación de aprobación lo indica
## Restricciones y puntos sin verificar
- Una copia directa desde un Access Point a un bucket de otra región devolvió `AccessDenied` (un Access Point, una vez). La segunda copia solo tiene como destino buckets de la misma región
- Comprobado en un volumen de estilo UNIX. Un cambio de contenido que conserve el tamaño y el mtime no lo detecta la comprobación de ETag y tamaño (véase «Comportamientos vistos en las ejecuciones de extremo a extremo»). No se comprobó si `chown` cambia el ETag
- La captura de atributos usa listados de directorio, y lee todo el directorio padre para un solo archivo; los directorios grandes son lentos
- El control de versiones del bucket de archivo no es Object Lock. Las versiones se conservan, pero quien tenga permiso también puede borrarlas
- Los archivos de más de 50 GiB no se seleccionan por defecto. Si se incluyen con `allowOversize: true`, no se pueden restaurar en el Access Point; descárguelos del bucket
- `requestedBy` y `approver` son valores declarados. Compruebe la separación por entidad principal con IAM y CloudTrail
## Documentos relacionados
- [Architecture (EN)](docs/architecture.en.md)
- [Notas de compatibilidad de S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Comparación de 8 mecanismos para mover archivos a clases de archivo](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (en japonés)

---

<!-- playbook-reading:start -->
## Lectura previa al paso a producción

Cómo se traducen en decisiones de diseño las restricciones que aparecen después del despliegue está documentado en el [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). El mismo contenido en dos lugares hace que la copia que deja de actualizarse sobreviva a la corregida.

- [Aprovechamiento de datos](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — restricciones del acceso a través de un access point (todos los patrones)
- [Protección de datos](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — donde se concentran las decisiones de este patrón
- [Construir](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — revisar antes de producción (todos los patrones)
<!-- playbook-reading:end -->
