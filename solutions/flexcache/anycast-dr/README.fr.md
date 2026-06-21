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

## Note de gouvernance

> Ce pattern fournit des conseils d'architecture technique. Il ne constitue pas un avis juridique, de conformité ou réglementaire. Les organisations doivent consulter des professionnels qualifiés.
