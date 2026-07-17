# OPS6: QoS Monitoring — QoS ポリシー監視

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

## 概要

FSx for ONTAP の QoS (Quality of Service) ポリシーの遵守状況を監視し、
帯域争奪 (noisy-neighbor) リスクの検出とワークロード分離推奨を提供するパターン。

## 検出項目

| 検出 | 重要度 | 説明 |
|------|:------:|------|
| QoS ポリシー未割当てボリューム | Medium | ポリシーなしは帯域無制限 → 他ワークロードに影響 |
| スループット制限なしポリシー | Low | max_throughput 未設定 → バースト時に帯域争奪 |
| 1ポリシーに多数ボリューム | Low | 10+ ボリュームで共有 → ポリシー分割推奨 |

## テスト

```bash
python3 -m pytest operations/qos-monitoring/tests/ -v
```
