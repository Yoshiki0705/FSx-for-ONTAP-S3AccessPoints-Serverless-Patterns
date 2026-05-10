# UC17: Smart City — Geospatial Analytics & Urban Planning

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/uc17-architecture.md) | [Demo Script](docs/uc17-demo-script.md)

> **Nota**: Esta traducción es un borrador generado automáticamente. Se agradecen las revisiones.

## Overview

Serverless pipeline for municipal geospatial data (GeoTIFF / Shapefile / GeoJSON / LAS / GeoPackage) automating CRS normalization, land use classification, change detection, infrastructure assessment, disaster risk mapping, and Bedrock-driven urban planning report generation.

### When this pattern is suitable
- Municipalities storing GIS data on FSx ONTAP with department-level access control
- Periodic analysis of land use changes (new buildings, green area reduction, road expansion)
- Flood / earthquake / landslide risk score computation for urban planning
- Automated Japanese-language planning report generation for city officials

### When this pattern is NOT suitable
- Real-time traffic optimization (dedicated streaming pipeline recommended)
- Interactive 3D GIS visualization (ArcGIS / QGIS desktop recommended)
- Network congestion simulation (specialized HPC cluster needed)

### Key features
- **Discovery**: Enumerate GeoTIFF / Shapefile / GeoJSON / LAS / GeoPackage
- **Preprocessing**: Normalize to `EPSG:4326` (WGS84) via pyproj Layer (optional)
- **Land Use Classification**: Rekognition / SageMaker route for raster imagery
- **Change Detection**: DynamoDB keyed by SHA256 of source_key, L1 distribution delta
- **Infra Assessment**: LAS point cloud analysis via laspy Layer (condition score GOOD/FAIR/POOR)
- **Risk Mapping**: Flood (elevation + water proximity + impervious rate), earthquake (soil + density), landslide (slope + precipitation + vegetation)
- **Report Generation**: Bedrock Nova Lite creates Japanese-language planning commentary

### Public Sector compliance
- INSPIRE Directive alignment (EU geospatial data infrastructure)
- OGC standards (WMS / WFS / GeoPackage)
- Open Data publishing workflow


### Capturas de pantalla UI/UX verificadas

> Esta sección muestra **pantallas UI/UX que el personal general utiliza en el día a día**. Las vistas técnicas como gráficos de Step Functions están documentadas en `docs/verification-results-phase7.md`.

#### 1. Colocación de datos GIS (vía S3 AP)

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png -->
![UC17: Colocación de GIS](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

#### 2. Informe de planificación urbana generado por Bedrock

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png -->
![UC17: Informe Bedrock](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

#### 3. Mapa de riesgos de desastres (JSON)

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png -->
![UC17: Mapa de riesgos](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

#### 4. Distribución de uso del suelo

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png -->
![UC17: Distribución de uso](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

#### 5. Cambio temporal (DynamoDB)

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png -->
![UC17: Historial de uso](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)

## Deploy

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

## Directory layout

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/
│   ├── preprocessing/
│   ├── land_use_classification/
│   ├── change_detection/
│   ├── infra_assessment/
│   ├── risk_mapping/
│   └── report_generation/
├── tests/
└── docs/
```