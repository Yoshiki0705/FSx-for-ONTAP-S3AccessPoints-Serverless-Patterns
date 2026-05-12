# UC15 Script de démonstration (créneau de 30 minutes)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note : Cette traduction est produite par Amazon Bedrock Claude. Les contributions pour améliorer la qualité de la traduction sont les bienvenues.

## Prérequis

- Compte AWS, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `defense-satellite/template-deploy.yaml` déployé (`EnableSageMaker=false`)

## Chronologie

### 0:00 - 0:05 Introduction (5 minutes)

- Contexte du cas d'usage : augmentation des données d'imagerie satellite (Sentinel, Landsat, SAR commercial)
- Défis du NAS traditionnel : workflows basés sur la copie, coûteux en temps et en ressources
- Avantages de FSxN S3AP : zero-copy, synchronisation NTFS ACL, traitement serverless

### 0:05 - 0:10 Explication de l'architecture (5 minutes)

- Présentation du workflow Step Functions via diagramme Mermaid
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
# Téléchargement d'un GeoTIFF échantillon
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Exécution Step Functions
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
- Prochaines étapes : intégration multi-fournisseurs satellite, connexion Sentinel-1/2 Hub

## Questions fréquentes et réponses

**Q. Comment traiter les données SAR (HDF5 de Sentinel-1) ?**  
R. La Lambda Discovery classifie en `image_type=sar`, le Tiling peut implémenter un parseur HDF5 (rasterio ou h5py). L'Object Detection nécessite un modèle d'analyse SAR dédié (SageMaker).

**Q. Quelle est la justification du seuil de taille d'image (5MB) ?**  
R. Limite supérieure du paramètre Bytes de l'API Rekognition DetectLabels. Via S3, jusqu'à 15MB possible. Le prototype adopte la route Bytes.

**Q. Quelle est la précision de la détection de changement ?**  
R. L'implémentation actuelle est une comparaison simple basée sur la surface bbox. Pour une utilisation en production, la segmentation sémantique SageMaker est recommandée.

---

## À propos de la destination de sortie : sélectionnable via OutputDestination (Pattern B)

UC15 defense-satellite prend en charge le paramètre `OutputDestination` depuis la mise à jour du 2026-05-11
(voir `docs/output-destination-patterns.md`).

**Charge de travail cible** : Tuilage d'imagerie satellite / Détection d'objets / Geo enrichment

**2 modes** :

### STANDARD_S3 (par défaut, comportement traditionnel)
Crée un nouveau bucket S3 (`${AWS::StackName}-output-${AWS::AccountId}`) et
y écrit les résultats AI. Seul le manifest de la Lambda Discovery est écrit
dans le S3 Access Point (comme auparavant).

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (autres paramètres obligatoires)
```

### FSXN_S3AP (pattern "no data movement")
Réécrit les métadonnées de tuilage, les JSON de détection d'objets et les résultats de détection enrichis Geo
dans le **même volume FSx ONTAP** que les images satellite originales, via le FSxN S3 Access Point.
Les analystes peuvent référencer directement les résultats AI dans la structure de répertoires SMB/NFS existante.
Aucun bucket S3 standard n'est créé.

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (autres paramètres obligatoires)
```

**Points d'attention** :

- Spécification de `S3AccessPointName` fortement recommandée (autoriser IAM pour les formats Alias et ARN)
- Objets supérieurs à 5GB non supportés par FSxN S3AP (spécification AWS), multipart upload obligatoire
- La Lambda ChangeDetection utilise uniquement DynamoDB, donc non affectée par `OutputDestination`
- La Lambda AlertGeneration utilise uniquement SNS, donc non affectée par `OutputDestination`
- Pour les contraintes de spécification AWS, voir
  [la section "Contraintes de spécification AWS et solutions de contournement" du README du projet](../../README.md#aws-仕様上の制約と回避策)
  et [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Captures d'écran UI/UX vérifiées

Même approche que les démos Phase 7 UC15/16/17 et UC6/11/14, ciblant **les écrans UI/UX que les utilisateurs finaux
voient réellement dans leur travail quotidien**. Les vues techniques (graphe Step Functions, événements de stack CloudFormation,
etc.) sont consolidées dans `docs/verification-results-*.md`.

### Statut de vérification de ce cas d'usage

- ✅ **Vérification E2E** : SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **Capture UI/UX** : ✅ Terminée (Phase 8 Theme D, commit d7ebabd)

### Captures d'écran existantes (vérification Phase 7)

![Vue graphique Step Functions (SUCCEEDED)](../../docs/screenshots/masked/uc15-demo/step-functions-graph-succeeded.png)

![Bucket de sortie S3](../../docs/screenshots/masked/uc15-demo/s3-output-bucket.png)

![Sortie S3 Enriched](../../docs/screenshots/masked/uc15-demo/s3-enriched-output.png)

![Table d'historique de changements DynamoDB](../../docs/screenshots/masked/uc15-demo/dynamodb-change-history-table.png)

![Topics de notification SNS](../../docs/screenshots/masked/uc15-demo/sns-notification-topics.png)
### Écrans UI/UX cibles lors de la revérification (liste de capture recommandée)

- Bucket de sortie S3 (detections/, geo-enriched/, alerts/)
- Aperçu JSON des résultats de détection d'objets d'imagerie satellite Rekognition
- Résultats de détection avec coordonnées GeoEnrichment
- E-mail de notification d'alerte SNS
- Résultats AI sur le volume FSx ONTAP (mode FSXN_S3AP)

### Guide de capture

1. **Préparation** :
   - Vérifier les prérequis avec `bash scripts/verify_phase7_prerequisites.sh` (présence VPC/S3 AP communs)
   - Packager Lambda avec `UC=defense-satellite bash scripts/package_generic_uc.sh`
   - Déployer avec `bash scripts/deploy_generic_ucs.sh UC15`

2. **Placement des données échantillons** :
   - Télécharger un GeoTIFF échantillon via S3 AP Alias vers le préfixe `satellite-imagery/`
   - Démarrer Step Functions `fsxn-defense-satellite-demo-workflow` (entrée `{}`)

3. **Capture** (fermer CloudShell/terminal, masquer le nom d'utilisateur en haut à droite du navigateur) :
   - Vue d'ensemble du bucket de sortie S3 `fsxn-defense-satellite-demo-output-<account>`
   - Aperçu des JSON de sortie AI/ML (detections, geo-enriched)
   - Notification e-mail SNS (notification depuis AlertGeneration)

4. **Traitement de masquage** :
   - Masquage automatique avec `python3 scripts/mask_uc_demos.py defense-satellite-demo`
   - Masquage supplémentaire selon `docs/screenshots/MASK_GUIDE.md` (si nécessaire)

5. **Nettoyage** :
   - Supprimer avec `bash scripts/cleanup_generic_ucs.sh UC15`
   - Libération ENI Lambda VPC en 15-30 minutes (spécification AWS)
