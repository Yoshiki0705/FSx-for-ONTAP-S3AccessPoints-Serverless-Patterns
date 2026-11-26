# archive-verify-delete : archivage avec les seuls appels d'API S3, copie, vérification, puis suppression après approbation
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation** : [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Vue d'ensemble
Ce modèle déplace vers des classes de stockage S3 Glacier les fichiers rarement lus d'un volume Amazon FSx for NetApp ONTAP (FSx for ONTAP). La lecture, l'écriture et la suppression des fichiers passent par l'API S3 de S3 Access Points ; aucun montage NFS n'est utilisé pour cela. Deux opérations demandent davantage : la sélection par date de dernier accès (`selection=ATIME`) et la capture des attributs utilisent l'API REST d'ONTAP (une fonction Lambda dans le VPC, des identifiants ONTAP, le point de terminaison de gestion), et rétablir le propriétaire, le mode et la date de modification après une restauration demande un hôte qui monte le volume en NFS.
Un fichier suit les étapes ci-dessous, et un fichier dont les conditions cessent d'être remplies à l'une des étapes est exclu de la suppression.
1. Enregistrer sa taille, son ETag, son SHA-256 et son CRC64NVME dans le registre (une table DynamoDB)
2. Le copier dans le compartiment d'archive avec `CopyObject`, en indiquant la classe de stockage (clé `<prefix><runId>/<original key>`)
3. Comparer la somme de contrôle renvoyée par le compartiment avec la valeur du registre
4. Une personne approuve la liste des fichiers concordants. L'approbation est consignée dans le registre comme `APPROVED`, et elle est refusée lorsque la personne qui approuve est le principal qui a lancé l'exécution (par défaut)
5. Seuls les fichiers que le registre indique comme `APPROVED` sont supprimés, après vérification que l'ETag et la taille côté Access Point sont toujours identiques à ceux du registre

Pour restaurer, le modèle retrouve les fichiers dans le registre, demande la restauration dans le compartiment, attend qu'elle se termine, recopie les fichiers vers l'Access Point avec `CopyObject`, puis relit chaque fichier restauré et le compare avec le SHA-256 et le CRC64NVME du registre.
Ce modèle n'utilise ni S3 Object Lock, ni S3 Glacier Vault Lock, ni AWS Backup Vault Lock, ni SnapLock, ni le verrouillage de snapshots, et le modèle de déploiement n'en contient aucun. Aucune durée de conservation n'est définie : les objets du compartiment d'archive peuvent être supprimés par toute personne qui en a l'autorisation.
Les hypothèses de ce modèle et sa comparaison avec d'autres approches se trouvent dans [Comparaison de 8 mécanismes de déplacement de fichiers vers des classes d'archive](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md).
## Ce qui a été mesuré et ce qui ne l'a pas été
| Catégorie | Contenu |
|---|---|
| Composants vérifiés une fois chacun sur un environnement réel (consignés dans la comparaison ci-dessus ; 2026-11-24 et 2026-11-26, ap-northeast-1, première génération `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, volume de style UNIX, l'utilisateur de l'Access Point est UNIX root) | Avec `ChecksumAlgorithm=SHA256` sur `CopyObject`, le `ChecksumSHA256` du compartiment était `FULL_OBJECT` et égal au SHA-256 du fichier (jusqu'à 8 MiB). Pour une copie multipart de 5,5 GiB, le SHA-256 est devenu `COMPOSITE` et le CRC64NVME était `FULL_OBJECT` et égal. `--copy-source-if-match` avec un ancien ETag a renvoyé `PreconditionFailed`. Le `DeleteObject` de l'Access Point ne prend pas en charge `If-Match`. Une intégration SDK de Step Functions a accepté l'alias de l'Access Point comme `Bucket` |
| Vérifié dans ce dépôt | Tests unitaires avec moto, et tests de la structure de la machine d'états et d'IAM. Aucune connexion à AWS. Six défauts trouvés lors des exécutions de bout en bout ci-dessus (autorisation d'appel de la fonction API REST d'ONTAP, vérification TLS, nom de l'erreur d'une demande de restauration en double, autorisation de journalisation des machines d'états, 403 renvoyé par `HeadObject`, autorisation de publication des alarmes) ont été corrigés avec des tests qui les reproduisent |
| Vérifié une fois chacun lors d'une exécution de bout en bout sur un environnement réel (2026-11-26, même environnement que ci-dessus, `selection=ATIME`, `GLACIER`, 7 fichiers) | Sélection par `accessed_time` et lecture de uid, gid, mode, mtime et atime par l'API REST d'ONTAP (la racine est la racine du volume et le chemin n'a pas de barre oblique initiale ; `unix_permissions` revient sous la forme de l'entier `640`). Le `ItemReader` et le `ResultWriter` de Distributed Map. Une copie multipart de 5,5 GiB par Fargate (avec `CopySourceIfMatch` ; CRC64NVME égal à celui du registre). Le calcul du hachage d'un fichier de 5,3 Go (environ 4,94 GiB) dans Lambda (69,8 s, 2048 Mo configurés, 152 Mo utilisés). La deuxième copie. La suppression après approbation. Un fichier réécrit par NFS pendant l'attente de l'approbation est passé à `CHANGED` et n'a pas été supprimé. Une approbation refusée n'a rien supprimé. Une restauration en `Expedited` (y compris le fichier de 5,5 GiB) et un SHA-256 identique pour les 6 fichiers restaurés (le septième des 7 fichiers avait été réécrit, il n'a donc été ni supprimé ni restauré). Le rétablissement de uid, gid, mode et mtime par `reapply.sh` |
| Vérifié une fois chacun lors d'une deuxième exécution de bout en bout (2026-11-26, même environnement, `GLACIER`, deuxième copie activée. Exécution à blanc avec `selection=ATIME`, exécution réelle avec `selection=MTIME` et attributs issus de l'API REST d'ONTAP. Fichiers de 64 o à 1 MiB et un fichier creux de 51 GiB) | Le comportement a changé après relecture. Avec `maxFiles=50`, trois fichiers de 64 o et un fichier de 131 071 o sont passés sous la taille minimale et un fichier de 131 073 o est resté. `*.vmdk` et un préfixe de conservation légale ont été exclus. Le fichier creux de 51 GiB a été consigné comme `SKIPPED_TOO_LARGE` et n'a pas été copié. Un `runId` réutilisé et une entrée d'exécution réelle sans `requestedBy` se sont arrêtés comme erreurs d'entrée. Une approbation avec le même ARN que celui qui a lancé l'exécution s'est terminée en `APPROVAL_REFUSED` et rien n'a été supprimé. L'appel direct de la fonction `delete` sans approbation a renvoyé `NOT_APPROVED` et n'a rien supprimé. Avec un autre approbateur, 3 fichiers ont été supprimés et le fichier réécrit pendant l'attente est resté `CHANGED`. Sur des éléments mis à `DELETING` pour simuler une interruption, une nouvelle tentative de la même exécution a consigné `DELETED` (`already gone on retry`), une autre exécution a été refusée, et `reconcile` a consigné `DELETED`. Après la restauration, 3 fichiers étaient `RESTORE_VERIFIED`. Les alarmes ont été publiées sur la rubrique chiffrée par KMS (après correction) |
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
Transitions d'état de la deuxième exécution (2026-11-26, petits fichiers, deuxième copie activée, `MapConcurrency=2`), une exécution chacune ; elles varient selon la taille des fichiers et le chemin.

| Exécution | Fichiers | Durée | Transitions d'état (parent + exécutions enfants du Map) | Par fichier |
|---|---|---|---|---|
| À blanc `e2e2-dry1` | 4 | 66 s (dont environ 20 s d'attente de l'approbation) | 12 + 60 = 72 | 18 |
| Réelle `e2e2-real2` (3 supprimés, 1 `CHANGED`) | 4 | 45 s (dont l'attente de l'approbation) | 14 + 64 = 78 | 19,5 |
| Restauration `e2e2-rest2` (Expedited, avec vérification, 1 `EXISTS`) | 4 | 192 s | 4 + 52 = 56 | 14 |
### Défauts trouvés et corrigés lors des exécutions de bout en bout
Chacun a été corrigé avec un test qui le reproduit.
| # | Symptôme | Cause et correction |
|---|---|---|
| 1 | Une exécution avec `selection=ATIME` a échoué à l'étape de sélection | Le rôle de la machine d'états d'archivage n'avait pas `lambda:InvokeFunction` sur la fonction API REST d'ONTAP. L'autorisation a été ajoutée |
| 2 | La fonction API REST d'ONTAP a échoué avec `CERTIFICATE_VERIFY_FAILED` | Elle vérifiait toujours TLS, or le certificat du point de terminaison de gestion de FSx for ONTAP n'est pas signé par une autorité publique. Le paramètre `OntapVerifySsl` (par défaut `false`) a été ajouté |
| 3 | Une demande de restauration en double est devenue un échec de fichier | L'intégration SDK de Step Functions renvoie `RestoreAlreadyInProgress` sous la forme `S3.S3Exception`, de sorte que le `Catch` sur `S3.RestoreAlreadyInProgressException` ne correspondait pas. Une restauration en cours est désormais dirigée vers la boucle d'attente |
La deuxième exécution (2026-11-26) a trouvé et corrigé trois défauts de plus.

| # | Symptôme | Cause et correction |
|---|---|---|
| 4 | Le déploiement a échoué avec `The state machine IAM Role is not authorized to access the Log Destination` | Les rôles des machines d'états n'avaient pas `logs:CreateLogDelivery` ni les autorisations associées que demande la journalisation des exécutions. Elles ont été ajoutées |
| 5 | Une nouvelle tentative de suppression et `reconcile` ont reçu un 403 de `HeadObject` sur un fichier supprimé | Pour un appelant sans `s3:ListBucket`, `HeadObject` sur une clé absente renvoie 403 et non 404. `s3:ListBucket` a été ajouté aux fonctions `delete` et `restore`, dans IAM et dans la politique de l'Access Point |
| 6 | Les notifications des alarmes CloudWatch ont échoué avec `CloudWatch Alarms is not authorized to perform: SNS:Publish` | La politique de clé autorisait CloudWatch, mais la politique de la rubrique n'autorisait qu'EventBridge. Une instruction `cloudwatch.amazonaws.com` a été ajoutée |
### Comportements observés lors de l'exécution de bout en bout
Ils n'ont pas été traités comme des défauts.
- Avec `selection=ATIME`, les lectures du modèle lui-même mettent à jour `accessed_time`. Après une exécution avec `dryRun=true`, les lectures du calcul de hachage placent l'atime de chaque fichier à l'heure d'exécution, si bien que la même entrée avec `dryRun=false` ne sélectionne rien (elle s'est terminée avec 0 fichier quand l'exécution réelle a suivi l'exécution à blanc). Pour lancer l'exécution réelle sur les mêmes candidats juste après une exécution à blanc, utilisez `selection=MTIME` (`LastModified` ne change pas à la lecture)
- Sur l'ETag, voici la formulation officielle et la mesure faite ici. La page officielle ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), lue le 2026-11-26) indique "The ETag reflects changes only to the contents of an object, not its metadata". Dans une mesure faite dans cet environnement, trois fichiers de même taille et de même mtime mais de contenus différents ont renvoyé le même ETag. Le modèle considère donc que la vérification de l'ETag et de la taille avant suppression ne peut pas détecter une modification du contenu qui conserve la taille et le mtime. Une réécriture de même taille qui a mis à jour le mtime pendant l'attente de l'approbation a été détectée (étape 3 de la première exécution, et deuxième exécution réelle) [E-023]
- Supprimer le dernier fichier d'un répertoire par l'Access Point supprime aussi le répertoire parent devenu vide (constaté avec `arc-e2e/large/`). Le `CopyObject` de la restauration le recrée
- Un fichier restauré avait pour propriétaire 0:1, pour mode 644 et pour date de modification l'heure de la restauration. L'exécution du `reapply.sh` généré, en root sur un hôte qui monte le volume par NFS, a rétabli les uid, gid, mode et mtime d'origine (1234:5678, 640, 2020-01-02 03:04:05) sans changer le SHA-256 du contenu
- La machine d'états de restauration sélectionne aussi un fichier resté `CHANGED` lorsque le compartiment d'archive en contient la copie. Si l'Access Point contient déjà la clé, elle reste `EXISTS` et n'est pas écrasée (constaté une fois lors de la deuxième restauration)
- Une demande de restauration `Expedited` du fichier de 5,5 GiB a été acceptée et s'est terminée en 4 minutes environ
### Points non vérifiés
- Durée et coût avec de nombreux fichiers. Débit du système de fichiers et latence des clients avec d'autres réglages de parallélisme
- Fin des restaurations `Standard` et `Bulk` (seul `Expedited` a été exécuté)
- Nouvelle tentative sur `S3.SlowDownException` (le nom renvoyé par l'intégration SDK n'a pas été observé ; un écart du même type que le défaut 3 est possible)
- Suppressions et approbations dans les événements de données de CloudTrail. Les événements de données S3 (`DeleteObject` et autres) ne sont enregistrés que si un journal de suivi a les événements de données activés. Cette exécution n'a pas vérifié si le journal de suivi du compte couvre les événements de données de cet Access Point. `SendTaskSuccess` est un événement de gestion ; son enregistrement n'a pas été vérifié non plus
- Le refus et l'acceptation d'une approbation ont été comparés avec le même principal SSO déclarant des ARN différents dans la sortie d'approbation. La valeur de l'approbateur est déclarative, un autre principal IAM devrait donc donner le même résultat, mais un véritable second principal n'a pas été utilisé
- Copie et restauration de fichiers de plus de 50 GiB (seule leur exclusion de la sélection a été vérifiée, avec un fichier creux)
- Volumes NTFS, utilisateurs autres que root, deuxième génération, Multi-AZ
- Dans la restauration, le chemin `EXISTS` autre que la non-sélection des fichiers `CHANGED` (un fichier de même nom sur NFS)
- Attente jusqu'à ce que `ApprovalPendingAlarm` passe réellement à `ALARM` (seule la publication de la métrique a été vérifiée)
- Un cas de zéro candidat reste inexpliqué. Une exécution environ 10 secondes après le rétablissement de l'atime par `touch -d` n'a trouvé aucun candidat. Une vérification environ 17 minutes plus tard a renvoyé les valeurs de 2020, et d'autres vérifications ont aussi renvoyé 6 fichiers. La cause n'a pas été identifiée et le cas ne s'est pas reproduit
### Fenêtre d'écriture restante avant la suppression
Une fenêtre d'écriture subsiste dans la vérification avant suppression. Le `DeleteObject` de l'Access Point ne prend pas en charge la suppression conditionnelle : une écriture survenue entre la vérification par `HeadObject` et la suppression n'est donc pas détectée. La fenêtre correspond à un aller-retour d'appel d'API.
## Déroulement
### Archivage
`olderThanDays` est obligatoire. `dryRun` vaut `true` par défaut. Une exécution avec `dryRun=false` demande l'ARN du principal qui lance l'exécution dans `requestedBy` lorsque `RequireSeparateApprover=true` (par défaut).
| Étape | Traitement | Implémentation |
|---|---|---|
| 1. Sélectionner | `MTIME` : `LastModified` du `ListObjectsV2` de l'Access Point. `ATIME` : `accessed_time` de l'API REST d'ONTAP (Lambda dans le VPC). Appliquer les exclusions (tableau ci-dessous) | `select`, `ontap_rest` |
| 2. Enregistrer | Taille, ETag, SHA-256, CRC64NVME et, si disponibles, uid, gid, mode, mtime, atime, dans le registre. Lambda jusqu'à 5 GiB, Fargate au-delà | `record`, tâche Fargate |
| 3. Copier | Jusqu'à 5 GiB : `copyObject` par intégration SDK (`SHA256`, l'ETag du registre comme `CopySourceIfMatch`). Au-delà : copie multipart par Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Vérifier | Comparer la taille et la somme de contrôle du `HeadObject` du compartiment (`ChecksumMode=ENABLED`) avec le registre. Une différence reste `MISMATCH` et le fichier est exclu de la suppression | `ledger` |
| 5. Deuxième copie (facultative) | Copier de l'Access Point vers un autre compartiment de la même région et vérifier de la même façon. Une différence retire le fichier de la suppression | Step Functions, `ledger` |
| 6. Approuver | Écrire la liste des fichiers concordants dans `manifests/<runId>.json`, notifier par SNS et attendre avec `waitForTaskToken`. La notification le précise lorsqu'il n'existe qu'une seule copie et lorsque des fichiers ne peuvent pas être restaurés | `approval` |
| 7. Consigner l'approbation | Seulement si `dryRun=false`. Refuser lorsque la personne qui approuve est celle qui a lancé l'exécution. Sinon, faire passer chaque fichier de la liste de `VERIFIED` à `APPROVED` dans le registre et écrire `manifests/<runId>-approval.json` | `approval` |
| 8. Supprimer | Seulement les fichiers que le registre indique comme `APPROVED`. Vérifier l'ETag et la taille pour chaque fichier ; `DeleteObject` s'ils sont identiques, sinon conserver comme `CHANGED` | `delete` |
| 9. Consigner | `manifests/<runId>-result.json` et métriques EMF (nombres, octets, exclusions). `COMPLETED_WITH_ERRORS` lorsqu'il reste des éléments `DELETING` ou `APPROVED` | `summarize` |
Avec `dryRun=true`, l'exécution va quand même jusqu'à l'étape 6. Les copies sont faites et le stockage de la classe d'archive est facturé (avec une durée de stockage minimale). Pour un essai, utilisez un `maxFiles` faible. Rien n'est supprimé.
Les statuts du registre progressent dans l'ordre `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED`, avec les sorties latérales `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE` et `RESTORE_MISMATCH`. Seuls les fichiers `APPROVED` (et, lorsqu'une deuxième copie est exigée, dont la deuxième copie est aussi vérifiée) peuvent être supprimés.

Un `runId` déjà utilisé est une erreur d'entrée. Pour poursuivre une exécution interrompue, indiquez le même `runId` avec `"resume": true` (voir « Reprise après une suppression interrompue » plus bas). La clé d'archive contient le `runId` : une exécution à blanc et une exécution réelle, ou un nouvel archivage après une réécriture, n'écrasent donc pas les objets les uns des autres. Sans versionnement, un écrasement supprime l'objet précédent, ce qui peut entraîner des frais de suppression anticipée dans les classes à durée de stockage minimale.

Ce que la sélection laisse de côté :

| Condition | Par défaut | Raison |
|---|---|---|
| Au-delà de 50 GiB | Exclu et consigné comme `SKIPPED_TOO_LARGE` dans le registre. `allowOversize: true` les inclut | La page officielle ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), lue le 2026-11-26) indique "Maximum object size is 50 GiB for uploads, but you can download objects larger than that". Une restauration écrit par l'Access Point : ce modèle ne peut donc pas y restaurer un fichier plus grand (il peut être téléchargé directement depuis le compartiment) [E-021] |
| En dessous de `MinFileSizeBytes` | 131 072 octets (128 KiB). Le `minSizeBytes` de l'entrée le modifie | Selon [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare) (lu le 2026-11-26), S3 Standard-IA et S3 Glacier Instant Retrieval facturent au moins 128 KB par objet, et S3 Glacier Flexible Retrieval et S3 Glacier Deep Archive ajoutent 40 KB de métadonnées par objet (32 KB au tarif de cette classe, 8 KB au tarif de S3 Standard). Pour de petits fichiers, cela dépasse les données elles-mêmes |
| `ExcludePatterns` (globs), `ExcludePrefixes` | Vide | Les valeurs de la pile s'appliquent toujours ; `excludePatterns` et `excludePrefixes` de l'entrée ne peuvent qu'en ajouter. Placez-y les préfixes sous conservation légale |

Excluez toujours les fichiers de données des tables Iceberg, Delta ou Hive, les fichiers d'une base de données en fonctionnement et les images disque de machines virtuelles (`*.vmdk`, `*.vhd`, `*.qcow2` et similaires). Le modèle déplace les fichiers un par un et ne sait rien des métadonnées de table ni du processus qui tient un fichier ouvert. Nettoyez une table avec ses propres fonctions (détacher des partitions, faire expirer des snapshots) et ne visez que les chemins restants. Savoir si des données sont sous conservation légale est une décision de votre service juridique ; le modèle ne la prend pas.
### Restauration
L'entrée est `runId` et exactement l'un de `keys` ou `prefix`. On peut indiquer `tier` (`Bulk` par défaut) et `days` (7 par défaut).
1. Sélectionner dans le registre les fichiers `DELETED`. Les fichiers `DELETING` et `CHANGED` sont aussi sélectionnés lorsque le compartiment d'archive en contient la copie (ce qui permet de restaurer les éléments laissés par une suppression interrompue)
2. Si l'Access Point contient déjà la même clé, la consigner comme `EXISTS` et ne pas écraser
3. Demander `RestoreObject` pour les objets de S3 Glacier Flexible Retrieval et de S3 Glacier Deep Archive (inutile pour S3 Glacier Instant Retrieval)
4. L'achèvement est interrogé par sondage : toutes les `RestorePollMinutes`, l'en-tête `Restore` de `HeadObject` est lu, et l'attente s'arrête à `RestoreMaxWaitHours`. L'événement EventBridge `Object Restore Completed` n'est pas utilisé ; les notifications EventBridge sont activées sur le compartiment, ce qui permet de changer plus tard
5. `CopyObject` du compartiment vers l'Access Point (Fargate au-delà de 5 GiB). Le registre indique `RESTORED`
6. Relire le fichier restauré par l'Access Point, calculer son hachage et le comparer avec le SHA-256, le CRC64NVME et la taille du registre (Fargate au-delà de 5 GiB). Une concordance donne `RESTORE_VERIFIED`, une différence `RESTORE_MISMATCH`
7. Écrire le script de réapplication des attributs `manifests/<runId>-reapply.sh`, uniquement pour les fichiers `RESTORE_VERIFIED`

Un fichier restauré avait pour propriétaire 0:1, pour mode 644, et une date de modification égale à l'heure de la restauration (vérifié dans l'environnement ci-dessus). Les valeurs d'origine ne sont pas restaurées par `CopyObject`.
### Reprise après une suppression interrompue
Une fonction Lambda qui s'arrête en pleine suppression ou qui a épuisé ses nouvelles tentatives peut laisser des éléments `DELETING` ou `APPROVED` dans le registre. Le résultat l'indique par `COMPLETED_WITH_ERRORS`, `stuckDeleting` et `notDeleted`, et `FilesStuckDeletingAlarm` se déclenche. Démarrer la machine d'états d'archivage avec le même `runId` et `"resume": true` exécute `reconcile`, qui règle les éléments comme ci-dessous, puis demande une nouvelle approbation pour les fichiers restants.
| Registre | Access Point | Résultat |
|---|---|---|
| `DELETING` | Pas de fichier | `DELETED` (la suppression avait eu lieu ; `reconciled: true`) |
| `DELETING`, `APPROVED` | Fichier présent, ETag et taille identiques au registre | Retour à `VERIFIED` ; la suppression demande une nouvelle approbation |
| `DELETING`, `APPROVED` | Fichier présent, différent du registre | `CHANGED` |
| L'un ou l'autre | L'exécution qui détient l'élément est encore en cours | Laissé tel quel |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
Lorsqu'un élément resté `DELETING` doit être récupéré, la machine d'états de restauration le restaure à partir de la copie du compartiment d'archive.
## Approbation
La notification d'approbation ne contient pas le jeton. Le jeton se trouve dans un SecureString d'AWS Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). La personne qui approuve doit avoir l'autorisation de lire ce paramètre ainsi que d'appeler `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# Reject:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
Après l'approbation, la fonction `approval` compare `approver` avec le `requestedBy` de l'entrée de démarrage (`RequireSeparateApprover=true`, par défaut). Le même principal termine l'exécution en `APPROVAL_REFUSED`, sans rien marquer `APPROVED`. L'ARN d'un rôle et l'ARN d'une session de ce rôle comptent comme le même principal. Sinon, chaque fichier de la liste passe à `APPROVED` dans le registre avec `approvedBy`, `approvedAt` et l'ARN de l'exécution. La fonction `delete` ne supprime que les fichiers qui portent cet enregistrement ; l'appeler directement ne supprime rien de ce qui n'en a pas.

`approver` et `requestedBy` sont tous deux déclarés par les appelants. Le `deletedBy` du registre est repris de son `approvedBy`. Les principaux qui ont réellement lancé et approuvé figurent dans les événements `StartExecution` et `SendTaskSuccess` de CloudTrail. Pour garantir la séparation des tâches par principal, séparez dans IAM les rôles qui lancent et ceux qui approuvent.
## Réapplication des attributs
À la fin d'une restauration, `manifests/<runId>-reapply.sh` est écrit. Exécutez-le en tant que root sur un hôte qui monte le volume en NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
Le script ne contient que `chown`, `chmod` et `touch -d`. Les valeurs du registre sont contrôlées selon des formats stricts, et chaque clé devient un seul mot du shell grâce au guillemetage. Une valeur qui ne correspond pas devient un commentaire et n'est pas exécutée. On n'a pas vérifié si l'API REST d'ONTAP peut définir le propriétaire, le groupe, le mode et la date de modification ; cette voie n'est donc pas implémentée.
## Déploiement
### Prérequis
- L'alias et l'ARN de l'Access Point (IAM exige les deux formes ; une politique avec l'alias seul peut se déployer et être refusée à l'exécution)
- Une politique d'Access Point. Cette pile ne crée pas l'Access Point (elle reçoit un Access Point existant en paramètre) et ne gère pas sa politique ; attachez-la après le déploiement comme indiqué ci-dessous. Sans elle, le premier appel S3 est refusé à l'exécution
- Un nom pour le compartiment d'archive (la pile le crée : `DeletionPolicy: Retain`, Block Public Access, SSE-S3 par défaut, KMS facultatif, notifications EventBridge activées, TLS obligatoire)
- Seulement pour `selection=ATIME` et la capture des attributs : un VPC, des sous-réseaux, le secret contenant les identifiants ONTAP, le point de terminaison de gestion, l'UUID du volume et `OntapVerifySsl`. Le certificat du point de terminaison de gestion de FSx for ONTAP n'est pas signé par une autorité publique ; la valeur par défaut est donc `false` (pas de vérification). Dans ce mode, les identifiants ONTAP sont envoyés sur une connexion dont l'homologue n'est pas authentifié (le chemin reste dans le VPC). Avec `true`, la vérification échoue et l'exécution s'arrête à la sélection (observé sur un système réel). La fonction Lambda du VPC a besoin d'une route vers Secrets Manager et S3 (points de terminaison de VPC ou NAT)
- Seulement pour les fichiers de plus de 5 GiB : une image dans ECR. L'Access Point est d'origine Internet : les sous-réseaux de Fargate ont donc besoin d'une passerelle NAT ou d'une adresse IP publique
- Un abonnement de notification confirmé. Un abonnement e-mail SNS ne fait rien tant que le destinataire n'a pas cliqué sur le lien de confirmation ; sans cela, personne ne voit la demande d'approbation
### Étapes
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # replace every <PLACEHOLDER>
sam build && sam deploy
```
Après le déploiement, attachez la politique de l'Access Point. Le script génère, à partir des ARN de rôles des sorties de la pile, une politique qui accorde `s3:DeleteObject` au seul rôle de la fonction `delete` et `s3:PutObject` aux seuls rôles de restauration.
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # no PendingConfirmation left
```
Si l'Access Point a déjà une politique, cette commande la remplace ; fusionnez d'abord les instructions existantes.
Pour utiliser Fargate, construisez l'image depuis la racine du dépôt, poussez-la dans votre propre dépôt ECR et indiquez-la dans `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Lancez d'abord avec une entrée qui omet `dryRun` (donc `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
Pour supprimer, passez `"dryRun": false` sous forme de booléen JSON et indiquez le principal qui lance l'exécution dans `requestedBy`. La chaîne `"false"` est une erreur d'entrée et rien n'est supprimé.
## Structure du répertoire
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
La logique métier (sommes de contrôle, validation des entrées, registre, vérification après restauration) se trouve dans [`shared/archive_verify/`](../../../shared/archive_verify/) et est testée dans `shared/tests/`. Les lectures et écritures vers l'Access Point passent par `shared/s3ap_helper.py`.
## Tests locaux
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Pour confirmer qu'une décision de suppression défaillante est détectée, `test_does_not_delete_when_etag_changed` et `test_does_not_delete_when_size_differs_but_etag_equal` ont été exécutés une fois contre un bouchon dont la comparaison d'ETag était retirée ; les deux ont échoué avec `assert 'DELETED' == 'CHANGED'`. Le contrôle de l'enregistrement d'approbation et l'exclusion à 50 GiB ont été écrits en commençant par les tests et exécutés une fois contre le code précédent, avec les échecs `assert 'DELETED' != 'DELETED'` et `KeyError: 'skippedTooLarge'`, avant d'être implémentés.
## Success Metrics
### Outcome
Déplacer les fichiers rarement lus vers des classes de stockage S3 Glacier après vérification et approbation humaine, réduire l'occupation du volume, et pouvoir retrouver et restaurer les fichiers déplacés à partir du registre.
### Metrics
Les cibles sont fixées par l'exploitant. Aucun chiffre n'est donné ici.
| Catégorie | Indicateur | Définition |
|---|---|---|
| Business Outcome | Capacité libérée | Différence d'occupation du volume avant et après l'exécution (une fois les snapshots nettoyés). `bytesDeleted` (`-result.json`) est la taille totale des fichiers supprimés, pas l'espace libéré : tant que des snapshots subsistent, l'occupation du volume ne baisse pas, et pour des données compressées ou dédupliquées l'espace libéré est inférieur à la taille logique |
| Business Outcome | Économie mensuelle de stockage attendue | (Go déplacés hors du pool de capacité × écart de prix) − (stockage de la classe d'archive, surcoût par objet, frais de récupération). Prix : voir « Estimation des coûts » ci-dessous |
| Technical KPI | Taux de concordance de la vérification | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Fichiers non supprimés | Total de `CHANGED`, `MISMATCH` et `FAILED` |
| Technical KPI | Taux de concordance de la vérification après restauration | `RESTORE_VERIFIED` ÷ (`RESTORE_VERIFIED` + `RESTORE_MISMATCH`) |
| Quality KPI | Fichiers supprimés sans approbation | Doit être 0. Compter les `DELETED` dont `approvedBy` ou `approvedAt` est vide |
| Cost KPI | Par exécution : Lambda, Fargate, DynamoDB, requêtes S3, transitions d'état et stockage de la classe d'archive | Estimer avec la formule de « Estimation des coûts » à partir d'une exécution `dryRun=true` mesurée avec un `maxFiles` faible |
| Go / No-Go | Technique : dans une exécution sur un environnement réel, tous les fichiers copiés passent à `VERIFIED`, un `CHANGED` créé volontairement n'est pas supprimé, une auto-approbation par la personne qui a lancé l'exécution est refusée, les fichiers restaurés sont `RESTORE_VERIFIED`. Métier : l'économie attendue dépasse le coût d'exploitation (effort d'approbation, traitement des demandes de restauration) ; le point d'entrée et le délai de réponse visé pour les demandes de restauration (y compris le temps de restauration de la classe) sont décidés ; les utilisateurs ont été informés | Ne pas utiliser `dryRun=false` sur un volume de production tant que tout cela n'est pas rempli. Désignez d'abord qui décide de chaque point (propriétaire des données, approbateur, responsable de l'exploitation) |

La préparation d'un PoC et les vérifications avant la production se trouvent dans la [liste de vérification avant mise en production](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md) et dans l'[inventaire avant migration](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md) du FSx for ONTAP Adoption Playbook (tous deux en japonais). Pour le PoC de ce modèle, augmenter `maxFiles` à 20, 200 puis 2 000 en relevant la durée de l'exécution parente, les transitions d'état et les secondes Fargate donne des valeurs par fichier.
### Measurement Method
Historique d'exécution et journaux de Step Functions (`/aws/vendedlogs/states/<stack>-archive` et `-restore`, sans les données d'exécution), `manifests/<runId>-result.json`, `manifests/<runId>-approval.json`, métriques EMF de CloudWatch (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `FilesStuckDeleting`, `BytesVerified`, `BytesDeleted`, `RestoreVerified`, `RestoreMismatch`, `ApprovalPendingHours`), et registre.

Alarmes (toutes vers la rubrique de notification) :

| Alarme | Condition |
|---|---|
| `ArchiveExecutionsFailedAlarm`, `RestoreExecutionsFailedAlarm` | Une exécution ou plus en échec, expirée ou interrompue en 5 minutes |
| `ApprovalPendingAlarm` | Une demande d'approbation attend depuis plus de `ApprovalAlarmHours` (24 par défaut) |
| `FilesStuckDeletingAlarm` | Une exécution s'est terminée avec des éléments `DELETING` ou `APPROVED` |
| `FilesMismatchAlarm` | Une copie archivée ne concordait pas (`MISMATCH`) |
| `RestoreMismatchAlarm` | Un fichier restauré ne concordait pas avec le registre |
La rubrique de notification est chiffrée avec une clé KMS gérée par le client. La clé gérée par AWS (`alias/aws/sns`) a une politique de clé non modifiable, et EventBridge et les alarmes CloudWatch ne peuvent publier sur une rubrique chiffrée qu'avec une clé gérée par le client qui autorise les principaux de service pour `kms:GenerateDataKey*` et `kms:Decrypt` ([Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html), lu le 2026-11-26). La deuxième exécution a confirmé que les notifications d'échec d'EventBridge et les notifications d'alarme arrivent. [E-022]
## Performance Considerations
Le parallélisme par défaut s'appuie sur la seule mesure ci-dessous. Le reste relève de facteurs de conception et n'a pas été mesuré.
- Le fichier source est lu deux fois : une fois par l'Access Point pour calculer le hachage, et une fois côté serveur par `CopyObject`. Les requêtes de lecture sont facturées, et pour les données situées dans le pool de capacité, la lecture du pool de capacité l'est aussi
- Le parallélisme est `MapConcurrency` (2 par défaut, pour l'archivage et la restauration). Dans une mesure, une fonction Lambda a lu 5,3 Go (environ 4,94 GiB) par l'Access Point en 69,8 secondes, soit environ 76 Mo/s sur un seul flux, ce qui représente environ 60 % de la capacité de débit de 128 Mo/s de cet environnement. Chaque fichier est lu deux fois et le même volume sert vos utilisateurs : la valeur par défaut est donc 2. Utilisez 1 pour de gros fichiers ou un volume très sollicité, et avant de l'augmenter, surveillez `DataReadBytes` du système de fichiers et la latence des clients pendant une exécution. Les exécutions en parallèle n'ont pas été mesurées
- La valeur par défaut de 5 GiB pour `LargeFileThresholdBytes` découle de la limite de `CopyObject` en une seule requête. À la vitesse ci-dessus, les 15 minutes de Lambda couvriraient environ 63 GiB, mais ce n'est qu'un point de mesure
- Le listage charge tous les résultats de `ListObjectsV2` dans la mémoire d'une seule fonction Lambda. Au-delà de quelques millions d'objets, répartissez le travail avec `prefix`
- `selection=ATIME` parcourt les répertoires en profondeur d'abord. La limite d'analyse est de 200 000 entrées (`ONTAP_SCAN_LIMIT`) ; au-delà, le résultat partiel est renvoyé
- Le temps d'attente d'une restauration dépend de la classe et de `tier`. AWS indique pour S3 Glacier Deep Archive moins de 12 heures en Standard et moins de 48 heures en Bulk. La valeur par défaut de `RestoreMaxWaitHours` est 72. Pour les classes à longue attente, un `RestorePollMinutes` plus grand réduit le nombre de transitions d'interrogation
- Les tâches Fargate sont bornées par `FargateTimeoutSeconds` (7200 s par défaut). Chaque Task a un `TimeoutSeconds`, et une expiration est relancée
## Estimation des coûts
Aucune facture n'a été mesurée. Voici des valeurs d'utilisation mesurées et des conditions publiées par objet, à partir desquelles estimer.
Transitions d'état par fichier dans les deux exécutions (une exécution chacune) :

| Exécution | Transitions d'état par fichier | Source |
|---|---|---|
| Archivage à blanc | 17 (119 ÷ 7), 18 (72 ÷ 4) | Première et deuxième exécution |
| Archivage réel (suppressions comprises) | 18 (127 ÷ 7), 19,5 (78 ÷ 4) | Idem |
| Restauration (`Expedited` ; la deuxième avec vérification) | 18 (107 ÷ 6), 14 (56 ÷ 4) | Idem |
Les classes à longue attente ajoutent des transitions à chaque sondage.
Conditions de stockage par objet ([Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare), lu le 2026-11-26) :

| Classe | Durée de stockage minimale | Surcoût par objet, taille facturable minimale |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 jours | Taille d'objet facturable minimale de 128 KB |
| S3 Glacier Flexible Retrieval | 90 jours | 40 KB de métadonnées (32 KB au tarif de cette classe, 8 KB au tarif de S3 Standard) |
| S3 Glacier Deep Archive | 180 jours | 40 KB de métadonnées (même répartition) |
Formule : coût mensuel ≈ fichiers × transitions par fichier × prix par transition + durée de Lambda et de Fargate × prix + fichiers × (prix des requêtes `CopyObject`, `HeadObject`, `DeleteObject` et similaires) + stockage (données + fichiers × surcoût) × prix de la classe + frais de récupération lors d'une restauration. Reprenez les prix de [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) et de [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) pour votre région et la date voulue ; aucun n'est inscrit ici.
## Governance Note
> Ce modèle fournit des orientations d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Consultez des professionnels qualifiés au sein de votre organisation.
- Le résultat de la vérification et l'approbation sont des signaux d'aide à la décision finale d'une personne. Aucune IA n'est utilisée
- Ce modèle ne répond pas à des exigences de conservation ou d'immutabilité. Il n'utilise ni Object Lock ni équivalent : toute personne autorisée peut supprimer
- Classification des sorties : le registre et les manifestes contiennent des chemins de fichiers, des tailles, des hachages et des attributs. Un chemin peut contenir le nom d'une personne ou un identifiant de patient ou de dossier ; les sorties portent donc par défaut `data_classification` `RESTRICTED` (« Restricted — Limited access » dans `shared/data_classification.py`). Lorsque la classification propre aux données est plus stricte, indiquez-la dans le paramètre `DataClassification`. C'est vous qui décidez de la classification. Le contenu des fichiers va dans le compartiment d'archive ; traitez-le avec la même classification que les données d'origine
- Human Review : l'approbation est exigée pour chaque exécution. Il n'y a pas d'approbation automatique fondée sur un niveau de confiance. Par défaut, rien n'est supprimé lorsque la personne qui lance l'exécution et celle qui approuve sont le même principal
- IAM : seul le rôle de la fonction `delete` détient `s3:DeleteObject` sur l'Access Point, et seuls la machine d'états de restauration et le rôle de la tâche Fargate de restauration y détiennent `s3:PutObject`. La tâche Fargate d'archivage ne fait que copier et ne peut ni supprimer ni écraser les fichiers sources. Aucun principal ne peut supprimer des éléments du registre
- Audit : les approbations et les suppressions sont consignées dans le registre (`approvedBy`, `approvedAt`, `requestedBy`, `deletedBy`, `deletedAt`), dans `manifests/<runId>-approval.json` et dans l'historique et les journaux de Step Functions. CloudTrail n'enregistre les suppressions que si un journal de suivi a les événements de données S3 activés ; cela n'a pas été vérifié dans cette exécution
- Nombre de copies : sans deuxième copie, l'objet du compartiment d'archive est la seule copie après la suppression. La notification d'approbation le précise
## Contraintes et points non vérifiés
- Une copie directe d'un Access Point vers un compartiment d'une autre région a renvoyé `AccessDenied` (un Access Point, une fois). La deuxième copie ne vise que des compartiments de la même région
- Vérifié sur un volume de style UNIX. Une modification du contenu qui conserve la taille et le mtime n'est pas détectée par la vérification de l'ETag et de la taille (voir « Comportements observés lors de l'exécution de bout en bout »). On n'a pas vérifié si `chown` modifie l'ETag
- La capture des attributs passe par le listage des répertoires : lire tout le répertoire parent pour un seul fichier est lent pour les grands répertoires
- Le versionnement du compartiment d'archive n'est pas Object Lock. Les versions sont conservées, mais toute personne autorisée peut aussi les supprimer
- Les fichiers de plus de 50 GiB ne sont pas sélectionnés par défaut. S'ils sont inclus avec `allowOversize: true`, ils ne peuvent pas être restaurés vers l'Access Point ; téléchargez-les depuis le compartiment
- `requestedBy` et `approver` sont des valeurs déclarées. Vérifiez la séparation par principal avec IAM et CloudTrail
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
