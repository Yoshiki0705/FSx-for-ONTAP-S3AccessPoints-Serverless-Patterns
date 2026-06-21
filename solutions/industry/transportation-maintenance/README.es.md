# UC22: Transporte y Ferrocarril — Análisis de imágenes de inspección / Gestión de informes de mantenimiento

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Descripción general

Flujo de trabajo serverless que detecta indicadores de deterioro en imágenes de inspección de infraestructura ferroviaria. **Infraestructura crítica para la seguridad: umbral de detección más bajo + revisión humana obligatoria.**

## Success Metrics

| Métrica | Objetivo |
|---------|----------|
| Tasa de detección (estándar) | >= 85% |
| Tasa de detección (crítica) | >= 95% |
| Precisión clasificación severidad | >= 80% |
| Tasa de falsos negativos (crítica) | < 5% |

## Nota de gobernanza

> Los resultados de detección AI no son juicios finales — la confirmación por un ingeniero cualificado es obligatoria.

## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar con MapConcurrency=10 en paralelo puede afectar otras cargas de trabajo en el mismo volumen.
- Para el procesamiento por lotes de gran volumen, verifique la Throughput Capacity (MBps) de FSx for ONTAP y ajuste MapConcurrency en consecuencia.
- Recomendado: Comience con MapConcurrency=5 en producción, monitoree las métricas de CloudWatch (ThroughputUtilization) y aumente gradualmente.

> **Nota S3 AP NetworkOrigin**: La Lambda Discovery se despliega dentro de un VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos FSx). Use un S3 AP de tipo VPC-origin o configure el acceso mediante NAT Gateway. Ver [Notas de compatibilidad S3AP](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
