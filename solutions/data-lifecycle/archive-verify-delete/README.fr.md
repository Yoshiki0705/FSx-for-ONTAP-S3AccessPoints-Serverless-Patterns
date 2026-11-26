# archive-verify-delete : archivage avec les seuls appels d'API S3, copie, vérification, puis suppression après approbation
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation** : [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Vue d'ensemble
Ce modèle déplace vers des classes de stockage S3 Glacier les fichiers rarement lus d'un volume Amazon FSx for NetApp ONTAP (FSx for ONTAP). Le volume n'est pas monté. Seuls des appels d'API S3 via S3 Access Points sont utilisés.
Un fichier suit les étapes ci-dessous, et un fichier dont les conditions cessent d'être remplies en cours de route est exclu de la suppression.
1. Enregistrer sa taille, son ETag, son SHA-256 et son CRC64NVME dans le registre (une table DynamoDB)
2. Le copier dans le compartiment d'archive avec `CopyObject`, en indiquant la classe de stockage
3. Comparer la somme de contrôle renvoyée par le compartiment avec la valeur du registre
4. Une personne approuve la liste des fichiers concordants
5. Vérifier que l'ETag et la taille côté Access Point sont identiques à ceux du registre, puis supprimer le fichier de l'Access Point

Pour restaurer, on retrouve le fichier dans le registre, on demande la restauration dans le compartiment, on attend qu'elle se termine, puis on le recopie vers l'Access Point avec `CopyObject`.
Ce modèle n'utilise ni S3 Object Lock, ni S3 Glacier Vault Lock, ni AWS Backup Vault Lock, ni SnapLock, ni le verrouillage de snapshots, et le modèle de déploiement n'en contient aucun. Aucune durée de conservation n'est définie : les objets du compartiment d'archive peuvent être supprimés par toute personne qui en a l'autorisation.
Les hypothèses de ce modèle et sa comparaison avec d'autres approches se trouvent dans [Comparaison de 8 mécanismes de déplacement de fichiers vers des classes d'archive](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (en japonais).
## Ce qui a été mesuré et ce qui ne l'a pas été
| Catégorie | Contenu |
|---|---|
| Composants vérifiés une fois chacun sur un environnement réel (consignés dans la comparaison ci-dessus ; 2026-11-24 et 2026-11-26, ap-northeast-1, première génération `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, volume de style UNIX, l'utilisateur de l'Access Point est UNIX root) | Avec `ChecksumAlgorithm=SHA256` sur `CopyObject`, le `ChecksumSHA256` du compartiment était `FULL_OBJECT` et égal au SHA-256 du fichier (jusqu'à 8 MiB). Pour une copie multipart de 5,5 GiB, le SHA-256 est devenu `COMPOSITE` et le CRC64NVME était `FULL_OBJECT` et égal. `--copy-source-if-match` avec un ancien ETag a renvoyé `PreconditionFailed`. Le `DeleteObject` de l'Access Point ne prend pas en charge `If-Match`. Une intégration SDK de Step Functions a accepté l'alias de l'Access Point comme `Bucket` |
| Vérifié dans ce dépôt | Tests unitaires avec moto, et tests de la structure de la machine d'états et d'IAM. Aucune connexion à AWS |
| Pas encore vérifié | Une exécution de bout en bout de l'ensemble du modèle sur un environnement réel. Durée et coût avec de nombreux fichiers. Temps de calcul du hachage dans Lambda pour des fichiers proches de 5 GiB. La copie multipart de Fargate sur un environnement réel. La façon de désigner le répertoire racine dans l'API REST d'ONTAP et la représentation de `unix_permissions`. Le `ItemReader` et le `ResultWriter` de Distributed Map sur un environnement réel. La restauration depuis les deux classes qui exigent une restauration. Volumes NTFS, utilisateurs autres que root, deuxième génération, Multi-AZ |
Une fenêtre d'écriture subsiste dans la vérification avant suppression. Le `DeleteObject` de l'Access Point ne prend pas en charge la suppression conditionnelle : une écriture survenue entre la vérification par `HeadObject` et la suppression n'est donc pas détectée. La fenêtre correspond à un aller-retour d'appel d'API.
## Déroulement
### Archivage
`olderThanDays` est obligatoire dans l'entrée, et `dryRun` vaut `true` par défaut.
| Étape | Traitement | Implémentation |
|---|---|---|
| 1. Sélectionner | `MTIME` : `LastModified` du `ListObjectsV2` de l'Access Point. `ATIME` : `accessed_time` de l'API REST d'ONTAP (Lambda dans le VPC) | `select`, `ontap_rest` |
| 2. Enregistrer | Taille, ETag, SHA-256, CRC64NVME et, si disponibles, uid, gid, mode, mtime, atime, dans le registre. Lambda jusqu'à 5 GiB, Fargate au-delà | `record`, tâche Fargate |
| 3. Copier | Jusqu'à 5 GiB : `copyObject` par intégration SDK (`SHA256`, l'ETag du registre comme `CopySourceIfMatch`). Au-delà : copie multipart par Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Vérifier | Comparer la taille et la somme de contrôle du `HeadObject` du compartiment (`ChecksumMode=ENABLED`) avec le registre. Une différence reste `MISMATCH` et le fichier est exclu de la suppression | `ledger` |
| 5. Deuxième copie (facultative) | Copier de l'Access Point vers un autre compartiment de la même région et vérifier de la même façon. Une différence retire le fichier de la suppression | Step Functions, `ledger` |
| 6. Approuver | Écrire la liste des fichiers concordants dans `manifests/<runId>.json`, notifier par SNS et attendre avec `waitForTaskToken` | `approval` |
| 7. Supprimer | Seulement si `dryRun=false`. Pour chaque fichier, vérifier l'ETag et la taille et, s'ils sont identiques, appeler `DeleteObject`. Une différence reste `CHANGED` | `delete` |
| 8. Consigner | `manifests/<runId>-result.json` et métriques EMF (nombres, octets) | `summarize` |
Avec `dryRun=true`, l'exécution va quand même jusqu'à l'étape 6. Autrement dit, la copie a lieu et le stockage de la classe d'archive est facturé (S3 Glacier Deep Archive a une durée de stockage minimale). Pour un essai, utilisez un `maxFiles` faible. Rien n'est supprimé.
Les statuts du registre progressent dans l'ordre `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETED`, `RESTORED`, avec les sorties latérales `CHANGED`, `MISMATCH` et `FAILED`. Seuls les fichiers `VERIFIED` (y compris la vérification de la deuxième copie lorsqu'elle est exigée) peuvent être supprimés.
### Restauration
L'entrée est `runId` et exactement l'un de `keys` ou `prefix`. On peut indiquer `tier` (`Bulk` par défaut) et `days` (7 par défaut).
1. Sélectionner dans le registre les fichiers `DELETED`
2. Si l'Access Point contient déjà la même clé, la consigner comme `EXISTS` et ne pas écraser
3. Demander `RestoreObject` pour les objets de S3 Glacier Flexible Retrieval et de S3 Glacier Deep Archive (inutile pour S3 Glacier Instant Retrieval)
4. L'achèvement est interrogé par sondage : toutes les `RestorePollMinutes`, l'en-tête `Restore` de `HeadObject` est lu, et l'attente s'arrête à `RestoreMaxWaitHours`. L'événement EventBridge `Object Restore Completed` n'est pas utilisé. Les notifications EventBridge sont activées sur le compartiment, ce qui permet de changer plus tard
5. `CopyObject` du compartiment vers l'Access Point (Fargate au-delà de 5 GiB)
6. Passer le registre à `RESTORED` et écrire le script de réapplication des attributs `manifests/<runId>-reapply.sh`

Un fichier restauré avait pour propriétaire 0:1, pour mode 644, et une date de modification égale à l'heure de la restauration (une vérification dans l'environnement ci-dessus). Les valeurs d'origine ne sont pas restaurées par `CopyObject`.
## Approbation
La notification d'approbation ne contient pas le jeton. Le jeton se trouve dans un SecureString d'AWS Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). La personne qui approuve doit avoir l'autorisation de lire ce paramètre ainsi que `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# Refuser :
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` est déclaratif. La valeur saisie est inscrite dans `deletedBy` du registre, mais la preuve de qui a réellement approuvé est l'événement `SendTaskSuccess` de CloudTrail. Si `approver` est vide, ou si `approved` n'est pas `true`, rien n'est supprimé.
## Réapplication des attributs
À la fin d'une restauration, `manifests/<runId>-reapply.sh` est écrit. Exécutez-le en tant que root sur un hôte qui monte le volume en NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
Le script ne contient que `chown`, `chmod` et `touch -d`. Les valeurs du registre sont contrôlées selon des formats stricts, et chaque clé devient un seul mot du shell grâce au guillemetage. Une valeur qui ne correspond pas devient un commentaire et n'est pas exécutée. On n'a pas vérifié si l'API REST d'ONTAP peut définir le propriétaire, le groupe, le mode et la date de modification ; cette voie n'est donc pas implémentée.
## Déploiement
### Prérequis
- L'alias et l'ARN de l'Access Point (IAM exige les deux formes ; une politique avec l'alias seul peut se déployer et être refusée à l'exécution)
- Un nom pour le compartiment d'archive (la pile le crée avec `DeletionPolicy: Retain`, Block Public Access, SSE-S3 par défaut, KMS facultatif, notifications EventBridge activées, TLS obligatoire)
- Seulement pour `selection=ATIME` et la capture des attributs : un VPC, des sous-réseaux, le secret contenant les identifiants ONTAP, le point de terminaison de gestion et l'UUID du volume. Il faut un chemin de la fonction Lambda du VPC vers Secrets Manager et S3 (points de terminaison de VPC ou NAT)
- Seulement pour les fichiers de plus de 5 GiB : une image dans ECR. L'Access Point est d'origine Internet : les sous-réseaux de Fargate ont donc besoin d'un NAT ou d'une adresse IP publique
### Étapes
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # remplacer <PLACEHOLDER>
sam build && sam deploy
```
Pour utiliser Fargate, construisez l'image depuis la racine du dépôt, poussez-la dans votre propre dépôt ECR et indiquez-la dans `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Lancez d'abord avec une entrée qui omet `dryRun` (donc `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
Pour supprimer, passez `"dryRun": false` sous forme de booléen JSON. La chaîne `"false"` est une erreur d'entrée et rien n'est supprimé.
## Structure du répertoire
```
archive-verify-delete/
├── template.yaml                # SAM : compartiment, registre, 8 fonctions Lambda, 2 machines d'états, Fargate (facultatif)
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
La logique métier (sommes de contrôle, validation des entrées, registre) se trouve dans [`shared/archive_verify/`](../../../shared/archive_verify/) et est testée dans `shared/tests/`. Les lectures et écritures vers l'Access Point passent par `shared/s3ap_helper.py`.
## Tests locaux
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Pour confirmer qu'un contrôle de suppression défaillant est détecté, `test_does_not_delete_when_etag_changed` et `test_does_not_delete_when_size_differs_but_etag_equal` ont été exécutés une fois contre un bouchon dont la comparaison d'ETag était retirée ; les deux ont échoué avec `assert 'DELETED' == 'CHANGED'`. Une fois le contrôle rétabli, 29 tests réussissent.
## Success Metrics
### Outcome
Déplacer les fichiers rarement lus vers des classes de stockage S3 Glacier après vérification et approbation humaine, réduire l'occupation du volume, et pouvoir retrouver et restaurer les fichiers déplacés à partir du registre.
### Metrics
Les cibles sont fixées par l'exploitant. Aucun chiffre n'est donné ici.
| Catégorie | Indicateur | Définition |
|---|---|---|
| Business Outcome | Capacité libérée | `bytesDeleted` (`-result.json`). L'occupation du volume ne baisse pas tant que des snapshots subsistent |
| Technical KPI | Taux de concordance de la vérification | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Fichiers non supprimés | Total de `CHANGED`, `MISMATCH` et `FAILED` |
| Quality KPI | Fichiers supprimés sans approbation | Doit être 0. Compter les `DELETED` dont `deletedBy` est vide |
| Cost KPI | Par exécution : Lambda, Fargate, DynamoDB, requêtes S3, stockage de la classe d'archive | Non mesuré. Estimer d'abord avec `dryRun=true` et un `maxFiles` faible |
| Go / No-Go | Dans une exécution de bout en bout sur un environnement réel, tous les fichiers copiés passent à `VERIFIED`, un `CHANGED` créé volontairement n'est pas supprimé, et le SHA-256 d'un fichier restauré concorde | Ne pas utiliser `dryRun=false` sur un volume de production tant que ces conditions ne sont pas remplies |
### Measurement Method
Historique d'exécution de Step Functions, `manifests/<runId>-result.json`, métriques EMF de CloudWatch (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `BytesVerified`, `BytesDeleted`), et registre.
## Performance Considerations
Non mesuré. Voici les facteurs de conception.
- Le fichier source est lu deux fois. La première lecture passe par l'Access Point pour calculer le hachage, la seconde est la lecture côté serveur de `CopyObject`. Les requêtes de lecture sont facturées, et pour les données situées dans le pool de capacité, la lecture du pool de capacité l'est aussi
- Le parallélisme est `MapConcurrency` (10 par défaut). Commencez bas et ajustez selon la charge sur l'Access Point et sur ONTAP
- La limite de Lambda est de 15 minutes. La vitesse de lecture depuis l'Access Point n'a pas été mesurée ; on ne sait donc pas si la valeur par défaut de 5 GiB pour `LargeFileThresholdBytes` suffit. Sinon, abaissez-la ; Fargate prend alors plus de fichiers
- Le listage charge tous les résultats de `ListObjectsV2` dans la mémoire d'une seule fonction Lambda. Au-delà de quelques millions d'objets, répartissez le travail avec `prefix`
- `selection=ATIME` parcourt les répertoires en profondeur d'abord. La limite d'analyse est de 200 000 entrées (`ONTAP_SCAN_LIMIT`) ; au-delà, le résultat partiel est renvoyé
- Le temps d'attente d'une restauration dépend de la classe et de `tier`. AWS indique pour S3 Glacier Deep Archive moins de 12 heures en Standard et moins de 48 heures en Bulk. La valeur par défaut de `RestoreMaxWaitHours` est 72
## Governance Note
> Ce modèle fournit des orientations d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Consultez des professionnels qualifiés au sein de votre organisation.
- Le résultat de la vérification et l'approbation sont des signaux d'aide à la décision finale d'une personne. Aucune IA n'est utilisée
- Si des durées de conservation ou une immutabilité sont requises, ce modèle n'y répond pas. Il n'utilise ni Object Lock ni équivalent : toute personne autorisée peut supprimer
- Classification des sorties : le registre et les manifestes contiennent des chemins de fichiers, des tailles, des hachages et des attributs (`dataClassification: operational-metadata`). Le contenu des fichiers va dans le compartiment d'archive ; traitez-le avec la même classification que les données d'origine
- Human Review : l'approbation est exigée pour chaque exécution. Il n'y a pas d'approbation automatique fondée sur un niveau de confiance
- IAM : seul le rôle de la fonction `delete` détient `s3:DeleteObject`. La tâche Fargate ne fait que copier et n'a aucune autorisation de suppression. Personne n'a l'autorisation de supprimer des éléments du registre
- Audit : l'approbation et la suppression sont consignées dans le registre (`deletedBy`, `deletedAt`), dans l'historique d'exécution de Step Functions et dans CloudTrail
## Contraintes et points non vérifiés
- Une copie directe d'un Access Point vers un compartiment d'une autre région a renvoyé `AccessDenied` (un Access Point, une fois). La deuxième copie ne vise que des compartiments de la même région
- Vérifié sur un volume de style UNIX. On n'a pas vérifié si une réécriture qui rétablit la date de modification, ou `chown`, est détectée par l'ETag
- Les attributs sont lus via le listage du répertoire. Lire tout le répertoire parent pour un seul fichier est lent pour les grands répertoires
- Le versionnement du compartiment d'archive n'est pas Object Lock. Les versions sont conservées, mais toute personne autorisée peut aussi supprimer des versions
## Documents associés
- [Architecture (EN)](docs/architecture.en.md)
- [Notes de compatibilité de S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Comparaison de 8 mécanismes de déplacement de fichiers vers des classes d'archive](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (en japonais)
