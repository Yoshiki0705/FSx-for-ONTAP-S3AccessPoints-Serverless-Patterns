# Espacio de trabajo agéntico de Amazon Quick sobre FSx for ONTAP

🌐 **Language / Idioma**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Resumen

Un patrón que usa Amazon FSx for NetApp ONTAP **mediante S3 Access Points** como base de datos para **Amazon Quick Suite** (el espacio de trabajo de IA agéntico). Los datos que los equipos de negocio mantienen con operaciones de archivos de Windows se aprovechan en las capacidades de Quick (Index / Sight / Flows / Research).

A diferencia del UC29 (ingesta autoservicio en una base gestionada de Bedrock), el UC30 se centra en **un espacio de trabajo agéntico que unifica búsqueda no estructurada, BI y automatización de acciones**.

> Amazon Quick Suite, lanzado en octubre de 2025. Funciones/precios/regiones son «time-sensitive»; consulte [aws.amazon.com/quick](https://aws.amazon.com/quick/).

## Capacidades de Quick y S3 AP

| Capacidad Quick | Datos (S3 AP) | Implementación |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/` (no estructurado) | Fuente de datos S3 AP de solo lectura |
| Quick Sight (BI) | `analytics/<role>/` (csv) | Glue/Athena (Athena Query Lambda) |
| Quick Flows | `flows/<role>/` (json) | Action API (API Gateway + Lambda + Bedrock) |

## Dos escenarios de demostración

| Escenario | Resumen |
|---------|------|
| **A: Espacio manual** | Colocar datos vía Windows; conectar Quick Index, crear conjuntos de Quick Sight, ejecutar Quick Flows manualmente |
| **B: Automatización** | Automatizar preparación, consultas BI y acciones en serverless (Data Prep / Athena Query / Action API) |

## Roles × servicios

Los roles coinciden con los de Amazon Quick (sales, marketing, IT, operations, finance, legal + developers). Datos de ejemplo en [`sample-data/quick-workspace/`](sample-data/). Distribución de roles compartida con el UC29.

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## Seguridad

- Sin movimiento de datos (original en FSx for ONTAP; S3 AP de solo lectura)
- La Action API usa autenticación IAM (SigV4); sin endpoint público no autenticado
- Mínimo privilegio, cifrado (SSE-FSX/SSE-S3/TLS)
- Las conexiones de fuente de datos de Quick se configuran en la consola de Quick

## Governance Note

> Orientación de arquitectura técnica, no asesoramiento legal ni de cumplimiento. Las funciones/precios de Quick cambian; verifique fuentes oficiales.
