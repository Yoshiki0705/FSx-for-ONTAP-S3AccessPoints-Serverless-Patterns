# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/edge (neutral respecto al proveedor)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Resumen

Patrón serverless neutral respecto al proveedor que mantiene FSx for NetApp ONTAP como
**fuente única de verdad (master)** y hace que las **renditions aprobadas para distribución** en los
S3 Access Points (S3 AP) sean distribuibles a través de una red CDN/edge.

Para la comparación de viabilidad técnica entre redes de distribución (CloudFront / Akamai / Fastly /
Cloudflare / Bunny.net / Google Media CDN, etc.), consulte **[comparativa CDN](../docs/cdn-comparison.es.md)**.

> Esta es una implementación de referencia. La selección del proveedor, la gestión de derechos, las
> restricciones geográficas y el cumplimiento son responsabilidad del cliente.

> **TL;DR (30s)**: sin mover el master ONTAP/NAS, distribuir **solo renditions aprobadas** vía CloudFront o
> un CDN de terceros. Empezar por `PUBLISH_PUSH` (M3), el de menor riesgo. Adoptar el pull directo SigV4
> (ORIGIN_PULL) solo tras medirlo con la [lista de verificación](../docs/cdn-origin-verification-checklist.es.md).

## Resultado de negocio y adopción (Outcome / Adoption)

Evaluar por **resultado de negocio**, no por "se desplegó".

| Aspecto | Outcome / Métrica / Método de medición |
|---|---|
| Resultado de negocio | Distribución edge sin duplicar el master (solo se copian renditions aprobadas) |
| Métrica | Objetos master que se filtran a la capa de distribución = 0 / nº de aprobaciones `unrecorded` |
| Medición | Agregar `provenance` y `skipped`/`published` del manifiesto publish |

- **Límite de experimentación seguro**: `DemoMode=true` valida la lógica sin FSx/CDN externo.
- **Business sponsor**: asignar un responsable de distribución (equipo de medios/plataforma) que apruebe el Go/No-Go.
- **Lista Go/No-Go**: ningún objeto fuera de `ApprovedPrefix` es objetivo; trazabilidad de aprobación
  registrada; tokens de espectador vía mecanismo nativo del CDN; para ORIGIN_PULL, la medición SigV4×alias es PASS.
- Presentar el trabajo futuro como **expansión de evidencia** (TBV → medido), no como incompletitud.

## Guía Partner/SI

- **Primera pregunta al cliente**: "¿Quiere conectar activos NAS/ONTAP existentes a la distribución edge sin
  copiar? ¿La distribución va por CloudFront o un CDN contratado (p. ej. Akamai)?"
- **Entregables de PoC**: demo DemoMode → manifiesto de distribución de renditions aprobadas → (opcional)
  resultado de verificación SigV4 en hardware. Use la [comparativa CDN](../docs/cdn-comparison.es.md) en conversaciones con clientes.

## Dos mecanismos de integración

- **ORIGIN_PULL**: sin copia de objetos; genera un manifiesto de referencia de origen para un CDN que obtiene
  el S3 AP directamente vía SigV4. CloudFront se admite de forma nativa vía OAC (referencia). La firma de
  origen SigV4 en CDN de terceros está **por verificar**.
- **PUBLISH_PUSH**: replica las renditions aprobadas al almacén compatible con S3 del CDN. Evita la cuestión
  de la auth de origen y es neutral — el primer paso de menor riesgo.

## Componentes clave

| Componente | Función |
|---|---|
| `functions/publish/handler.py` | Refleja las renditions aprobadas a la capa de distribución y reescribe un manifiesto de distribución en el S3 AP |
| `functions/delivery_log_sync/handler.py` | Normaliza los logs de distribución del CDN (enmascarado de IP) y los reescribe en el S3 AP para correlacionarlos con los datos de producción |
| Step Functions | Publish → notificación SNS |
| CloudFront (opcional) | Distribución de referencia para ORIGIN_PULL (OAC + SigV4) |

## Despliegue

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

## Seguridad / Gobernanza

- **permission-aware**: la distribución se limita a objetos bajo `ApprovedPrefix`. Los datos master
  controlados por ACL no se distribuyen directamente.
- **Autenticación de espectadores**: URL prefirmadas de S3 no admitidas → tokens nativos del CDN.
- **PII**: la IP del cliente se enmascara al reescribir los logs (`RedactClientIp=true`).
- **Mínimo privilegio**: las Lambdas de distribución se ejecutan **fuera de la VPC** para el acceso Internet-origin.

> **Governance Note**: la distribución no aplica los permisos de archivos de ONTAP. El límite de distribución
> se garantiza mediante la regla "solo renditions aprobadas", la trazabilidad de aprobaciones y los controles
> de acceso del destino.

### Responsabilidades (RACI / sector público)

| Rol | Responsabilidad |
|---|---|
| Data Owner | Responsabilidad final de la clasificación, residencia y elegibilidad de publicación |
| Approver | Aprueba la colocación bajo `ApprovedPrefix`; establece la trazabilidad (approved-by / approval-id) |
| Audit Reviewer | Revisa periódicamente `provenance` en los manifiestos y los logs de distribución |
| Ops Owner | Recibe alarmas, gestiona incidentes, ejecuta rollback |

- Las decisiones IA/automáticas son **señales asistivas**; la publicación la deciden humanos
  (Data Owner / Approver).
- Usar datos **sintéticos/de muestra no sensibles** para la verificación (nunca datos personales de producción).
- La validación técnica **no reemplaza** la evaluación legal/cumplimiento/privacidad.

## Operación / Runbook

- **Alarmas**: con `EnableCloudWatchAlarms=true`, los errores de Lambda (publish/log-sync) y los fallos de
  Step Functions notifican vía SNS (`NotificationEmail`).
- **Triaje**: errores de publish → revisar `/aws/lambda/<stack>-publish`; aislar la autz del S3 AP (IAM +
  AP policy + identidad ONTAP) de la auth del almacén externo (Secrets Manager). Fallos de push externo →
  revisar `ExternalStoreSecretName`, endpoint, bucket. Sospecha de violación de límite →
  [playbook de respuesta a incidentes](../docs/incident-response-playbook.md).
- **Rollback**: la distribución solo publica renditions aprobadas; ante una publicación errónea, eliminar el
  objeto del destino (almacén/distribución del CDN), retirarlo de `ApprovedPrefix` y volver a publicar.
- **Auth del almacén externo**: para PUBLISH_PUSH a Akamai/R2/Fastly, las credenciales AWS por defecto no
  aplican — establecer `ExternalStoreSecretName` (Secrets Manager, `{"access_key_id","secret_access_key"}`).

## Documentos relacionados

- [Comparativa de integración CDN/edge](../docs/cdn-comparison.es.md)
- [Lista de verificación SigV4 ORIGIN_PULL](../docs/cdn-origin-verification-checklist.es.md) (procedimiento en hardware)
- [Comparativa de arquitecturas alternativas](../docs/comparison-alternatives.md)
- [Playbook de respuesta a incidentes](../docs/incident-response-playbook.md)
