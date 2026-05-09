# Détection de changements BIM et vérification de conformité sécurité -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un pipeline de détection de changements BIM et de vérification automatique de conformité sécurité. Les violations sont détectées automatiquement lors des modifications.

**Message clé**: Détecter automatiquement les violations de sécurité lors des modifications BIM pour éliminer les risques dès la conception.

**Durée prévue**: 3–5 min

---

## Workflow

```
Upload BIM → Détection changements → Matching réglementaire → Détection violations → Rapport conformité
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : La revue manuelle de sécurité à chaque modification est inefficace

### Section 2 (0:45–1:30)
> Upload BIM : Placer les fichiers modifiés pour démarrer la vérification

### Section 3 (1:30–2:30)
> Détection et matching : Analyse diff automatique et comparaison aux normes de sécurité

### Section 4 (2:30–3:45)
> Violations détectées : Liste des non-conformités et niveaux de gravité

### Section 5 (3:45–5:00)
> Rapport conformité : Génération du rapport avec recommandations correctives

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (Change Detector) | Détection changements BIM |
| Lambda (Rule Matcher) | Moteur de matching réglementaire |
| Lambda (Report Generator) | Génération rapport conformité |
| Amazon Athena | Analyse agrégée de l'historique des violations |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
