# GenAI RAG — Archivos empresariales

🌐 **Language / Idioma**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Descripción general

Un patrón que proporciona de forma segura documentos confidenciales en servidores de archivos empresariales (FSx for ONTAP) a pipelines de Amazon Bedrock / RAG a través de S3 Access Points **sin copiar a S3**. Logra RAG consciente de permisos manteniendo los permisos de archivos (ACL/NTFS).

## Problemas resueltos

| Problema | Solución |
|----------|----------|
| Proliferación de datos al copiar archivos sensibles a S3 | Lectura directa vía S3 AP, sin necesidad de copia |
| Pérdida de permisos de archivos | Recuperación de ACL vía ONTAP REST API, filtrado en respuesta RAG |
| Problemas de frescura de datos | FlexCache + S3 AP proporciona datos más recientes |
| Procesamiento de volumen completo de grandes servidores de archivos | EventBridge Scheduler + detección delta para eficiencia |
| Distancia entre procesamiento IA y datos | FlexCache coloca datos cerca del VPC de procesamiento IA |

## Concepto RAG consciente de permisos

1. **En indexación**: Recuperar información ACL/permisos para cada documento vía ONTAP REST API y almacenar como metadatos en el almacén vectorial
2. **En consulta**: Filtrar alcance de búsqueda a solo documentos accesibles por el usuario basado en su AD SID / membresía de grupo
3. **En respuesta**: Pasar solo documentos filtrados a Bedrock para generación de respuesta

## Métricas de éxito

| Métrica | Objetivo |
|---------|----------|
| Archivos procesados por ejecución | > 200 archivos |
| Tasa de éxito de extracción ACL | > 95% |
| Tiempo de generación de embeddings | < 5 min / 100 archivos |
| Precisión de filtrado consciente de permisos | > 99% |
| Tasa de Human Review | < 10% (chunks de baja confianza) |

---

## Despliegue

Despliegue con AWS SAM CLI (reemplace los marcadores por los de su entorno):

```bash
# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.
sam build

sam deploy \
  --stack-name fsxn-rag-enterprise-files \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **Nota**: `template.yaml` está diseñado para usarse con AWS SAM CLI (`sam build` + `sam deploy`).
> Para desplegar directamente con `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3).

> **Acerca de la extracción de ACL a nivel de archivo**: de forma predeterminada, la extracción de ACL se ejecuta en modo de simulación (sin ONTAP). Para extraer ACL reales, defina `OntapManagementIp` / `OntapSecretName`. Tenga en cuenta que esta plantilla no incluye `VpcConfig`, por lo que alcanzar un LIF de gestión de ONTAP privado requiere configuración de red adicional.

## Nota de gobernanza

> Este patrón proporciona orientación de arquitectura técnica. No constituye asesoramiento legal, de cumplimiento o regulatorio. Las organizaciones deben consultar a profesionales calificados.
