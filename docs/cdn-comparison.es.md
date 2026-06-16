# Comparativa de integración CDN / edge — Distribución desde FSx ONTAP S3 Access Points

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. Alcance

Referencia de viabilidad técnica para distribuir datos en los FSx for ONTAP S3 Access Points (S3 AP) a
través de una red CDN/edge. Este documento **no** clasifica proveedores, no compara precio/rendimiento ni
hace afirmaciones de marketing. Solo aborda **qué es técnicamente alcanzable, qué no lo es y qué requiere
verificación** frente a las restricciones del S3 AP de FSx ONTAP. La selección del proveedor depende de
factores fuera de este alcance (contratos, SLA, operación, requisitos regionales) y es responsabilidad del cliente.

## 1. Restricciones del S3 AP que determinan el diseño de distribución

| Restricción | Detalle | Impacto en la distribución |
|-------------|---------|----------------------------|
| Block Public Access forzado (no desactivable) | Activado por defecto, inmutable | Sin origen público sin autenticación; se requiere auth de origen |
| Auth de origen es SigV4 (IAM) | Solicitudes evaluadas por IAM / política AP | El CDN debe firmar las solicitudes de origen con AWS SigV4 |
| Autorización en dos capas (AWS + ONTAP) | IAM y luego identidad de archivo ONTAP (UNIX UID / Windows AD) | Distribución limitada a lo que la identidad ONTAP puede leer |
| URL prefirmadas no admitidas | Oficialmente no soportadas | La auth por token de espectador no puede usar URL prefirmadas S3; usar tokens nativos del CDN |
| NetworkOrigin (Internet/VPC, inmutable) | El CDN accede desde red gestionada/externa | La integración CDN necesita **origen Internet** |
| PutObject máx. 5 GB | Límite de un único PUT | Las reescrituras grandes requieren multipart |

## 2. Mecanismos de integración (neutrales respecto al proveedor)

- **M1 — Origin-pull SigV4 nativo**: el CDN obtiene el S3 AP directamente firmando en SigV4. Alcanzable
  cuando el CDN incorpora firma de origen SigV4. **Por verificar**: el host `accesspoint alias` del S3 AP
  difiere de un bucket estándar; el comportamiento SigV4 debe validarse en hardware.
- **M2 — Firma SigV4 por edge compute**: implementar SigV4 en el runtime edge del CDN
  (Workers/Compute/EdgeWorkers). Alcanzable cuando no hay firma de origen nativa; usted gestiona la
  firma y las claves.
- **M3 — Push a un almacén compatible con S3 nativo del CDN**: mantener FSx como master, replicar solo las
  renditions aprobadas al almacén de objetos del CDN. Evita la cuestión de la auth de origen; neutral
  respecto al proveedor; primer paso de menor riesgo.
- **M4 — Proxy de firma SigV4 autogestionado**: colocar un intermediario de firma (Lambda Function URL /
  ALB) como origen. Funciona con casi cualquier CDN; el proxy se convierte en un punto de
  disponibilidad/escalado.

> Restricción universal: la auth por token de espectador no puede usar URL prefirmadas S3 — usar tokens
> nativos del CDN. La distribución pública omite las ACL NFS/SMB, por lo que solo se distribuyen renditions
> aprobadas (ver sección 4).

## 3. Soporte de mecanismos por red de distribución (basado en hechos)

○ = función nativa documentada / △ = condicional o autoimplementado / − = sin esa función / TBV = se requiere verificación específica del S3 AP.

| Red | M1 pull SigV4 nativo | M2 firma edge | M3 almacén S3-compatible propio | Token de espectador | TBV específico del S3 AP |
|-----|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | (a S3 estándar) | URL/Cookie firmadas de CloudFront | **Probado** (el tutorial oficial de AWS muestra S3 AP + OAC) |
| Akamai | ○ Cloud Access Manager (firma AWS) | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | Firma en host AP alias TBV |
| Fastly | ○ SigV4 a origen privado S3-compatible | △ Compute | ○ Fastly Object Storage | URL firmada de Fastly | SigV4 en AP alias TBV |
| Cloudflare | − (sin SigV4 nativo en el proxy) | ○ Firma SigV4 vía Workers | ○ R2 (S3-compatible) | URL firmada de Cloudflare | Firma con Workers + AP alias TBV |
| Bunny.net | △ Origin-pull S3 (tipo de origen AWS S3) | − | ○ Bunny Storage (API S3-compatible, beta) | Auth por token de Pull Zone | Firma en AP alias TBV |
| Google Cloud CDN / Media CDN | ○ Auth SigV4 de origen privado S3-compatible | △ Enrutamiento Media CDN | (GCS / cualquier S3-compatible) | URL/Cookie firmadas de Media CDN | Egress entre nubes + AP alias TBV |

### Mencionados pero no clasificados en la tabla
- **Azure Front Door / Azure CDN**: el mismo mecanismo (M1/M4) puede aplicarse; fuera del alcance principal; TBV.
- **Gcore**: almacenamiento de objetos S3-compatible + almacenamiento-como-origen (M3); fuera del alcance principal.
- **Edgio (antes Limelight / Edgecast)**: **servicio CDN cesado el 2025-01-15**; la mayoría de los activos
  adquiridos por Akamai. **No es una opción activa** — excluido.

> Las fuentes son docs públicas de proveedores (CloudFront OAC, Akamai Cloud Access Manager, orígenes
> privados S3-compatibles de Fastly, Cloudflare Workers/R2, Bunny Storage, Google Media CDN). Todas describen
> **buckets S3-compatibles estándar**; el comportamiento en el accesspoint alias del S3 AP de FSx ONTAP es TBV.

## 4. Requisitos de seguridad fijos (independientes del mecanismo)

1. La distribución pública omite las ACL NFS/SMB — distribuir **solo renditions aprobadas**; nunca enrutar
   datos master controlados por ACL directamente a la capa de distribución.
2. Separar el master (controlado por ACL, sensible) de los artefactos de distribución (público/semipúblico).
   M3 hace natural esta separación.
3. Auth de espectador mediante tokens nativos del CDN (sin URL prefirmadas S3).
4. Credenciales de origen con mínimo privilegio; evitar claves de larga duración en el edge; preferir
   credenciales efímeras.
5. Logs de distribución: tratar la PII del espectador al reescribir los logs hacia FSx.
6. **Trazabilidad de aprobación**: registrar qué objeto se aprobó para distribución pública, por quién y
   cuándo. Los objetos sin aprobador registrado se **visibilizan** (`unrecorded`), no se bloquean en silencio.
7. **Residencia de datos / restricción geográfica**: los CDN distribuyen globalmente. Excluir los datos que
   no pueden salir de una región, o imponer geo-blocking; incluir comprobaciones de residencia en el proceso
   de aprobación.

### 4.1 Clasificación de evidencia
- **Evidencia pública**: capacidades de proveedores de la sección 3 — basadas en docs públicas,
  **dependientes del momento**, reverificar antes de adoptar.
- **Por verificar (este proyecto)**: comportamiento de la firma de origen SigV4 frente al accesspoint alias
  del S3 AP de FSx ONTAP.

## 5. Resumen de viabilidad

| Pregunta | Respuesta |
|----------|-----------|
| ¿Exponer el S3 AP como origen CDN sin autenticación? | **No** (BPA forzado) |
| ¿Distribuir directamente desde el S3 AP vía CDN? | **Sí, condicionalmente** — M1/M2 con SigV4; la firma AP-alias es TBV |
| ¿Distribuir vía un CDN sin SigV4? | **Sí** — M3 (push) o M4 (proxy de firma) |
| ¿Usar URL prefirmadas S3 para los espectadores? | **No** — usar tokens nativos del CDN |
| ¿Imponer las ACL de ONTAP en el momento de la distribución? | **No** — garantizado vía "solo renditions aprobadas" + trazabilidad |
| ¿Primer paso de menor riesgo de verificación? | **M3 (push)** — evita la auth de origen, neutral, compatible con DemoMode |

> **Governance Caveat**: esta es información técnica de referencia. Las funciones de los proveedores cambian;
> reverifique con la documentación oficial más reciente antes de adoptar. La firma de origen SigV4 frente al
> accesspoint alias del S3 AP es un punto de verificación del proyecto (TBV). La selección del proveedor es
> decisión del cliente.
