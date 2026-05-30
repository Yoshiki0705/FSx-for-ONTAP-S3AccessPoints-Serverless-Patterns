# Life Sciences Research — Data Classification & Metadata Extraction

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## Overview

Automated classification and metadata extraction pipeline for life sciences research data (microscopy images, sequence data, research papers). Leverages FlexCache for multi-site research data sharing.

## Problems Solved

| Problem | Solution |
|---------|----------|
| Unorganized research data across file servers | Automated classification by data type |
| Manual metadata cataloging | AI-powered metadata extraction |
| Slow data access for remote research sites | FlexCache for multi-site sharing |
| Difficulty finding relevant datasets | Searchable metadata catalog |

## Supported Data Formats

| Category | Formats | Description |
|----------|---------|-------------|
| Microscopy images | .tiff, .nd2, .czi | Fluorescence, confocal, electron microscopy |
| Sequence data | .fastq, .bam, .vcf | NGS sequencing results |
| Research papers | .pdf | Literature, protocols, reports |
| Structural data | .pdb, .cif | Protein structures |

## Role of FlexCache

- **Multi-site sharing**: Headquarters → each research site
- **Large datasets**: Cache microscopy images (hundreds of GB)
- **Collaboration**: Multiple teams analyzing the same dataset in parallel

## Success Metrics

| Metric | Target |
|--------|--------|
| Files classified per execution | > 500 files |
| Classification accuracy | > 85% |
| Metadata extraction success rate | > 90% |
| Processing time per file | < 5 sec |
| Human Review rate | < 10% (low-confidence classifications) |
