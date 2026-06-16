# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/edge (neutre vis-à-vis du fournisseur)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Vue d'ensemble

Pattern serverless neutre vis-à-vis du fournisseur qui conserve FSx for NetApp ONTAP comme
**source de vérité unique (master)** et rend les **rendus approuvés pour diffusion** présents sur les
S3 Access Points (S3 AP) diffusables via un réseau CDN/edge.

Pour la comparaison de faisabilité technique entre réseaux de diffusion (CloudFront / Akamai / Fastly /
Cloudflare / Bunny.net / Google Media CDN, etc.), voir **[comparatif CDN](../docs/cdn-comparison.fr.md)**.

> Ceci est une implémentation de référence. Le choix du fournisseur, la gestion des droits, les
> restrictions géographiques et la conformité relèvent de la responsabilité du client.

> **TL;DR (30s)** : sans déplacer le master ONTAP/NAS, diffuser **uniquement les rendus approuvés** via
> CloudFront ou un CDN tiers. Commencer par `PUBLISH_PUSH` (M3), le moins risqué. N'adopter le pull direct
> SigV4 (ORIGIN_PULL) qu'après mesure avec la [checklist de vérification](../docs/cdn-origin-verification-checklist.fr.md).

## Résultat métier et adoption (Outcome / Adoption)

Évaluer par le **résultat métier**, pas par « c'est déployé ».

| Aspect | Outcome / Métrique / Méthode de mesure |
|---|---|
| Résultat métier | Diffusion edge sans dupliquer le master (seuls les rendus approuvés sont copiés) |
| Métrique | Objets master fuyant vers la couche de diffusion = 0 / nombre d'approbations `unrecorded` |
| Mesure | Agréger `provenance` et `skipped`/`published` du manifeste publish |

- **Périmètre d'expérimentation sûr** : `DemoMode=true` valide la logique sans FSx/CDN externe.
- **Business sponsor** : désigner un responsable de diffusion (équipe média/plateforme) qui approuve le Go/No-Go.
- **Checklist Go/No-Go** : aucun objet hors `ApprovedPrefix` ciblé ; traçabilité d'approbation enregistrée ;
  jetons spectateur via mécanisme natif du CDN ; pour ORIGIN_PULL, mesure SigV4×alias = PASS.
- Présenter le travail futur comme une **extension de preuves** (TBV → mesuré), non comme une incomplétude.

## Guide Partner/SI

- **Première question client** : « Voulez-vous connecter des actifs NAS/ONTAP existants à la diffusion edge
  sans copie ? La diffusion passe-t-elle par CloudFront ou un CDN sous contrat (ex. Akamai) ? »
- **Livrables PoC** : démo DemoMode → manifeste de diffusion des rendus approuvés → (option) résultat de
  vérification SigV4 sur matériel. Utiliser le [comparatif CDN](../docs/cdn-comparison.fr.md) en clientèle.

## Deux mécanismes d'intégration

- **ORIGIN_PULL** : aucune copie d'objet ; génère un manifeste de référence d'origine pour un CDN qui
  récupère le S3 AP directement via SigV4. CloudFront pris en charge nativement via OAC (référence). La
  signature d'origine SigV4 sur des CDN tiers est **à vérifier**.
- **PUBLISH_PUSH** : réplique les rendus approuvés vers le stockage objet compatible S3 du CDN. Évite la
  question de l'auth d'origine et reste neutre — l'étape initiale la moins risquée.

## Composants clés

| Composant | Rôle |
|---|---|
| `functions/publish/handler.py` | Reflète les rendus approuvés vers la couche de diffusion et réécrit un manifeste de diffusion dans le S3 AP |
| `functions/delivery_log_sync/handler.py` | Normalise les logs de diffusion CDN (masquage IP) et les réécrit dans le S3 AP pour corrélation avec les données de production |
| Step Functions | Publish → notification SNS |
| CloudFront (optionnel) | Diffusion de référence pour ORIGIN_PULL (OAC + SigV4) |

## Déploiement

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

## Sécurité / Gouvernance

- **permission-aware** : la diffusion est limitée aux objets sous `ApprovedPrefix`. Les données master
  contrôlées par ACL ne sont pas diffusées directement.
- **Authentification des spectateurs** : URL présignées S3 non prises en charge → jetons natifs du CDN.
- **PII** : masquage de l'IP client lors de la réécriture des logs (`RedactClientIp=true`).
- **Moindre privilège** : les Lambdas de diffusion s'exécutent **hors VPC** pour l'accès Internet-origin au S3 AP.

> **Governance Note** : la diffusion n'applique pas les permissions de fichiers ONTAP. La frontière de
> diffusion est garantie par la règle « rendus approuvés uniquement », la traçabilité des approbations et
> les contrôles d'accès de la cible.

### Responsabilités (RACI / secteur public)

| Rôle | Responsabilité |
|---|---|
| Data Owner | Responsabilité finale de la classification, la résidence et l'éligibilité à la publication |
| Approver | Approuve le placement sous `ApprovedPrefix` ; renseigne la traçabilité (approved-by / approval-id) |
| Audit Reviewer | Examine périodiquement `provenance` dans les manifestes et les logs de diffusion |
| Ops Owner | Reçoit les alarmes, gère les incidents, exécute le rollback |

- Les décisions IA/automatiques sont des **signaux assistifs** ; la publication est décidée par des humains
  (Data Owner / Approver).
- Utiliser des données **synthétiques/échantillons non sensibles** pour la vérification (jamais de données
  personnelles de production).
- La validation technique **ne remplace pas** l'évaluation juridique/conformité/confidentialité.

## Exploitation / Runbook

- **Alarmes** : avec `EnableCloudWatchAlarms=true`, les erreurs Lambda (publish/log-sync) et les échecs Step
  Functions notifient via SNS (`NotificationEmail`).
- **Triage** : erreurs publish → consulter `/aws/lambda/<stack>-publish` ; isoler l'autz S3 AP (IAM + AP
  policy + identité ONTAP) de l'auth du stockage externe (Secrets Manager). Échecs de push externe → vérifier
  `ExternalStoreSecretName`, endpoint, bucket. Soupçon de violation de frontière →
  [playbook de réponse aux incidents](../docs/incident-response-playbook.md).
- **Rollback** : la diffusion ne publie que des rendus approuvés ; en cas de publication erronée, retirer
  l'objet de la cible (store/distribution CDN), le retirer de `ApprovedPrefix`, puis re-publier.
- **Auth du stockage externe** : pour PUBLISH_PUSH vers Akamai/R2/Fastly, les identifiants AWS par défaut ne
  s'appliquent pas — définir `ExternalStoreSecretName` (Secrets Manager, `{"access_key_id","secret_access_key"}`).

## Documents associés

- [Comparatif d'intégration CDN/edge](../docs/cdn-comparison.fr.md)
- [Checklist de vérification SigV4 ORIGIN_PULL](../docs/cdn-origin-verification-checklist.fr.md) (procédure sur matériel)
- [Comparatif d'architectures alternatives](../docs/comparison-alternatives.md)
- [Playbook de réponse aux incidents](../docs/incident-response-playbook.md)
