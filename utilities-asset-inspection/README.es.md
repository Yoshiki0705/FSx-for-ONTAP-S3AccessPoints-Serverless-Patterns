# UC25: Energía y servicios públicos — Inspección por drones / Detección de anomalías SCADA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | Español

📚 **Documentación**: [Arquitectura](docs/architecture.es.md) | [Guía de demostración](docs/demo-guide.es.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to detect equipment defects from drone inspection images of transmission facilities, identify anomalies in SCADA time-series logs, and analyze thermal hot-spots from FLIR imagery.

## Success Metrics

| Metric | Target |
|--------|--------|
| Defect detection rate | ≥ 85% |
| SCADA anomaly false positive rate | < 10% |
| Thermal hot-spot detection accuracy | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $3.00 |
| Human review required rate | > 30% (all critical severity detections reviewed) |

## Architecture

See [Architecture Document](docs/architecture.es.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled

> **Nota S3 AP NetworkOrigin**: La Lambda Discovery se despliega dentro de un VPC. Si el NetworkOrigin del S3 Access Point es `Internet`, no se puede acceder a través del S3 Gateway VPC Endpoint (las solicitudes no se enrutan al plano de datos FSx). Use un S3 AP de tipo VPC-origin o configure el acceso mediante NAT Gateway. Ver [Notas de compatibilidad S3AP](../docs/s3ap-compatibility-notes.md).

## Deployment

```bash
aws cloudformation deploy \
  --template-file utilities-asset-inspection/template.yaml \
  --stack-name fsxn-utilities-inspection \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```


## ⚠️ Consideraciones de rendimiento

- La capacidad de rendimiento de FSx for ONTAP se **comparte entre NFS/SMB/S3 AP**. Ejecutar con MapConcurrency=10 en paralelo puede afectar otras cargas de trabajo en el mismo volumen.
- Para el procesamiento por lotes de gran volumen, verifique la Throughput Capacity (MBps) de FSx ONTAP y ajuste MapConcurrency en consecuencia.
- Recomendado: Comience con MapConcurrency=5 en producción, monitoree las métricas de CloudWatch (ThroughputUtilization) y aumente gradualmente.

## Cleanup

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. SCADA data is critical infrastructure information. Access control and audit log retention must comply with applicable electricity business regulations and critical infrastructure protection guidelines.

> **Related Regulations**: 電気事業法 (Electricity Business Act), 電気設備技術基準

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
