# Comparatif d'intégration CDN / edge — Diffusion depuis FSx ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. Portée

Référence de faisabilité technique pour diffuser des données présentes sur les FSx for ONTAP
S3 Access Points (S3 AP) via un réseau CDN/edge. Ce document **ne** classe **pas** les fournisseurs, ne
compare ni prix ni performances et ne formule aucune affirmation marketing. Il traite uniquement de **ce
qui est techniquement réalisable, ce qui ne l'est pas et ce qui doit être vérifié** au regard des
contraintes du S3 AP FSx ONTAP. Le choix du fournisseur dépend d'éléments hors périmètre (contrats, SLA,
exploitation, exigences régionales) et relève du client.

## 1. Contraintes du S3 AP qui déterminent la conception de la diffusion

| Contrainte | Détail | Impact sur la diffusion |
|------------|--------|-------------------------|
| Block Public Access imposé (non désactivable) | Activé par défaut, immuable | Pas d'origine publique non authentifiée ; auth d'origine requise |
| Auth d'origine en SigV4 (IAM) | Requêtes évaluées par IAM / politique AP | Le CDN doit signer les requêtes d'origine en AWS SigV4 |
| Autorisation à deux niveaux (AWS + ONTAP) | IAM puis identité de fichier ONTAP (UNIX UID / Windows AD) | Diffusion limitée à ce que l'identité ONTAP peut lire |
| URL présignées non prises en charge | Officiellement non supportées | L'auth par jeton spectateur ne peut pas utiliser les URL présignées S3 ; utiliser les jetons natifs du CDN |
| NetworkOrigin (Internet/VPC, immuable) | Le CDN accède depuis un réseau managé/externe | L'intégration CDN nécessite une **origine Internet** |
| PutObject max 5 Go | Limite d'un PUT unique | Les réécritures volumineuses nécessitent le multipart |

## 2. Mécanismes d'intégration (neutres vis-à-vis du fournisseur)

- **M1 — Origin-pull SigV4 natif** : le CDN récupère le S3 AP directement en signant en SigV4. Réalisable
  lorsque le CDN embarque la signature d'origine SigV4. **À vérifier** : l'hôte `accesspoint alias` du
  S3 AP diffère d'un bucket standard ; le comportement SigV4 doit être validé sur matériel.
- **M2 — Signature SigV4 par edge compute** : implémenter SigV4 dans le runtime edge du CDN
  (Workers/Compute/EdgeWorkers). Réalisable en l'absence de signature d'origine native ; vous gérez la
  signature et les clés.
- **M3 — Push vers un stockage objet compatible S3 du CDN** : conserver FSx comme master, répliquer
  uniquement les rendus approuvés vers le stockage objet du CDN. Évite la question de l'auth d'origine ;
  neutre vis-à-vis du fournisseur ; étape initiale la moins risquée.
- **M4 — Proxy de signature SigV4 auto-géré** : placer un intermédiaire de signature (Lambda Function URL /
  ALB) comme origine. Fonctionne avec presque tous les CDN ; le proxy devient un point de
  disponibilité/scalabilité.

> Contrainte universelle : l'auth par jeton spectateur ne peut pas utiliser les URL présignées S3 — utiliser
> les jetons natifs du CDN. La diffusion publique contourne les ACL NFS/SMB, donc ne diffuser que les rendus
> approuvés (voir section 4).

## 3. Prise en charge des mécanismes par réseau de diffusion (factuel)

○ = fonctionnalité native documentée / △ = conditionnel ou auto-implémenté / − = pas de telle fonctionnalité / TBV = vérification propre au S3 AP nécessaire.

| Réseau | M1 pull SigV4 natif | M2 signature edge | M3 stockage S3-compatible propre | Jeton spectateur | TBV propre au S3 AP |
|--------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | (vers S3 standard) | URL/Cookie signés CloudFront | **Avéré** (le tutoriel officiel AWS montre S3 AP + OAC) |
| Akamai | ○ Cloud Access Manager (signature AWS) | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | Signature sur l'hôte AP alias TBV |
| Fastly | ○ SigV4 vers origine privée S3-compatible | △ Compute | ○ Fastly Object Storage | URL signée Fastly | SigV4 sur AP alias TBV |
| Cloudflare | − (pas de SigV4 natif au proxy) | ○ Signature SigV4 via Workers | ○ R2 (S3-compatible) | URL signée Cloudflare | Signature Workers + AP alias TBV |
| Bunny.net | △ Origin-pull S3 (type d'origine AWS S3) | − | ○ Bunny Storage (API S3-compatible, beta) | Auth par jeton Pull Zone | Signature sur AP alias TBV |
| Google Cloud CDN / Media CDN | ○ Auth SigV4 d'origine S3-compatible privée | △ Routage Media CDN | (GCS / tout S3-compatible) | URL/Cookie signés Media CDN | Egress cross-cloud + AP alias TBV |

### Mentionnés mais non classés dans le tableau
- **Azure Front Door / Azure CDN** : le même mécanisme (M1/M4) peut s'appliquer ; hors périmètre principal ; TBV.
- **Gcore** : stockage objet S3-compatible + stockage-comme-origine (M3) ; hors périmètre principal.
- **Edgio (ex-Limelight / Edgecast)** : **service CDN arrêté le 2025-01-15** ; la plupart des actifs acquis
  par Akamai. **Pas une option active** — exclu.

> Les sources sont les docs publiques des fournisseurs (CloudFront OAC, Akamai Cloud Access Manager,
> origines privées S3-compatibles Fastly, Cloudflare Workers/R2, Bunny Storage, Google Media CDN). Toutes
> décrivent des **buckets S3-compatibles standard** ; le comportement sur l'accesspoint alias du S3 AP
> FSx ONTAP est TBV.

## 4. Exigences de sécurité fixes (indépendantes du mécanisme)

1. La diffusion publique contourne les ACL NFS/SMB — ne diffuser **que les rendus approuvés** ; ne jamais
   router des données master contrôlées par ACL directement vers la couche de diffusion.
2. Séparer le master (contrôlé par ACL, sensible) des artefacts de diffusion (public/semi-public). M3 rend
   cette séparation naturelle.
3. Auth spectateur via les jetons natifs du CDN (pas d'URL présignées S3).
4. Identifiants d'origine à moindre privilège ; éviter les clés longue durée à l'edge ; préférer des
   identifiants éphémères.
5. Logs de diffusion : traiter les PII spectateur lors de la réécriture des logs vers FSx.
6. **Traçabilité d'approbation** : enregistrer quel objet a été approuvé pour la diffusion publique, par qui
   et quand. Les objets sans approbateur enregistré sont **rendus visibles** (`unrecorded`), non bloqués
   silencieusement.
7. **Résidence des données / restriction géographique** : les CDN diffusent mondialement. Exclure les données
   qui ne peuvent pas quitter une région, ou imposer le geo-blocking ; inclure des contrôles de résidence
   dans le processus d'approbation.

### 4.1 Classification des preuves
- **Preuve publique** : capacités des fournisseurs de la section 3 — basées sur des docs publiques,
  **dépendantes du moment**, à revérifier avant adoption.
- **À vérifier (ce projet)** : comportement de la signature d'origine SigV4 sur l'accesspoint alias du
  S3 AP FSx ONTAP.

## 5. Synthèse de faisabilité

| Question | Réponse |
|----------|---------|
| Exposer le S3 AP comme origine CDN non authentifiée ? | **Non** (BPA imposé) |
| Diffuser directement depuis le S3 AP via un CDN ? | **Oui, sous conditions** — M1/M2 avec SigV4 ; la signature AP-alias est TBV |
| Diffuser via un CDN sans SigV4 ? | **Oui** — M3 (push) ou M4 (proxy de signature) |
| Utiliser des URL présignées S3 pour les spectateurs ? | **Non** — utiliser les jetons natifs du CDN |
| Imposer les ACL ONTAP au moment de la diffusion ? | **Non** — assuré via « rendus approuvés uniquement » + traçabilité |
| Première étape au risque de vérification le plus faible ? | **M3 (push)** — évite l'auth d'origine, neutre, compatible DemoMode |

> **Governance Caveat** : informations techniques de référence. Les fonctionnalités des fournisseurs
> évoluent ; revérifier avec les docs officielles les plus récentes avant adoption. La signature d'origine
> SigV4 sur l'accesspoint alias du S3 AP est un point de vérification du projet (TBV). Le choix du
> fournisseur relève du client.
