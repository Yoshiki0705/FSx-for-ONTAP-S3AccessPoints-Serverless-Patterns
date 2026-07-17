# OPS2: Storage Efficiency — 重複排除/圧縮効率

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

## 概要

FSx for ONTAP の重複排除 (deduplication) と圧縮 (compression) の効率比を追跡し、
低効率ボリュームに有効化・チューニング推奨を提供するパターン。

## 推奨ロジック

| 状態 | 推奨 |
|------|------|
| dedupe=off, compression=off | 両方有効化 (推定 2:1 効率) |
| 有効だが ratio < MinEfficiencyRatio | データパターンの確認を推奨 |
| 高効率 (ratio ≥ 1.5) | 推奨なし |

## テスト

```bash
python3 -m pytest operations/storage-efficiency/tests/ -v
```
