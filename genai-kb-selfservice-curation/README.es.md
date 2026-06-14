# Curación autoservicio de la base de conocimiento

🌐 **Language / Idioma**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Resumen

Un patrón que permite a los usuarios de negocio mantener una fuente de datos de Amazon Bedrock Knowledge Base **únicamente con arrastrar y soltar en el familiar Explorador de Windows**.

Se crea un **volumen/carpeta dedicado a la IA** en FSx for ONTAP, compartido por SMB a cada rol/departamento. Los mismos datos se conectan a una Amazon Bedrock Knowledge Base **mediante S3 Access Points (ruta de lectura)**, y los cambios de archivos activan la **ingesta automática**.

Así se pasa de una operación de «ETL/copia/ingesta manual por TI en cada solicitud» a un **modelo democratizado en el que el negocio mantiene su propio conocimiento**.

## Antes / Después

> **Nota**: relato operativo generalizado, con nombres de cliente, personas y equipos enmascarados.

- **Antes**: solicitud del negocio → TI copia manualmente desde un Windows Server en EC2 → carga a S3 → ingesta manual en Bedrock KB. Cuello de botella por solicitud, doble gestión de datos.
- **Después**: «Coloca los datos para la IA en esta carpeta de Windows y mantenlos tú mismo.» El usuario arrastra y suelta como siempre; la KB se sincroniza automáticamente vía S3 AP.

## Dos escenarios de demostración

La misma base admite dos etapas según la madurez operativa (consulte la [guía de demo](docs/demo-guide.md)):

| Escenario | Resumen | Disparador de ingesta |
|---------|------|----------------------|
| **A: Práctica manual** | Mantener los datos de IA con operaciones de archivos de Windows (añadir/actualizar/eliminar); ingesta activada manualmente (consola «Sincronizar»/CLI) | Manual |
| **B: Automatización** | Automatizar la sincronización manual de A con Lambda + Step Functions + EventBridge (detectar→ingerir→esperar→notificar) | Automático |

> La acción del usuario de negocio (arrastrar y soltar) es idéntica en ambos. Solo cambian los pasos posteriores a la ingesta: realizados por una persona o por serverless.

## Problemas resueltos

| Problema | Solución |
|------|--------|
| Actualizaciones a la espera del trabajo manual de TI | El negocio mantiene vía Windows; ingesta automática |
| Doble gestión por copias a S3 | Fuente de datos directa desde el original FSx ONTAP vía S3 AP |
| Ingestas/actualizaciones omitidas | Detección de cambios e ingesta automática |
| Se requieren conocimientos de ETL/S3/Bedrock | Solo arrastrar y soltar en Windows |
| Propiedad de los datos poco clara | Estructura de carpetas por rol/departamento |

## KB gestionada vs RAG personalizado

Este UC adopta **Bedrock Knowledge Bases gestionado (Pattern C)** para minimizar la carga operativa. Si necesita filtrado de permisos a nivel de archivo en la búsqueda, elija RAG personalizado ([FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/), Pattern A).

> **Requisito de despliegue**: cree la Knowledge Base y la fuente de datos con [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) o la consola de Bedrock y pase sus ID como parámetros de la plantilla.

## Seguridad

- Sin movimiento de datos (el original permanece en FSx ONTAP; S3 AP solo lectura)
- Escritura solo por SMB/NFS; la ruta de ingesta de IA (S3 AP) es de lectura
- ACL NTFS por carpeta para separar permisos de escritura por departamento
- El límite de la fuente de datos S3 AP es a nivel de volumen/prefijo (el control de visibilidad por usuario queda fuera de alcance)

## Governance Note

> Este patrón ofrece orientación de arquitectura técnica, no asesoramiento legal ni de cumplimiento. Consulte a profesionales cualificados.
