# Audit des permissions du serveur de fichiers — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

Cette démo présente un workflow d'audit automatisé détectant les permissions excessives sur les serveurs de fichiers. Il analyse les ACL NTFS et génère des rapports de conformité.

**Message clé**: Automatiser les audits de permissions prenant des semaines, visualisant instantanément les risques.

**Durée prévue**: 3–5 min

---

## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problématique : L'audit manuel de milliers de dossiers est irréaliste

### Section 2 (0:45–1:30)
> Déclenchement : Spécifier le volume cible et lancer l'audit

### Section 3 (1:30–2:30)
> Analyse ACL : Collecter les ACL et détecter les violations

### Section 4 (2:30–3:45)
> Revue des résultats : Saisir violations et niveaux de risque

### Section 5 (3:45–5:00)
> Rapport de conformité : Générer rapport avec actions prioritaires

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orchestration du workflow |
| Lambda (ACL Collector) | Collecte métadonnées ACL NTFS |
| Lambda (Policy Checker) | Correspondance règles de violation |
| Lambda (Report Generator) | Génération rapport via Bedrock |
| Amazon Athena | Analyse SQL des violations |

---

*Ce document sert de guide de production pour les vidéos de démonstration technique.*
