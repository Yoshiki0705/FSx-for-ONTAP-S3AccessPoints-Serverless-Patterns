# UC16 Script de démonstration (créneau de 30 minutes)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Prérequis

- Compte AWS, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Déployer `government-archives/template-deploy.yaml` (avec `OpenSearchMode=none` pour réduire les coûts)

## Chronologie

### 0:00 - 0:05 Introduction (5 minutes)

- Cas d'usage : numérisation de la gestion des archives publiques pour les collectivités locales et l'administration
- Charge liée aux délais légaux FOIA / demandes d'accès à l'information (20 jours ouvrables)
- Défi : la détection et la caviardage des PII sont manuels et prennent plusieurs heures

### 0:05 - 0:10 Architecture (5 minutes)

- Combinaison de Textract + Comprehend + Bedrock
- 3 modes OpenSearch (none / serverless / managed)
- Gestion automatique des périodes de conservation NARA GRS

### 0:10 - 0:15 Déploiement (5 minutes)

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 Exécution du traitement (7 minutes)

```bash
# サンプル PDF（機密情報含む）アップロード
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

Vérifier les résultats :
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt` (texte brut)
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json` (résultats de classification)
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json` (détection PII)
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt` (version caviardée)
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json` (sidecar)

### 0:22 - 0:27 Suivi des délais FOIA (5 minutes)

```bash
# FOIA 請求登録
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 手動実行
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

Vérifier l'e-mail de notification SNS.

### 0:27 - 0:30 Conclusion (3 minutes)

- Chemin d'activation d'OpenSearch (recherche complète avec `serverless`)
- Migration vers GovCloud (exigences FedRAMP High)
- Prochaines étapes : génération de réponses FOIA interactives avec les agents Bedrock

## Questions fréquentes et réponses

**Q. Est-il possible de se conformer à la loi japonaise sur l'accès à l'information (30 jours) ?**  
R. Oui, en modifiant `REMINDER_DAYS_BEFORE` et le codage en dur de 20 jours ouvrables (jours fériés fédéraux US → jours fériés japonais).

**Q. Où sont stockées les PII du document original ?**  
R. Elles ne sont stockées nulle part. `pii-entities/*.json` contient uniquement le hash SHA-256, `redaction-metadata/*.json` contient uniquement hash + offset. La restauration nécessite une réexécution à partir du document original.

**Q. Comment réduire les coûts d'OpenSearch Serverless ?**  
R. Minimum 2 OCU = environ 350 $/mois. Arrêt recommandé hors production.
R. Ignorer avec `OpenSearchMode=none`, ou réduire à ~25 $/mois avec `OpenSearchMode=managed` + `t3.small.search × 1`.

---

## À propos de la destination de sortie : sélectionnable via OutputDestination (Pattern B)

UC16 government-archives prend en charge le paramètre `OutputDestination` depuis la mise à jour du 11 mai 2026
(voir `docs/output-destination-patterns.md`).

**Charges de travail concernées** : texte OCR / classification de documents / détection PII / caviardage / documents en amont d'OpenSearch

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats de l'IA. Seul le manifest de la Lambda Discovery est écrit
dans le S3 Access Point (comme auparavant).

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP (pattern "no data movement")
Écrit le texte OCR, les résultats de classification, les résultats de détection PII, les documents caviardés et les métadonnées de caviardage
via le FSxN S3 Access Point dans le **même volume FSx ONTAP** que les documents originaux.
Les responsables des archives publiques peuvent consulter directement les résultats de l'IA dans la structure de répertoires SMB/NFS existante.
Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**Relecture dans la structure en chaîne** :

UC16 a une structure en chaîne où les Lambda en aval relisent les résultats des étapes précédentes (OCR → Classification →
EntityExtraction → Redaction → IndexGeneration), donc `shared/output_writer.py` relit
via `get_bytes/get_text/get_json` depuis la même destination que celle où les données ont été écrites.
Cela permet la relecture depuis le FSxN S3 Access Point lorsque `OutputDestination=FSXN_S3AP`,
et l'ensemble de la chaîne fonctionne avec une destination cohérente.

**Points d'attention** :

- Il est fortement recommandé de spécifier `S3AccessPointName` (autoriser IAM pour les formats Alias et ARN)
- Les objets de plus de 5 Go ne sont pas pris en charge par FSxN S3AP (spécification AWS), upload multipart obligatoire
- La Lambda ComplianceCheck utilise uniquement DynamoDB et n'est donc pas affectée par `OutputDestination`
- La Lambda FoiaDeadlineReminder utilise uniquement DynamoDB + SNS et n'est donc pas affectée
- L'index OpenSearch est géré séparément par le paramètre `OpenSearchMode` (indépendant de `OutputDestination`)
- Pour les contraintes liées aux spécifications AWS, consultez
  [la section "Contraintes des spécifications AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Suivant la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant
**les écrans UI/UX que les utilisateurs finaux voient réellement dans leurs opérations quotidiennes**.
Les vues techniques (graphe Step Functions, événements de pile CloudFormation, etc.)
sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'utilisation

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **Capture UI/UX** : ✅ Terminé (Phase 8 Theme D, commit d7ebabd)

### Captures d'écran existantes

![Vue graphique Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc16-demo/step-functions-graph-succeeded.png)

![Bucket S3 de sortie](../../docs/screenshots/masked/uc16-demo/s3-output-bucket.png)

![Table DynamoDB retention](../../docs/screenshots/masked/uc16-demo/dynamodb-retention-table.png)
### Écrans UI/UX cibles pour re-vérification (liste de captures recommandées)

- Bucket S3 de sortie (ocr-results/, classified/, redacted/, compliance/)
- Résultats JSON Textract OCR (Cross-Region us-east-1)
- Aperçu du document expurgé
- Table DynamoDB retention (gestion des délais FOIA)
- Email de rappel FOIA via SNS
- Index OpenSearch (quand OpenSearchMode activé)
- Artefacts AI sur volume FSx ONTAP (mode FSXN_S3AP)

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
