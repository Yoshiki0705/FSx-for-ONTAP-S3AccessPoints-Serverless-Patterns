# OPS5: Cost Optimization

🌐 **Language / 言語**: [日本語](README.md) | English

## Overview

Decomposes FSx for ONTAP cost structure, provides unit economics ($/GB),
growth projection, top cost driver analysis, and AI recommendations.

**Cost components**: SSD capacity + Capacity Pool + Throughput + Backup

## Testing

```bash
python3 -m pytest operations/cost-optimization/tests/ -v
```
