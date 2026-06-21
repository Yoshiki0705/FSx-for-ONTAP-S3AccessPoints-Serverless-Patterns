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

---

## Industry Reference Cases

> **Evidence Tier**: Public (official blog / conference sessions)

### AstraZeneca: Multi-Agent System (DAIS 2026)

AstraZeneca built a multi-agent system for commercial teams to access pharmaceutical data (structured + unstructured, 400K+ clinical documents) across therapeutic areas. A Supervisor Agent coordinates therapeutic-area-specific sub-agents while preserving permission boundaries, scaling from 5 PoC agents to 20+ production agents.

- **Results**: 10x agent scale (5 PoC → 20+ production, designed for 50+)
- **Architecture**: Supervisor Agent + therapeutic area sub-agents + structured data query (NL-to-SQL) + unstructured document RAG + row/column-level security
- **Key lessons**: Permission-preserving design, supervisor split vs. agent addition criteria, human-in-the-loop testing, data quality importance
- **FSx for ONTAP relevance**: Clinical documents stored on NAS shares → S3 AP for AI pipeline access → ACL metadata extracted and propagated to vector DB → therapeutic-area-level permission filtering at search time

This pattern (UC7) solves the same class of problem (research document AI analysis + classification) using FSx for ONTAP S3 AP + AWS Bedrock. Multi-agent extension can be realized via Step Functions with therapeutic-area routing.

Detailed analysis: [DAIS 2026 Agent Bricks Industry Cases](../docs/investigations/dais2026-agent-bricks-industry-cases.md)

Sources:
- [DAIS 2026 Session: AstraZeneca's Multi-Agent System](https://www.databricks.com/dataaisummit/session/astrazenecas-multi-agent-system-lessons-scaling-agents-10x-agent-bricks)
- [Agent Bricks DAIS 2026 Blog](https://www.databricks.com/blog/agent-bricks-dais-2026)

---

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. Organizations should consult qualified professionals.
