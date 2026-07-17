# OPS5: Cost Optimization — FinOps 統合コスト最適化

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

## 概要

FSx for ONTAP のコスト構成を分解・可視化し、単位経済 ($/GB)、成長予測、
トップコストドライバー分析、AI 推奨を提供する FinOps パターン。

**コスト構成要素**: SSD容量 + Capacity Pool + スループット + バックアップ

## テスト

```bash
python3 -m pytest operations/cost-optimization/tests/ -v
```
