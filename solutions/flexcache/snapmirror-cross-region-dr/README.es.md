# SnapMirror Cross-Region DR + S3 Access Points Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Descripción general

Un patrón de recuperación ante desastres que replica los datos recopilados a través de S3 Access Points mediante SnapMirror Asynchronous hacia un destino en otra región, con conmutación por error automatizada que adjunta un nuevo S3 AP en el volumen de destino.

Durante las operaciones normales, los datos se ingieren a través del S3 AP en el volumen de origen. Ante un evento DR, una función Lambda orquesta la conmutación por error en ~3 minutos: SnapMirror break → junction path → creación de S3 AP.

## Arquitectura

```mermaid
graph TB
    subgraph "Operaciones normales (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>Origen]
        SRC_VOL[Volumen origen<br/>vol_sm_dr_source]
    end
    subgraph "Replicación"
        SM[SnapMirror Async<br/>Programación: intervalos de 5 min]
    end
    subgraph "Conmutación DR (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>Destino<br/>(creado en la conmutación)]
        DST_VOL[Volumen dest (DP)<br/>vol_sm_dr_dest]
        SNS[Notificación SNS]
        CLIENT[Aplicaciones<br/>(cambian al nuevo S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|Replicación<br/>incremental| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## Componentes clave

| Componente | Descripción |
|-----------|-------------|
| Volumen origen + S3 AP | Punto de ingesta de datos (Region A). Operaciones normales |
| SnapMirror Async | Replicación incremental a nivel de volumen (RPO = intervalo de programación) |
| Volumen destino (DP) | Volumen de protección de datos (solo lectura hasta break). Creado via FSx API (SM-VAL-009) |
| Failover Lambda | Automatiza: break → junction → creación S3 AP. RTO ~3 min |
| SNS Topic | Notifica a las aplicaciones el nuevo endpoint S3 AP tras la conmutación |

## RTO / RPO

| Métrica | Valor | Notas |
|---------|:-----:|-------|
| **RTO** | ~3 minutos | SnapMirror break (instantáneo) + propagación junction (~2 min) + creación S3 AP (~30s) |
| **RPO** | ≤ programación SnapMirror | Programación predeterminada de 5 minutos. Los datos desde la última transferencia pueden perderse |

## Prerrequisitos

- 2 clusters FSx for ONTAP en diferentes regiones
- VPC Peering con Cluster/SVM Peering establecidos
- Volumen DP de destino creado via `aws fsx create-volume` (no solo via ONTAP REST API — SM-VAL-009)
- Relación SnapMirror inicializada y en estado `snapmirrored`
- Credenciales fsxadmin en Secrets Manager (ambas regiones)
- Acceso VPC desde Lambda a la IP de gestión ONTAP de destino (puerto 443)

## Despliegue

```bash
# 1. Desplegar la pila (crea volumen origen, volumen DP destino, Failover Lambda, SNS)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Crear S3 AP de origen + relación SnapMirror
#    (ver PostDeployInstructions en las salidas de la pila)

# 3. Probar la conmutación por error (ejecución de prueba)
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## Ejecutar conmutación por error

```bash
# Activar conmutación DR
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# Verificar resultado
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## Verificación

```bash
# Después de la conmutación, leer desde el S3 AP de destino
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## Restricciones técnicas

| Restricción | Detalles |
|------------|---------|
| Solo SnapMirror Asynchronous | El modo Synchronous NO es compatible con volúmenes S3 NAS bucket |
| SVM-DR no soportado | Un SVM que contiene S3 NAS bucket bloquea SVM-DR. Solo SnapMirror a nivel de volumen |
| Volumen DP via FSx API | SM-VAL-009: Volúmenes creados solo via ONTAP REST API son invisibles para FSx API, bloqueando S3 AP |
| S3 AP no se transfiere | SM-002: S3 AP es un recurso de la capa AWS. Nuevo AP requerido en destino |
| Actualización de la aplicación cliente | El nuevo AP tiene diferente ARN/alias. Las aplicaciones deben cambiar de endpoint |
| Programación SnapMirror | FSx for ONTAP mínimo: intervalos de 5 minutos |

## Limpieza (Orden crítico — SM-VAL-011)

```bash
# ⚠️ Seguir el orden exacto para evitar recursos huérfanos

# 1. Eliminar relación SnapMirror (desde el cluster DESTINO)
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    Luego desde el ORIGEN: snapmirror release (ONTAP CLI)

# 2. Eliminar SVM Peers (AMBOS clusters) — consultar ambos lados hasta num_records: 0

# 3. Eliminar Cluster Peers (ambos clusters)

# 4. Eliminar VPC Peering (solo después de confirmar el paso 2)

# 5. Desconectar/eliminar S3 Access Points (origen y destino si fue creado)
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. Eliminar la pila CloudFormation
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## Referencias

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
