# SnapMirror Cross-Region DR + S3 Access Points Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Présentation

Un modèle de reprise après sinistre qui réplique les données collectées via S3 Access Points en utilisant SnapMirror Asynchronous vers une destination inter-régions, avec basculement automatisé rattachant un nouveau S3 AP sur le volume de destination.

En fonctionnement normal, les données sont ingérées via S3 AP sur le volume source. Lors d'un événement DR, une fonction Lambda orchestre le basculement en ~3 minutes : SnapMirror break → junction path → création S3 AP.

## Architecture

```mermaid
graph TB
    subgraph "Fonctionnement normal (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>Source]
        SRC_VOL[Volume source<br/>vol_sm_dr_source]
    end
    subgraph "Réplication"
        SM[SnapMirror Async<br/>Planification : intervalles de 5 min]
    end
    subgraph "Basculement DR (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>Destination<br/>(créé lors du basculement)]
        DST_VOL[Volume dest (DP)<br/>vol_sm_dr_dest]
        SNS[Notification SNS]
        CLIENT[Applications<br/>(basculent vers le nouveau S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|Réplication<br/>incrémentale| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## Composants clés

| Composant | Description |
|-----------|-------------|
| Volume source + S3 AP | Point d'ingestion des données (Region A). Fonctionnement normal |
| SnapMirror Async | Réplication incrémentale au niveau volume (RPO = intervalle de planification) |
| Volume destination (DP) | Volume de protection des données (lecture seule jusqu'au break). Créé via FSx API (SM-VAL-009) |
| Failover Lambda | Automatise : break → junction → création S3 AP. RTO ~3 min |
| SNS Topic | Notifie les applications du nouveau point d'accès S3 AP après basculement |

## RTO / RPO

| Métrique | Valeur | Notes |
|----------|:------:|-------|
| **RTO** | ~3 minutes | SnapMirror break (instantané) + propagation junction (~2 min) + création S3 AP (~30s) |
| **RPO** | ≤ planification SnapMirror | Planification par défaut de 5 minutes. Les données depuis le dernier transfert peuvent être perdues |

## Prérequis

- 2 clusters FSx for ONTAP dans des régions différentes
- VPC Peering avec Cluster/SVM Peering établis
- Volume DP de destination créé via `aws fsx create-volume` (pas uniquement via ONTAP REST API — SM-VAL-009)
- Relation SnapMirror initialisée et en état `snapmirrored`
- Identifiants fsxadmin dans Secrets Manager (les deux régions)
- Accès VPC Lambda vers l'IP de gestion ONTAP de destination (port 443)

## Déploiement

```bash
# 1. Déployer la pile (crée le volume source, le volume DP dest, Failover Lambda, SNS)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Créer le S3 AP source + la relation SnapMirror
#    (voir PostDeployInstructions dans les sorties de la pile)

# 3. Tester le basculement (exécution à blanc)
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## Exécuter le basculement

```bash
# Déclencher le basculement DR
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# Vérifier le résultat
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## Vérification

```bash
# Après le basculement, lire depuis le S3 AP de destination
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## Contraintes techniques

| Contrainte | Détails |
|-----------|---------|
| SnapMirror Asynchronous uniquement | Le mode Synchronous N'EST PAS pris en charge pour les volumes S3 NAS bucket |
| SVM-DR non supporté | Un SVM contenant un S3 NAS bucket bloque SVM-DR. Uniquement SnapMirror au niveau volume |
| Volume DP via FSx API | SM-VAL-009 : Les volumes créés uniquement via ONTAP REST API sont invisibles pour FSx API, bloquant S3 AP |
| S3 AP non transféré | SM-002 : S3 AP est une ressource de la couche AWS. Nouveau AP requis à la destination |
| Mise à jour de l'application cliente | Le nouveau AP a un ARN/alias différent. Les applications doivent changer de point d'accès |
| Planification SnapMirror | FSx for ONTAP minimum : intervalles de 5 minutes |

## Nettoyage (Ordre critique — SM-VAL-011)

```bash
# ⚠️ Suivre l'ordre exact pour éviter les ressources orphelines

# 1. Supprimer la relation SnapMirror (depuis le cluster DESTINATION)
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    Puis depuis la SOURCE : snapmirror release (ONTAP CLI)

# 2. Supprimer les SVM Peers (les DEUX clusters) — interroger les deux côtés jusqu'à num_records: 0

# 3. Supprimer les Cluster Peers (les deux clusters)

# 4. Supprimer le VPC Peering (uniquement après confirmation de l'étape 2)

# 5. Détacher/supprimer les S3 Access Points (source et destination si créés)
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. Supprimer la pile CloudFormation
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## Références

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
