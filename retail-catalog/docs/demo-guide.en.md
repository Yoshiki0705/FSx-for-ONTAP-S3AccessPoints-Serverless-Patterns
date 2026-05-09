# Product Image Tagging & Catalog Metadata Generation — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated product image tagging and catalog metadata generation pipeline. AI-powered image analysis automatically extracts product attributes, building a searchable catalog.

**Core Message**: AI automatically extracts attributes (color, material, category, etc.) from product images, instantly generating catalog metadata.

**Target Duration**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | E-commerce Operator / Catalog Manager / Merchandiser |
| **Daily Tasks** | Product registration, image management, catalog updates |
| **Challenge** | Attribute entry and tagging for new products is time-consuming |
| **Expected Outcome** | Automated product registration and improved searchability |

### Persona: E-commerce Catalog Manager

- Registers 200+ new products weekly
- Manually enters 10+ attribute tags per product
- "I want tags auto-generated just by uploading product images"

---

## Demo Scenario: New Product Batch Registration

### Workflow Overview

```
Product Images     Image Analysis    Attribute Extraction   Catalog Update
(JPEG/PNG)     →   AI Analysis   →  Tag Generation     →   Metadata
                   Object Detection   Category              Registration
                                      Classification
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1: Problem Statement (0:00–0:45)

**Narration Summary**:
> Over 200 new products weekly. Manually entering color, material, category, style tags for each is enormous work. Input errors and inconsistencies also occur.

**Key Visual**: Product image folder, manual tag entry screen

### Section 2: Image Upload (0:45–1:30)

**Narration Summary**:
> Simply place product images in a folder to auto-trigger the tagging pipeline.

**Key Visual**: Image upload → workflow auto-trigger

### Section 3: AI Analysis (1:30–2:30)

**Narration Summary**:
> AI analyzes each image, automatically determining product category, color, material, pattern, and style. Multiple attributes extracted simultaneously.

**Key Visual**: Image analysis in progress, attribute extraction results

### Section 4: Tag Generation (2:30–3:45)

**Narration Summary**:
> Convert extracted attributes into standardized tags. Ensure consistency with existing tag taxonomy.

**Key Visual**: Generated tag list, category distribution

### Section 5: Catalog Update (3:45–5:00)

**Narration Summary**:
> Auto-register metadata to catalog. Contributes to improved searchability and product recommendation accuracy. Generate processing summary report.

**Key Visual**: Catalog update results, AI summary report

---

## Screen Capture Plan

| # | Screen | Section |
|---|--------|---------|
| 1 | Product image folder | Section 1 |
| 2 | Pipeline trigger screen | Section 2 |
| 3 | AI image analysis results | Section 3 |
| 4 | Tag generation results list | Section 4 |
| 5 | Catalog update summary | Section 5 |

---

## Narration Outline

| Section | Time | Key Message |
|---------|------|-------------|
| Problem | 0:00–0:45 | "Manual tagging of 200 products weekly is enormous work" |
| Upload | 0:45–1:30 | "Image placement starts automated tagging" |
| Analysis | 1:30–2:30 | "AI auto-determines color, material, and category" |
| Tags | 2:30–3:45 | "Auto-generate standardized tags" |
| Catalog | 3:45–5:00 | "Auto-register to catalog, improving searchability" |

---

## Sample Data Requirements

| # | Data | Purpose |
|---|------|---------|
| 1 | Apparel product images (10) | Main processing target |
| 2 | Furniture product images (5) | Category classification demo |
| 3 | Accessory images (5) | Multi-attribute extraction demo |
| 4 | Existing tag taxonomy master | Standardization demo |

---

## Timeline

### Achievable Within 1 Week

| Task | Duration |
|------|----------|
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
|-----------|------|
| Step Functions | Workflow orchestration |
| Lambda (Image Analyzer) | Image analysis via Bedrock/Rekognition |
| Lambda (Tag Generator) | Attribute tag generation/standardization |
| Lambda (Catalog Updater) | Catalog metadata registration |
| Lambda (Report Generator) | Processing summary report generation |

### Fallback

| Scenario | Response |
|----------|----------|
| Image analysis accuracy issues | Use pre-analyzed results |
| Bedrock delay | Display pre-generated tags |

---

*This document serves as a production guide for technical presentation demo videos.*
