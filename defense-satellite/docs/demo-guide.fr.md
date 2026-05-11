# UC15 Script de démonstration (créneau de 30 minutes)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Prérequis

- Compte AWS, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `defense-satellite/template-deploy.yaml` déployé (`EnableSageMaker=false`)

## Chronologie

### 0:00 - 0:05 Introduction (5 minutes)

- Contexte du cas d'usage : augmentation des données d'images satellites (Sentinel, Landsat, SAR commercial)
- Défis des NAS traditionnels : workflows basés sur la copie, coûteux en temps et en argent
- Avantages de FSxN S3AP : zero-copy, synchronisation NTFS ACL, traitement serverless

### 0:05 - 0:10 Explication de l'architecture (5 minutes)

- Présentation du workflow Step Functions avec diagramme Mermaid
- Logique de basculement Rekognition / SageMaker selon la taille de l'image
- Mécanisme de détection de changement par geohash

### 0:10 - 0:15 Déploiement en direct (5 minutes)

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-uc15-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:20 Traitement d'images échantillons (5 minutes)

```bash
# サンプル GeoTIFF アップロード
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- Afficher le graphe Step Functions dans la console AWS (Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration)
- Vérifier le temps d'exécution jusqu'à SUCCEEDED (généralement 2-3 minutes)

### 0:20 - 0:25 Vérification des résultats (5 minutes)

- Afficher la hiérarchie du bucket de sortie S3 :
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- Vérifier les métriques EMF dans CloudWatch Logs
- Historique de détection de changement dans la table DynamoDB `change-history`

### 0:25 - 0:30 Q&R + Conclusion (5 minutes)

- Conformité réglementaire du secteur public (DoD CC SRG, CSfC, FedRAMP)
- Chemin de migration GovCloud (même template `ap-northeast-1` → `us-gov-west-1`)
- Optimisation des coûts (SageMaker Endpoint activé uniquement en production)
- Prochaines étapes : intégration multi-fournisseurs satellites, connexion Sentinel-1/2 Hub

## Questions fréquentes et réponses

**Q. Comment traiter les données SAR (HDF5 de Sentinel-1) ?**  
R. La Lambda Discovery les classe en `image_type=sar`, le Tiling peut implémenter un parseur HDF5 (rasterio ou h5py). L'Object Detection nécessite un modèle d'analyse SAR dédié (SageMaker).

**Q. Quelle est la justification du seuil de taille d'image (5MB) ?**  
R. Limite supérieure du paramètre Bytes de l'API Rekognition DetectLabels. Via S3, jusqu'à 15MB possible. Le prototype adopte la route Bytes.

**Q. Quelle est la précision de la détection de changement ?**  
R. L'implémentation actuelle est une comparaison simple basée sur la surface bbox. Pour une utilisation en production, la segmentation sémantique SageMaker est recommandée.

---

## À propos de la destination de sortie : sélectionnable via OutputDestination (Pattern B)

UC15 defense-satellite prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-11
(voir `docs/output-destination-patterns.md`).

**Charge de travail concernée** : tuilage d'images satellites / détection d'objets / Geo enrichment

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats de l'IA. Seul le manifest de la Lambda Discovery est écrit
dans le S3 Access Point (comme auparavant).

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP (pattern "no data movement")
Les métadonnées de tuilage, les JSON de détection d'objets et les résultats de détection enrichis Geo sont réécrits
via le FSxN S3 Access Point dans le **même volume FSx ONTAP** que les images satellites originales.
Les analystes peuvent référencer directement les résultats de l'IA dans la structure de répertoires SMB/NFS existante.
Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**Points d'attention** :

- Spécification de `S3AccessPointName` fortement recommandée (autoriser IAM pour les formats Alias et ARN)
- Les objets de plus de 5GB ne sont pas possibles avec FSxN S3AP (spécification AWS), multipart upload obligatoire
- La Lambda ChangeDetection utilise uniquement DynamoDB et n'est donc pas affectée par `OutputDestination`
- La Lambda AlertGeneration utilise uniquement SNS et n'est donc pas affectée par `OutputDestination`
- Pour les contraintes de spécification AWS, voir
  [la section "Contraintes de spécification AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Suivant la même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant
**les écrans UI/UX que les utilisateurs finaux voient réellement dans leurs opérations quotidiennes**.
Les vues techniques (graphe Step Functions, événements de pile CloudFormation, etc.)
sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification pour ce cas d'utilisation

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX**: Not yet captured

### Captures d'écran existantes

![UC15 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc15-demo/uc15-stepfunctions-graph.png)

### Écrans UI/UX cibles pour re-vérification (liste de captures recommandées)

- Bucket S3 de sortie (detections/, geo-enriched/, alerts/)
- Résultats JSON de détection d'objets Rekognition sur images satellite
- Résultats de détection GeoEnrichment avec coordonnées
- Email de notification d'alerte SNS
- Artefacts AI sur volume FSx ONTAP (mode FSXN_S3AP)

### Guide de capture

1. **Préparation** : Exécuter `bash scripts/verify_phase7_prerequisites.sh` pour vérifier les prérequis
2. **Données d'exemple** : Télécharger les fichiers via S3 AP Alias, puis démarrer le workflow Step Functions
3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur)
4. **Masquage** : Exécuter `python3 scripts/mask_uc_demos.py <uc-dir>` pour le masquage OCR automatique
5. **Nettoyage** : Exécuter `bash scripts/cleanup_generic_ucs.sh <UC>` pour supprimer la pile
