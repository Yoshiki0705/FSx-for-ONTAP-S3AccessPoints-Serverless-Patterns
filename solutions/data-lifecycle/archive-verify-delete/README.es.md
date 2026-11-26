# archive-verify-delete: archivado solo con llamadas a la API de S3, copia, verificación y borrado tras la aprobación
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español
📚 **Documentación**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Descripción general
Este patrón mueve a clases de almacenamiento S3 Glacier los archivos que se leen pocas veces de un volumen de Amazon FSx for NetApp ONTAP (FSx for ONTAP). El volumen no se monta. Solo se usan llamadas a la API de S3 a través de S3 Access Points.
Un archivo sigue los pasos siguientes, y un archivo cuyas condiciones dejan de cumplirse por el camino queda fuera del borrado.
1. Registrar su tamaño, ETag, SHA-256 y CRC64NVME en el libro de registro (una tabla de DynamoDB)
2. Copiarlo al bucket de archivo con `CopyObject`, indicando la clase de almacenamiento
3. Comparar la suma de comprobación que devuelve el bucket con el valor del libro de registro
4. Una persona aprueba la lista de archivos que coinciden
5. Comprobar que el ETag y el tamaño en el Access Point son iguales a los del libro de registro y, entonces, borrar el archivo del Access Point

Para restaurar, se busca el archivo en el libro de registro, se solicita la restauración en el bucket, se espera a que termine y se copia de vuelta al Access Point con `CopyObject`.
Este patrón no usa S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock ni el bloqueo de instantáneas, y la plantilla no contiene ninguno. No se establece ningún período de retención, de modo que los objetos del bucket de archivo pueden ser borrados por quien tenga permiso.
Las premisas de este patrón y su comparación con otros enfoques están en [Comparación de 8 mecanismos para mover archivos a clases de archivo](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (en japonés).
## Qué se midió y qué no
| Categoría | Contenido |
|---|---|
| Componentes comprobados una vez cada uno en un entorno real (registrados en la comparación anterior; 2026-11-24 y 2026-11-26, ap-northeast-1, primera generación `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, volumen de estilo UNIX, el usuario del Access Point es UNIX root) | Con `ChecksumAlgorithm=SHA256` en `CopyObject`, el `ChecksumSHA256` del bucket fue `FULL_OBJECT` e igual al SHA-256 del archivo (hasta 8 MiB). En una copia multiparte de 5,5 GiB, el SHA-256 pasó a ser `COMPOSITE` y el CRC64NVME fue `FULL_OBJECT` e igual. `--copy-source-if-match` con un ETag antiguo devolvió `PreconditionFailed`. El `DeleteObject` del Access Point no admite `If-Match`. Una integración SDK de Step Functions aceptó el alias del Access Point como `Bucket` |
| Comprobado en este repositorio | Pruebas unitarias con moto y pruebas de la estructura de la máquina de estados y de IAM. Sin conexión a AWS. Tres defectos encontrados en la ejecución de extremo a extremo anterior (permiso de invocación de la función de la API REST de ONTAP, verificación TLS, nombre del error de una solicitud de restauración duplicada) se corrigieron con pruebas que los reproducen |
| Comprobado una vez cada uno en una ejecución de extremo a extremo en un entorno real (2026-11-26, mismo entorno que arriba, `selection=ATIME`, `GLACIER`, 7 archivos) | Selección por `accessed_time` y captura de uid, gid, mode, mtime y atime mediante la API REST de ONTAP (la raíz es la raíz del volumen y la ruta no lleva barra inicial; `unix_permissions` vuelve como el entero `640`). El `ItemReader` y el `ResultWriter` de Distributed Map. Una copia multiparte de 5,5 GiB con Fargate (con `CopySourceIfMatch`; CRC64NVME igual al del libro de registro). El cálculo del hash de un archivo de 5,3 GB (unos 4,94 GiB) en Lambda (69,8 s, 2048 MB configurados, 152 MB usados). La segunda copia. El borrado tras la aprobación. Un archivo reescrito por NFS mientras la ejecución esperaba la aprobación pasó a `CHANGED` y no se borró. Una aprobación rechazada no borró nada. La restauración con `Expedited` (incluido el archivo de 5,5 GiB) y un SHA-256 igual en los 6 archivos restaurados (el séptimo de los 7 archivos se había reescrito, así que no se borró ni se restauró). La recuperación de uid, gid, mode y mtime con `reapply.sh` |
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
### Tres defectos encontrados y corregidos en la ejecución de extremo a extremo
Cada uno se corrigió con una prueba que lo reproduce.
| # | Síntoma | Causa y corrección |
|---|---|---|
| 1 | Una ejecución con `selection=ATIME` falló en el paso de selección | Al rol de la máquina de estados de archivo le faltaba `lambda:InvokeFunction` sobre la función de la API REST de ONTAP. Se añadió el permiso |
| 2 | La función de la API REST de ONTAP falló con `CERTIFICATE_VERIFY_FAILED` | Siempre verificaba TLS, pero el certificado del punto de enlace de administración de FSx for ONTAP no está firmado por una CA pública. Se añadió el parámetro `OntapVerifySsl` (por defecto `false`) |
| 3 | Una solicitud de restauración duplicada se convirtió en un fallo de archivo | La integración SDK de Step Functions devuelve `RestoreAlreadyInProgress` como `S3.S3Exception`, de modo que el `Catch` de `S3.RestoreAlreadyInProgressException` no coincidía. Ahora una restauración en curso se dirige al bucle de espera |
### Comportamientos vistos en la ejecución de extremo a extremo
No se trataron como defectos.
- Con `selection=ATIME`, las propias lecturas del patrón actualizan `accessed_time`. Tras una ejecución con `dryRun=true`, las lecturas del cálculo del hash dejan el atime de los archivos en la hora de ejecución, así que la misma entrada con `dryRun=false` no selecciona nada (terminó con 0 archivos; visto cuando una ejecución real siguió a una de prueba). Por tanto, una ejecución de prueba hace que los archivos parezcan leídos hace poco. Para ejecutar la pasada real sobre los mismos candidatos justo después de una ejecución de prueba, usa `selection=MTIME` (`LastModified` no cambia al leer)
- El ETag del Access Point sigue al mtime y al tamaño, no al contenido. Tres archivos con contenido distinto pero igual tamaño e igual mtime devolvieron el mismo ETag. Por eso la comprobación de ETag y tamaño antes de borrar no detecta un cambio de contenido que conserve el tamaño y el mtime. Una reescritura que conservaba el tamaño pero actualizaba el mtime sí se detectó (paso 3)
- Al borrar por el Access Point el último archivo de un directorio, también desaparece el directorio padre que queda vacío (visto con `arc-e2e/large/`). El `CopyObject` de la restauración vuelve a crear el padre
- Un archivo restaurado tenía propietario 0:1, modo 644 y, como hora de modificación, la hora de la restauración. Al ejecutar como root el `reapply.sh` generado, en un host que monta el volumen por NFS, se recuperaron los uid, gid, mode y mtime originales (1234:5678, 640, 2020-01-02 03:04:05) y el SHA-256 del contenido no cambió
- La ejecución usó una política del Access Point que permite cada rol (los roles de las funciones `select`, `record`, `delete` y `restore`, el rol de la tarea de Fargate y los roles de las dos máquinas de estados)
- Una solicitud de restauración `Expedited` de 5,5 GiB fue aceptada y terminó en unos 4 minutos o menos
### Puntos no comprobados
- Duración y coste con muchos archivos
- Finalización de las restauraciones `Standard` y `Bulk` (solo se ejecutó `Expedited`)
- Reintento ante `S3.SlowDownException` (no se observó el nombre que devuelve la integración SDK, y es posible una discrepancia del mismo tipo que el defecto 3)
- Registros de los borrados en los eventos de datos de CloudTrail (no se comprobó si el trail de la cuenta cubre los eventos de datos de este Access Point)
- Volúmenes NTFS, usuarios distintos de root, segunda generación, Multi-AZ
- Comportamiento cuando el Access Point no tiene política
- La ruta `EXISTS` de la restauración (un archivo con el mismo nombre ya presente en NFS); lo único observado como omisión fue que no se seleccionó el archivo `CHANGED`
- Una ejecución que encontró 0 candidatos sigue sin explicación. Una ejecución unos 10 segundos después de restablecer el atime con `touch -d` encontró 0 candidatos. Una comprobación unos 17 minutos después devolvió el valor de 2020, y otra comprobación justo después de `touch` devolvió 6 archivos. No se identificó la causa y no se reprodujo
### Ventana de escritura que queda antes del borrado
En la comprobación previa al borrado queda una ventana de escritura. El `DeleteObject` del Access Point no admite el borrado condicional, por lo que una escritura entre la comprobación con `HeadObject` y el borrado no se detecta. La ventana equivale a una ida y vuelta de llamada a la API.
## Flujo
### Archivado
`olderThanDays` es obligatorio en la entrada, y `dryRun` es `true` por defecto.
| Paso | Procesamiento | Implementación |
|---|---|---|
| 1. Seleccionar | `MTIME`: `LastModified` del `ListObjectsV2` del Access Point. `ATIME`: `accessed_time` de la API REST de ONTAP (Lambda dentro de la VPC) | `select`, `ontap_rest` |
| 2. Registrar | Tamaño, ETag, SHA-256, CRC64NVME y, si están disponibles, uid, gid, mode, mtime, atime, en el libro de registro. Lambda hasta 5 GiB, Fargate por encima | `record`, tarea de Fargate |
| 3. Copiar | Hasta 5 GiB: `copyObject` por integración SDK (`SHA256`, el ETag del libro de registro como `CopySourceIfMatch`). Por encima: copia multiparte con Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Verificar | Comparar el tamaño y la suma de comprobación del `HeadObject` del bucket (`ChecksumMode=ENABLED`) con el libro de registro. Una diferencia queda como `MISMATCH` y el archivo se excluye del borrado | `ledger` |
| 5. Segunda copia (opcional) | Copiar desde el Access Point a otro bucket de la misma región y verificar de la misma forma. Una diferencia retira el archivo del borrado | Step Functions, `ledger` |
| 6. Aprobar | Escribir la lista de coincidencias en `manifests/<runId>.json`, notificar por SNS y esperar con `waitForTaskToken` | `approval` |
| 7. Borrar | Solo con `dryRun=false`. Por cada archivo, comprobar ETag y tamaño y, si son iguales, llamar a `DeleteObject`. Una diferencia queda como `CHANGED` | `delete` |
| 8. Registrar | `manifests/<runId>-result.json` y métricas EMF (recuentos, bytes) | `summarize` |
Con `dryRun=true` la ejecución llega igualmente hasta el paso 6. Es decir, la copia se realiza y se factura el almacenamiento de la clase de archivo (S3 Glacier Deep Archive tiene una duración mínima de almacenamiento). Para probar, use un `maxFiles` pequeño. No se borra nada.
Los estados del libro de registro avanzan en el orden `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETED`, `RESTORED`, con las salidas laterales `CHANGED`, `MISMATCH` y `FAILED`. Solo se pueden borrar los archivos `VERIFIED` (incluida la verificación de la segunda copia cuando se exige).
### Restauración
La entrada es `runId` y exactamente uno de `keys` o `prefix`. Se pueden indicar `tier` (`Bulk` por defecto) y `days` (7 por defecto).
1. Seleccionar en el libro de registro los archivos `DELETED`
2. Si el Access Point ya tiene la misma clave, registrarla como `EXISTS` y no sobrescribir
3. Solicitar `RestoreObject` para los objetos de S3 Glacier Flexible Retrieval y S3 Glacier Deep Archive (no es necesario para S3 Glacier Instant Retrieval)
4. La finalización se consulta por sondeo: cada `RestorePollMinutes` se lee el encabezado `Restore` de `HeadObject`, y la espera se corta en `RestoreMaxWaitHours`. No se usa el evento `Object Restore Completed` de EventBridge. Las notificaciones de EventBridge están habilitadas en el bucket, por lo que se puede cambiar más adelante
5. `CopyObject` del bucket al Access Point (Fargate por encima de 5 GiB)
6. Pasar el libro de registro a `RESTORED` y escribir el script para reaplicar atributos `manifests/<runId>-reapply.sh`

Un archivo restaurado tenía propietario 0:1, modo 644 y una hora de modificación igual a la hora de la restauración (una comprobación en el entorno anterior). `CopyObject` no restaura los valores originales.
## Aprobación
La notificación de aprobación no contiene el token. El token está en un SecureString de AWS Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). Quien apruebe necesita permiso para leer ese parámetro y `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# Rechazar:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` es una declaración propia. El valor que se introduce pasa a `deletedBy` en el libro de registro, pero la prueba de quién aprobó realmente es el evento `SendTaskSuccess` de CloudTrail. Si `approver` está vacío, o `approved` no es `true`, no se borra nada.
## Reaplicación de atributos
Al final de una restauración se escribe `manifests/<runId>-reapply.sh`. Ejecútelo como root en un host que monte el volumen por NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
El script contiene solo `chown`, `chmod` y `touch -d`. Los valores del libro de registro se comprueban con formatos estrictos, y cada clave se convierte en una sola palabra de shell mediante comillas. Un valor que no coincide pasa a ser un comentario y no se ejecuta. No se ha verificado si la API REST de ONTAP puede establecer propietario, grupo, modo y hora de modificación, por lo que esa vía no está implementada.
## Despliegue
### Requisitos previos
- El alias y el ARN del Access Point (IAM necesita ambas formas; una política solo con el alias puede desplegarse y, aun así, ser denegada en tiempo de ejecución)
- Un nombre para el bucket de archivo (la pila lo crea con `DeletionPolicy: Retain`, Block Public Access, SSE-S3 por defecto, KMS opcional, notificaciones de EventBridge habilitadas y TLS obligatorio)
- Solo para `selection=ATIME` y la captura de atributos: una VPC, subredes, el secreto con las credenciales de ONTAP, el punto de enlace de administración, el UUID del volumen y `OntapVerifySsl`. El certificado del punto de enlace de administración de FSx for ONTAP no está firmado por una CA pública, por lo que el valor por defecto es `false` (sin verificación) y las credenciales de ONTAP se envían entonces por una conexión cuyo extremo no se autentica (la ruta está dentro de la VPC). Con `true`, la selección se detuvo por un error de certificado (observado). Hace falta una ruta desde la función Lambda de la VPC hasta Secrets Manager y S3 (puntos de enlace de VPC o NAT)
- Solo para archivos de más de 5 GiB: una imagen en ECR. El Access Point tiene origen en Internet, por lo que las subredes de Fargate necesitan NAT o una IP pública
### Pasos
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # sustituir <PLACEHOLDER>
sam build && sam deploy
```
Para usar Fargate, construya la imagen desde la raíz del repositorio, súbala a su propio repositorio de ECR e indíquela en `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Ejecute primero con una entrada que omita `dryRun` (es decir, `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
Para borrar, pase `"dryRun": false` como booleano JSON. La cadena `"false"` es un error de entrada y no se borra nada.
## Estructura de directorios
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, libro de registro, 8 funciones Lambda, 2 máquinas de estados, Fargate (opcional)
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
La lógica de dominio (sumas de comprobación, validación de entradas, libro de registro) está en [`shared/archive_verify/`](../../../shared/archive_verify/) y se prueba en `shared/tests/`. Las lecturas y escrituras hacia el Access Point pasan por `shared/s3ap_helper.py`.
## Pruebas locales
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Para confirmar que se detecta una comprobación de borrado rota, `test_does_not_delete_when_etag_changed` y `test_does_not_delete_when_size_differs_but_etag_equal` se ejecutaron una vez contra un stub sin la comparación de ETag; ambas fallaron con `assert 'DELETED' == 'CHANGED'`. Con la comprobación restaurada, pasan 29 pruebas.
## Success Metrics
### Outcome
Mover a clases de almacenamiento S3 Glacier los archivos que se leen pocas veces, tras la verificación y la aprobación humana, reducir el uso del volumen y poder encontrar y restaurar los archivos movidos a partir del libro de registro.
### Metrics
Los objetivos los fija el operador. Aquí no se dan cifras.
| Categoría | Indicador | Definición |
|---|---|---|
| Business Outcome | Capacidad liberada | `bytesDeleted` (`-result.json`). El uso del volumen no baja mientras existan instantáneas |
| Technical KPI | Tasa de coincidencia de la verificación | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Archivos no borrados | Total de `CHANGED`, `MISMATCH` y `FAILED` |
| Quality KPI | Archivos borrados sin aprobación | Debe ser 0. Contar los `DELETED` cuyo `deletedBy` está vacío |
| Cost KPI | Por ejecución: Lambda, Fargate, DynamoDB, solicitudes de S3, almacenamiento de la clase de archivo | No medido. Estimar primero con `dryRun=true` y un `maxFiles` pequeño |
| Go / No-Go | En una ejecución de extremo a extremo en un entorno real, todos los archivos copiados pasan a `VERIFIED`, un `CHANGED` creado a propósito no se borra y el SHA-256 de un archivo restaurado coincide | No usar `dryRun=false` en un volumen de producción hasta que se cumpla |
### Measurement Method
Historial de ejecución de Step Functions, `manifests/<runId>-result.json`, métricas EMF de CloudWatch (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `BytesVerified`, `BytesDeleted`) y el libro de registro.
## Performance Considerations
No medido. Los siguientes son factores de diseño.
- El archivo de origen se lee dos veces. La primera lectura es a través del Access Point para calcular el hash, y la segunda es la lectura en el lado del servidor de `CopyObject`. Se facturan las solicitudes de lectura y, para los datos que están en el grupo de capacidad, también la lectura del grupo de capacidad
- El paralelismo es `MapConcurrency` (10 por defecto). Empiece con poco y ajuste según la carga en el Access Point y en ONTAP
- El límite de Lambda es de 15 minutos. No se midió la velocidad de lectura desde el Access Point, así que se desconoce si el valor por defecto de 5 GiB de `LargeFileThresholdBytes` es suficiente. Si no lo es, bájelo; Fargate se encargará de más archivos
- El listado carga todos los resultados de `ListObjectsV2` en la memoria de una sola función Lambda. Por encima de unos pocos millones de objetos, divida el trabajo con `prefix`
- `selection=ATIME` recorre los directorios en profundidad. El límite de análisis es de 200.000 entradas (`ONTAP_SCAN_LIMIT`); al superarlo se devuelve el resultado parcial
- El tiempo de espera de una restauración depende de la clase y de `tier`. AWS indica para S3 Glacier Deep Archive menos de 12 horas en Standard y menos de 48 horas en Bulk. El valor por defecto de `RestoreMaxWaitHours` es 72
## Governance Note
> Este patrón ofrece orientación sobre arquitectura técnica. No constituye asesoramiento legal, de cumplimiento ni regulatorio. Consulte a profesionales cualificados de su organización.
- El resultado de la verificación y la aprobación son señales de apoyo para la decisión final de una persona. No se usa IA
- Si se exigen períodos de retención o inmutabilidad, este patrón no los cumple. No usa Object Lock ni nada equivalente, por lo que quien tenga permiso puede borrar
- Clasificación de las salidas: el libro de registro y los manifiestos contienen rutas de archivos, tamaños, hashes y atributos (`dataClassification: operational-metadata`). El contenido de los archivos va al bucket de archivo; trátelo con la misma clasificación que los datos originales
- Human Review: la aprobación es obligatoria en cada ejecución. No hay aprobación automática basada en un valor de confianza
- IAM: solo el rol de la función `delete` tiene `s3:DeleteObject`. La tarea de Fargate solo copia y no tiene permiso de borrado. Nadie tiene permiso para borrar elementos del libro de registro
- Auditoría: la aprobación y el borrado quedan registrados en el libro de registro (`deletedBy`, `deletedAt`), en el historial de ejecución de Step Functions y en CloudTrail
## Restricciones y puntos sin verificar
- Una copia directa desde un Access Point a un bucket de otra región devolvió `AccessDenied` (un Access Point, una vez). La segunda copia solo tiene como destino buckets de la misma región
- Comprobado en un volumen de estilo UNIX. Un cambio de contenido que conserve el tamaño y el mtime no lo detecta la comprobación de ETag y tamaño (véase «Comportamientos vistos en la ejecución de extremo a extremo» más arriba). No se comprobó si `chown` cambia el ETag
- Los atributos se leen mediante el listado del directorio. Leer todo el directorio padre para un solo archivo es lento en directorios grandes
- El control de versiones del bucket de archivo no es Object Lock. Las versiones se conservan, pero quien tenga permiso también puede borrar versiones
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
