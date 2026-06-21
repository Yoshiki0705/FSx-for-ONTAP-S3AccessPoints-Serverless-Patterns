# ORIGIN_PULL SigV4 × S3 AP alias — Lista de verificación en hardware

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## Propósito

Procedimiento reproducible para resolver, en hardware real, los puntos marcados como **por verificar (TBV)**
en la [comparativa CDN](cdn-comparison.es.md): es decir, **si la firma de origen SigV4 de cada CDN funciona
sobre el host `accesspoint alias` del S3 Access Point de FSx for ONTAP igual que sobre un bucket S3 estándar**.

Úsese para decidir si `DeliveryMode=ORIGIN_PULL` (M1/M2) de `solutions/edge/content-delivery` es viable.
**M3 (PUBLISH_PUSH) no depende de esta verificación** (evita la auth de origen).

> **Distinción**: esta es una medición en un entorno de prueba específico. No trate el comportamiento general
> de S3 ni el historial de un CDN sobre buckets estándar como una garantía para el alias del S3 AP.

---

## 0. Requisitos previos

- Un sistema de archivos FSx for ONTAP y un S3 Access Point en **Internet-origin** (el VPC-origin no puede
  servir a los CDN)
- El alias del S3 AP (p. ej. `<alias>-ext-s3alias`) y la región objetivo
- Un objeto de prueba bajo el **prefijo aprobado** (p. ej. `delivery-approved/test-1mb.bin`)
  - Según el principio permission-aware, no usar datos master controlados por ACL para la verificación
- Credenciales IAM de **mínimo privilegio** para la firma de origen (solo `s3:GetObject` sobre el AP
  objetivo); preferir credenciales efímeras
- Un host de prueba (curl ≥ 7.75 admite `--aws-sigv4`), AWS CLI v2

> **Seguridad**: nunca deje claves de acceso en logs, capturas o commits durante la verificación.
> Referencie por nombre de clave, no por valor (política de repositorio público).

---

## 1. Verificación de línea base (sin CDN / la más importante)

Sin CDN, confirmar directamente **si el host alias del S3 AP acepta SigV4**. Este es el punto crucial común
a todos los CDN.

### 1.1 AWS CLI (firma del SDK)

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- Esperado: HTTP 200 y obtención correcta del objeto.
- En caso de fallo: aislar IAM / política AP / identidad de archivo ONTAP (UNIX UID / AD) en la
  autorización de dos capas.

### 1.2 SigV4 en crudo (aproxima la firma de origen del CDN)

Los CDN suelen firmar los pulls de origen en SigV4 con una clave de acceso fija. `curl --aws-sigv4`
aproxima ese comportamiento:

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **Si devuelve 200**: el host alias acepta SigV4 como un bucket estándar → M1/M4 probablemente viables.
- **Si falla**: puede deberse a una diferencia de direccionamiento propia del alias → verificar en la
  configuración de origen de cada CDN el formato de host, la región, el nombre de servicio (`s3`) y el
  manejo path-style vs virtual-host.
- Con credenciales temporales, añadir `-H "x-amz-security-token: $AWS_SESSION_TOKEN"`.

### 1.3 Comprobaciones negativas (reconfirmar la especificación)

- Un GET sin firmar devuelve **403/AccessDenied** (confirma la aplicación de Block Public Access).
- Las URL prefirmadas no están disponibles (no se pueden generar/no soportadas) → tokens de espectador vía
  mecanismos nativos del CDN.

---

## 2. Procedimientos por CDN

Para cada CDN, definir "origen = host alias del S3 AP" y confirmar que una obtención de origen en cache-miss
devuelve 200.

### 2.1 Amazon CloudFront (M1 / OAC) — referencia
- Desplegar la plantilla `solutions/edge/content-delivery` con `EnableCloudFront=true` (OAC + `SigningProtocol: sigv4`).
- Verificar: `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200.
- Esperado: éxito según el tutorial oficial de AWS (**probado**).

### 2.2 Fastly (M1 / SigV4 nativo)
- Configurar el host alias como origen privado S3-compatible y habilitar la firma SigV4 (región, servicio `s3`).
- Verificar: GET vía el servicio Fastly → 200. Comprobar que la forma virtual-host del alias se firma
  correctamente con la implementación SigV4 de Fastly.

### 2.3 Cloudflare (M2 / firma con Workers)
- Implementar SigV4 en un Worker y hacer fetch firmado al host alias (si se usa el S3 AP directamente como
  origen, no R2). Verificar: GET vía el Worker → 200; comprobar las cabeceras firmadas / el hash de payload.

### 2.4 Akamai (M1 / Cloud Access Manager)
- Configurar la firma AWS en Cloud Access Manager y establecer el host alias vía Origin Characteristics.
- Verificar: GET vía la propiedad Akamai → 200; confirmar que la firma se aplica sobre el host AP alias.

### 2.5 Bunny.net (M1 / origin-pull S3)
- Establecer el origen de la Pull Zone en el host alias con el tipo de origen AWS S3. Verificar: GET vía la
  Pull Zone → 200.

### 2.6 Google Cloud CDN / Media CDN (M1 / private S3 origin)
- Configurar el host alias con auth SigV4 de origen privado S3-compatible. Verificar: GET vía Media CDN →
  200; comprobar también la ruta de egress entre nubes.

---

## 3. Criterios de aprobación/fallo

| Resultado | Condición |
|-----------|-----------|
| **PASS** | La línea base 1.2 es 200 Y un GET en cache-miss vía el CDN es 200; los tokens de espectador funcionan vía el mecanismo nativo del CDN |
| **CONDITIONAL** | El GET vía CDN es 200 pero requiere configuración adicional (path-style, etc.) o restricciones (cabeceras específicas) |
| **FAIL** | SigV4 al host alias no funciona en el CDN; se necesita una solución alternativa (firma M2 / proxy M4 / cambio a M3) |
| **BLOCKED** | Los requisitos previos (Internet-origin, IAM, objeto de prueba) no están listos; no se puede verificar |

---

## 4. Comprobaciones de seguridad/gobernanza durante la verificación

- [ ] Objetos de prueba solo bajo `delivery-approved/` (sin master controlado por ACL)
- [ ] IAM de firma de origen limitado a `s3:GetObject` sobre el AP objetivo
- [ ] No dejar claves de larga duración en el edge/config (preferir efímeras; revocar después)
- [ ] No dejar claves de acceso, valores reales de alias o ID de cuenta en logs/capturas/commits
- [ ] Tokens de espectador vía mecanismos nativos del CDN (sin URL prefirmadas S3)
- [ ] Limpiar los recursos temporales (distribuciones, pull zones, etc.) creados para la verificación

---

## 5. Tabla de registro de resultados (evidencia)

| CDN | Mecanismo | Config hecha | Línea base 1.2 | GET vía CDN | Token de espectador | Resultado | Evidencia (estado HTTP/cabeceras/marca de tiempo) | Fecha | Rol |
|-----|-----------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> Nota de registro: valores de alias, ID de cuenta, IP como placeholders (`<alias>-ext-s3alias`,
> `123456789012`). Trate los resultados como mediciones en un entorno de prueba específico, no como
> garantías generales.

---

## 6. Retroalimentación de resultados

- Reflejar los resultados confirmados en la [comparativa CDN](cdn-comparison.es.md) sección 3 "TBV específico
  del S3 AP" y 4.1 "por verificar" (TBV → resultado medido).
- Para los CDN en FAIL, recomendar `DeliveryMode=PUBLISH_PUSH` (M3) en `solutions/edge/content-delivery`.

## Documentos relacionados

- [Comparativa de integración CDN/edge](cdn-comparison.es.md)
- [UC content-edge-delivery](../solutions/edge/content-delivery/README.es.md)
- [Notas de compatibilidad S3AP](s3ap-compatibility-notes.md)
