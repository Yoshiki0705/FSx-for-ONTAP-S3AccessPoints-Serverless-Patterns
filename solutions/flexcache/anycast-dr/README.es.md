# FlexCache AnyCast / DR Pattern

🌐 **Language / Idioma**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Descripción general

Este patrón proporciona guías de diseño, demos de simulación y documentos de diseño operativo para implementar configuraciones ONTAP FlexCache AnyCast y DR (recuperación ante desastres) combinadas con FSx for ONTAP × S3 Access Points × servicios AWS Serverless.

## Problemas resueltos

| Problema | Solución FlexCache AnyCast / DR |
|----------|-------------------------------|
| Rendimiento de lectura para equipos geográficamente distribuidos | Servir datos calientes desde el FlexCache más cercano |
| Cloud bursting para EDA/Media/HPC | Origin on-premises + FlexCache Cloud reduce transferencias WAN |
| Continuidad de lectura durante DR | Lecturas basadas en caché continúan durante fallo de Origin |
| Reducción del volumen de transferencia WAN | Solo cachear datos calientes, transferencias delta |
| Complejidad de configuración de montaje del cliente | Punto de montaje único vía AnyCast IP |

## Métricas de éxito

| Métrica | Objetivo |
|---------|----------|
| Tiempo de detección de fallo | < 30 seg |
| Tiempo de propagación DNS | < 60 seg |
| Continuidad de lectura durante failover | > 99,9% |
| Tasa de acierto de caché (datos calientes) | > 80% |
| Reducción de transferencias WAN | > 60% |

---

## Nota de gobernanza

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento o regulatorio. Las organizaciones deben consultar a profesionales calificados.
