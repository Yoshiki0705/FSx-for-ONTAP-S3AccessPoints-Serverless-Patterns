# Organizaciones sin fines de lucro — Clasificación de solicitudes de subvención / Coincidencia de resultados Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

This demo showcases an automated pipeline where AI/ML services analyze files on FSx for ONTAP via S3 Access Points.

**Estimated Time**: 3–5 minutes

---

## Quick Start

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/nonprofit-grant-management
sam build
sam deploy \
  --stack-name fsxn-nonprofit-grants-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

---

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|-----------|
| Discovery Lambda timeout | S3 AP access failure | Check NetworkOrigin setting |
| `AccessDenied` | IAM policy ARN format | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` |
| AI/ML service error | Region configuration | Check Cross-Region settings |

---

---

## Capturas de pantalla

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc24-demo/step-functions-graph-view.png)


## Cleanup

```bash
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants-demo --region ap-northeast-1
```
