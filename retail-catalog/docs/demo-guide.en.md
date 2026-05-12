# Product Image Tagging and Catalog Metadata Generation — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Executive Summary

This demo demonstrates an automated product image tagging and catalog metadata generation pipeline. It automatically extracts product attributes through AI-powered image analysis and builds a searchable catalog.

**Core Demo Message**: AI automatically extracts attributes (color, material, category, etc.) from product images and instantly generates catalog metadata.

**Estimated Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|------|
| **Role** | E-commerce Site Operator / Catalog Manager / Merchandising Manager |
| **Daily Tasks** | Product registration, image management, catalog updates |
| **Challenges** | Time-consuming attribute entry and tagging for new products |
| **Expected Outcomes** | Automation of product registration and improved searchability |

### Persona: Yoshida-san (E-commerce Catalog Manager)

- Registers 200+ new products per week
- Manually enters 10+ attribute tags per product
- "I want to auto-generate tags just by uploading product images"

---

## Demo Scenario: New Product Batch Registration

### Overall Workflow

```
Product Images    Image Analysis    Attribute Extraction    Catalog Update
(JPEG/PNG)    →   AI Analysis   →   Tag Generation     →    Metadata
                  Object Detection  Category Classification  Registration
```

---

## Storyboard (5 Sections / 3–5 minutes)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 200 new products per week. Manually entering tags for color, material, category, style, etc. for each product is an enormous task. Input errors and inconsistencies also occur.

**Key Visual**: Product image folder, manual tag entry screen

### Section 2: Image Upload (0:45–1:30)

**Narration Summary**:
> Simply place product images in a folder to trigger the automated tagging pipeline.

**Key Visual**: Image upload → Automatic workflow activation

### Section 3: AI Analysis (1:30–2:30)

**Narration Summary**:
> AI analyzes each image and automatically determines product category, color, material, pattern, and style. Extracts multiple attributes simultaneously.

**Key Visual**: Image analysis in progress, attribute extraction results

### Section 4: Tag Generation (2:30–3:45)

**Narration Summary**:
> Converts extracted attributes into standardized tags. Ensures consistency with existing tag taxonomy.

**Key Visual**: Generated tag list, distribution by category

### Section 5: Catalog Update (3:45–5:00)

**Narration Summary**:
> Automatically registers metadata to the catalog. Contributes to improved searchability and product recommendation accuracy. Generates processing summary report.

**Key Visual**: Catalog update results, AI summary report

---

## Screen Capture Plan

| # | Screen | Section |
|---|------|-----------|
| 1 | Product image folder | Section 1 |
| 2 | Pipeline launch screen | Section 2 |
| 3 | AI image analysis results | Section 3 |
| 4 | Tag generation results list | Section 4 |
| 5 | Catalog update summary | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "Manual tagging of 200 products per week is an enormous task" |
| Upload | 0:45–1:30 | "Auto-tagging starts just by placing images" |
| Analysis | 1:30–2:30 | "AI automatically determines color, material, and category" |
| Tags | 2:30–3:45 | "Automatically generates standardized tags" |
| Catalog | 3:45–5:00 | "Automatically registers to catalog, improving searchability" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|--------|------|
| 1 | Apparel product images (10 images) | Main processing target |
| 2 | Furniture product images (5 images) | Category classification demo |
| 3 | Accessory images (5 images) | Multi-attribute extraction demo |
| 4 | Existing tag taxonomy master | Standardization demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Time Required |
|--------|---------|
| Prepare sample product images | 2 hours |
| Verify pipeline execution | 2 hours |
| Capture screenshots | 2 hours |
| Create narration script | 2 hours |
| Video editing | 4 hours |

### Future Enhancements

- Similar product search
- Automatic product description generation
- Trend analysis integration

---

## Technical Notes

| Component | Role |
|--------------|------|
| Step Functions | Workflow orchestration |
| Lambda (Image Analyzer) | Image analysis via Bedrock/Rekognition |
| Lambda (Tag Generator) | Attribute tag generation and standardization |
| Lambda (Catalog Updater) | Catalog metadata registration |
| Lambda (Report Generator) | Processing summary report generation |

### Fallback

| Scenario | Response |
|---------|------|
| Insufficient image analysis accuracy | Use pre-analyzed results |
| Bedrock latency | Display pre-generated tags |

---

*This document is a production guide for technical presentation demo videos.*

---

## Verified UI/UX Screenshots (2026-05-10 AWS Verification)

Following the same approach as Phase 7, capturing **UI/UX screens that e-commerce staff actually use in daily operations**.
Technical screens (Step Functions graphs, etc.) are excluded.

### Output Destination Selection: Standard S3 vs FSxN S3AP

UC11 supports the `OutputDestination` parameter as of the 2026-05-10 update.
**Writing AI outputs back to the same FSx volume** allows SMB/NFS users to
view auto-generated tag JSON within the product image directory structure
("no data movement" pattern).

```bash
# STANDARD_S3 mode (default, traditional behavior)
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP mode (write AI outputs back to FSx ONTAP volume)
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

For AWS specification constraints and workarounds, refer to the ["AWS Specification Constraints and Workarounds"
section in the project README](../../README.md#aws-仕様上の制約と回避策).

### 1. Automated Product Image Tagging Results

AI analysis results received by e-commerce managers during new product registration. Rekognition detected 7 labels from the actual image
(`Oval` 99.93%, `Food`, `Furniture`, `Table`, `Sweets`, `Cocoa`, `Dessert`).

<!-- SCREENSHOT: uc11-product-tags.png
     Content: Product image + AI detected tag list (with confidence scores)
     Masked: Account ID, bucket name -->
![UC11: Product Tags](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. S3 Output Bucket — Overview of Tag and Quality Check Results

Screen where e-commerce operations staff verify batch processing results.
JSON files are generated per product under two prefixes: `tags/` and `quality/`.

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     Content: S3 console showing tags/, quality/ prefixes
     Masked: Account ID -->
![UC11: S3 Output Bucket](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### Actual Measurements (2026-05-10 AWS Deployment Verification)

- **Step Functions Execution**: SUCCEEDED, parallel processing of 4 product images
- **Rekognition**: Detected 7 labels from actual images (highest confidence 99.93%)
- **Generated JSON**: tags/*.json (~750 bytes), quality/*.json (~420 bytes)
- **Actual Stack**: `fsxn-retail-catalog-demo` (ap-northeast-1, verified on 2026-05-10)
