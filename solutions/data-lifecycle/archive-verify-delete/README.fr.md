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
| Vérifié dans ce dépôt | Tests unitaires avec moto, et tests de la structure de la machine d'états et d'IAM. Aucune connexion à AWS. Trois défauts trouvés lors de l'exécution de bout en bout ci-dessus (autorisation d'appel de la fonction API REST d'ONTAP, vérification TLS, nom de l'erreur d'une demande de restauration en double) ont été corrigés avec des tests qui les reproduisent |
| Vérifié une fois chacun lors d'une exécution de bout en bout sur un environnement réel (2026-11-26, même environnement que ci-dessus, `selection=ATIME`, `GLACIER`, 7 fichiers) | Sélection par `accessed_time` et lecture de uid, gid, mode, mtime et atime par l'API REST d'ONTAP (la racine est la racine du volume et le chemin n'a pas de barre oblique initiale ; `unix_permissions` revient sous la forme de l'entier `640`). Le `ItemReader` et le `ResultWriter` de Distributed Map. Une copie multipart de 5,5 GiB par Fargate (avec `CopySourceIfMatch` ; CRC64NVME égal à celui du registre). Le calcul du hachage d'un fichier de 5,3 Go (environ 4,94 GiB) dans Lambda (69,8 s, 2048 Mo configurés, 152 Mo utilisés). La deuxième copie. La suppression après approbation. Un fichier réécrit par NFS pendant l'attente de l'approbation est passé à `CHANGED` et n'a pas été supprimé. Une approbation refusée n'a rien supprimé. Une restauration en `Expedited` (y compris le fichier de 5,5 GiB) et un SHA-256 identique pour les 6 fichiers restaurés (le septième des 7 fichiers avait été réécrit, il n'a donc été ni supprimé ni restauré). Le rétablissement de uid, gid, mode et mtime par `reapply.sh` |
### Environnement et résultat de chaque étape
L'environnement est ap-northeast-1, FSx for ONTAP de première génération `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, un volume de style de sécurité UNIX, et un Access Point dont l'utilisateur du système de fichiers est UNIX root. La date est le 2026-11-26 (heures en heure normale du Japon) et chaque étape a été exécutée une seule fois. La configuration était `selection=ATIME`, `GLACIER`, une deuxième copie, et Fargate en arm64 avec 2 vCPU et 8 GiB. Les données étaient 6 petits fichiers (trois de 64 o et trois de 8 MiB, propriétaire 1234:5678, mode 640, mtime et atime au 2020-01-02) et un fichier de 5 905 580 032 o.
| Étape | Résultat | Durée |
|---|---|---|
| 1. Déploiement | Réussi. Deux défauts découverts à l'exécution ont été corrigés, puis le déploiement refait | Environ 30 minutes de la préparation au déploiement (16:19 à 16:50) |
| 2. Exécution à blanc (`dryRun=true`) | Réussie après les corrections. Les 7 fichiers en `VERIFIED` (SHA-256 identique pour 6, CRC64NVME identique pour 1), la deuxième copie aussi en `VERIFIED`. 0 octet supprimé, et les 7 fichiers sont restés visibles par NFS | 244 s (dont environ 70 s d'attente de l'approbation) |
| 3. Réécriture pendant l'attente de l'approbation | Un fichier a été écrasé par NFS avec 4 KiB de même taille (mtime mis à jour). Après l'approbation il est passé à `CHANGED` (ETag ou taille différents) et n'a pas été supprimé | |
| 4. Exécution réelle (`dryRun=false`) et approbation | 6 fichiers en `DELETED`, 1 en `CHANGED`. `bytesDeleted` valait 5 922 357 440. Par NFS, les 6 fichiers avaient disparu et seul le fichier réécrit restait | 310 s (172 s jusqu'à la demande d'approbation, environ 6 s de l'approbation à la fin) |
| 5. Restauration (`tier=Expedited`, `days=1`) | 6 fichiers en `RESTORED` (y compris celui de 5,5 GiB). SHA-256 identique pour les 6 à la valeur relevée par NFS avant l'étape 1. Le fichier `CHANGED` n'était pas visé | 287 s (les 5 petits fichiers en environ 2,5 minutes ; la copie Fargate de 5,5 GiB a pris 2 min 38 s) |
| 6. Approbation refusée (`send-task-failure`) | L'exécution s'est terminée en `REJECTED_OR_TIMED_OUT`, 3 fichiers sont restés `VERIFIED`, `deletedBy` était vide et les 3 fichiers sont restés visibles par NFS | 16 s |
| En plus : hachage de 5,3 Go (environ 4,94 GiB) dans Lambda | `VERIFIED` (SHA-256 identique à la valeur NFS), la deuxième copie aussi `VERIFIED` | Fonction `record` : 69,8 s (2048 Mo configurés, 152 Mo utilisés) |
| En plus : demande de restauration en double | La deuxième demande a renvoyé HTTP 409 `RestoreAlreadyInProgress`. L'intégration SDK de Step Functions la renvoie sous la forme `S3.S3Exception` | |
Toutes les ressources ont ensuite été supprimées, et la suppression a été confirmée par relecture.
### Consommation (une exécution chacune, pas une facture)
| Exécution | Fichiers | Durée | Transitions d'état (parent + exécutions enfants du Map) | Tâches Fargate |
|---|---|---|---|---|
| À blanc | 7 | 244 s | 12 + 107 = 119 | 2 (hachage et copie 96 s, deuxième copie 35 s) |
| Réelle | 7 | 310 s | 13 + 114 = 127 | 2 (94 s, 35 s) |
| Restauration | 6 | 287 s | 4 + 103 = 107 | 1 (156 s) |
| Refus | 3 | 16 s | 10 + 45 = 55 | 0 |
- Durée totale des fonctions Lambda (CloudWatch ; inclut les invocations en échec, exclut l'exécution de 4,94 GiB) : `select` 13 invocations 5,9 s, `ontap_rest` 11 invocations 13,4 s (2 échecs), `record` 17 invocations 11,7 s, `ledger` 34 invocations 9,1 s, `approval` 6 invocations 4,3 s, `delete` 7 invocations 5,6 s, `summarize` 5 invocations 5,1 s, `restore` 26 invocations 9,2 s
- Fargate : 5 tâches, environ 416 s au total (2 vCPU, 8 GiB, arm64). DynamoDB (à la demande) : 68,5 RCU en lecture et 74 WCU en écriture, cumulés sur toutes les exécutions
- Le nombre de requêtes S3 n'a pas été mesuré (les métriques de requêtes n'étaient pas activées)
### Trois défauts trouvés et corrigés lors de l'exécution de bout en bout
Chacun a été corrigé avec un test qui le reproduit.
| # | Symptôme | Cause et correction |
|---|---|---|
| 1 | Une exécution avec `selection=ATIME` a échoué à l'étape de sélection | Le rôle de la machine d'états d'archivage n'avait pas `lambda:InvokeFunction` sur la fonction API REST d'ONTAP. L'autorisation a été ajoutée |
| 2 | La fonction API REST d'ONTAP a échoué avec `CERTIFICATE_VERIFY_FAILED` | Elle vérifiait toujours TLS, or le certificat du point de terminaison de gestion de FSx for ONTAP n'est pas signé par une autorité publique. Le paramètre `OntapVerifySsl` (par défaut `false`) a été ajouté |
| 3 | Une demande de restauration en double est devenue un échec de fichier | L'intégration SDK de Step Functions renvoie `RestoreAlreadyInProgress` sous la forme `S3.S3Exception`, de sorte que le `Catch` sur `S3.RestoreAlreadyInProgressException` ne correspondait pas. Une restauration en cours est désormais dirigée vers la boucle d'attente |
### Comportements observés lors de l'exécution de bout en bout
Ils n'ont pas été traités comme des défauts.
- Avec `selection=ATIME`, les lectures du modèle lui-même mettent à jour `accessed_time`. Après une exécution avec `dryRun=true`, les lectures du calcul de hachage placent l'atime des fichiers à l'heure d'exécution, si bien que la même entrée avec `dryRun=false` ne sélectionne rien (elle s'est terminée avec 0 fichier ; constaté quand une exécution réelle a suivi une exécution à blanc). Une exécution à blanc fait donc paraître les fichiers récemment lus. Pour lancer l'exécution réelle sur les mêmes candidats juste après une exécution à blanc, utilisez `selection=MTIME` (`LastModified` ne change pas à la lecture)
- L'ETag de l'Access Point suit le mtime et la taille, pas le contenu. Trois fichiers de contenus différents mais de même taille et de même mtime ont renvoyé le même ETag. La vérification de l'ETag et de la taille avant suppression ne détecte donc pas une modification du contenu qui conserve la taille et le mtime. Une réécriture qui conservait la taille mais mettait à jour le mtime a été détectée (étape 3)
- Supprimer le dernier fichier d'un répertoire par l'Access Point supprime aussi le répertoire parent devenu vide (constaté avec `arc-e2e/large/`). Le `CopyObject` de la restauration recrée le parent
- Un fichier restauré avait pour propriétaire 0:1, pour mode 644 et pour date de modification l'heure de la restauration. L'exécution du `reapply.sh` généré, en root sur un hôte qui monte le volume par NFS, a rétabli les uid, gid, mode et mtime d'origine (1234:5678, 640, 2020-01-02 03:04:05), et le SHA-256 du contenu n'a pas changé
- L'exécution a utilisé une politique d'Access Point qui autorise chaque rôle (les rôles des fonctions `select`, `record`, `delete` et `restore`, le rôle de la tâche Fargate et les rôles des deux machines d'états)
- Une demande de restauration `Expedited` de 5,5 GiB a été acceptée et s'est terminée en 4 minutes environ ou moins
### Points non vérifiés
- Durée et coût avec de nombreux fichiers
- Fin des restaurations `Standard` et `Bulk` (seul `Expedited` a été exécuté)
- Nouvelle tentative sur `S3.SlowDownException` (le nom renvoyé par l'intégration SDK n'a pas été observé, et un écart du même type que le défaut 3 est possible)
- Enregistrements des suppressions dans les événements de données de CloudTrail (on n'a pas vérifié si le journal de suivi du compte couvre les événements de données de cet Access Point)
- Volumes NTFS, utilisateurs autres que root, deuxième génération, Multi-AZ
- Comportement lorsque l'Access Point n'a pas de politique
- Le chemin `EXISTS` de la restauration (un fichier de même nom déjà présent sur NFS) ; le seul cas ignoré observé est le fichier `CHANGED` non sélectionné
- Une exécution ayant trouvé 0 candidat reste inexpliquée. Une exécution environ 10 secondes après le rétablissement de l'atime par `touch -d` a trouvé 0 candidat. Une vérification environ 17 minutes plus tard a renvoyé la valeur de 2020, et une autre vérification juste après `touch` a renvoyé 6 fichiers. La cause n'a pas été identifiée et le cas n'a pas été reproduit
### Fenêtre d'écriture restante avant la suppression
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
- Seulement pour `selection=ATIME` et la capture des attributs : un VPC, des sous-réseaux, le secret contenant les identifiants ONTAP, le point de terminaison de gestion, l'UUID du volume et `OntapVerifySsl`. Le certificat du point de terminaison de gestion de FSx for ONTAP n'est pas signé par une autorité publique ; la valeur par défaut est donc `false` (pas de vérification), et les identifiants ONTAP sont alors envoyés sur une connexion dont l'homologue n'est pas authentifié (le chemin reste dans le VPC). Avec `true`, la sélection s'est arrêtée sur une erreur de certificat (observé). Il faut une route de la fonction Lambda du VPC vers Secrets Manager et S3 (points de terminaison de VPC ou NAT)
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
- Vérifié sur un volume de style UNIX. Une modification du contenu qui conserve la taille et le mtime n'est pas détectée par la vérification de l'ETag et de la taille (voir « Comportements observés lors de l'exécution de bout en bout » plus haut). On n'a pas vérifié si `chown` modifie l'ETag
- Les attributs sont lus via le listage du répertoire. Lire tout le répertoire parent pour un seul fichier est lent pour les grands répertoires
- Le versionnement du compartiment d'archive n'est pas Object Lock. Les versions sont conservées, mais toute personne autorisée peut aussi supprimer des versions
## Documents associés
- [Architecture (EN)](docs/architecture.en.md)
- [Notes de compatibilité de S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Comparaison de 8 mécanismes de déplacement de fichiers vers des classes d'archive](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (en japonais)

---

<!-- playbook-reading:start -->
## À lire avant la mise en production

La façon de traduire en décisions de conception les contraintes qui apparaissent après le déploiement est documentée dans le [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). Un même contenu présent à deux endroits laisse survivre la copie qui a cessé d'être mise à jour.

- [Exploitation des données](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — contraintes de l'accès via un access point (tous les patterns)
- [Protection des données](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — là où se concentrent les décisions pour ce pattern
- [Construire](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — à parcourir avant la production (tous les patterns)
<!-- playbook-reading:end -->
