# FlexCache AnyCast / DR Pattern

🌐 **Language / Langue**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Aperçu

Ce pattern fournit des guides de conception, des démos de simulation et des documents de conception opérationnelle pour implémenter les configurations ONTAP FlexCache AnyCast et DR (reprise après sinistre) combinées avec FSx for ONTAP × S3 Access Points × services AWS Serverless.

## Problèmes résolus

| Problème | Solution FlexCache AnyCast / DR |
|----------|-------------------------------|
| Performance de lecture pour équipes géographiquement distribuées | Servir les données chaudes depuis le FlexCache le plus proche |
| Cloud bursting pour EDA/Média/HPC | Origin on-premises + FlexCache Cloud réduit les transferts WAN |
| Continuité de lecture pendant le DR | Les lectures basées sur le cache continuent même pendant une panne Origin |
| Réduction du volume de transfert WAN | Cache uniquement les données chaudes, transferts delta |
| Complexité de configuration de montage client | Point de montage unique via AnyCast IP |

## Métriques de succès

| Métrique | Objectif |
|----------|----------|
| Temps de détection de panne | < 30 sec |
| Temps de propagation DNS | < 60 sec |
| Continuité de lecture pendant le basculement | > 99,9% |
| Taux de hit cache (données chaudes) | > 80% |
| Réduction des transferts WAN | > 60% |

---

## Déploiement

Déployez avec AWS SAM CLI (remplacez les paramètres d'exemple selon votre environnement) :

```bash
# パラメータファイルを編集
cp params/staging.json params/flexcache-anycast-demo.json
# 必要なパラメータを設定

# デプロイ
# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.
sam build

sam deploy \
  --stack-name flexcache-anycast-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    SimulationMode=true \
    CacheEndpoints="cache-a.example.com,cache-b.example.com" \
    HealthCheckIntervalMinutes=5
```

> **Remarque** : `template.yaml` est conçu pour être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).
> Pour un déploiement direct avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3).

## Note de gouvernance

> Ce pattern fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Les organisations doivent consulter des professionnels qualifiés.
