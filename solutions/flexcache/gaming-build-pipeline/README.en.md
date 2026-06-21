# Gaming Build Pipeline — Asset Quality Check & Log Analysis

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## Overview

Automated asset quality checking and build log analysis pipeline for game development. Leverages FlexCache for global studio asset sharing and CI/CD pipeline integration.

## Problems Solved

| Problem | Solution |
|---------|----------|
| Manual texture/asset quality review | Automated Rekognition-based quality check |
| Build log analysis across large teams | AI-powered log pattern analysis (Bedrock) |
| Slow asset distribution to global studios | FlexCache for global asset delivery |
| Late discovery of quality issues | Automated quality gates in build pipeline |

## Supported Game Engines

| Engine | Asset Formats | Check Items |
|--------|--------------|-------------|
| Unreal Engine 5 | .uasset, .umap | Texture resolution, LOD settings |
| Unity | .prefab, .asset | Mesh vertex count, material references |
| Godot | .tscn, .tres | Scene structure, resource references |

## Role of FlexCache

- **Global asset delivery**: Main studio → regional studios
- **Build cache**: Fast asset reads from CI/CD pipelines
- **Version management**: Delta delivery between asset versions

## Success Metrics

| Metric | Target |
|--------|--------|
| Assets checked per execution | > 1,000 |
| Quality check pass rate | > 90% |
| Build log issues detected | 100% (known patterns) |
| Processing time per asset | < 2 sec |
| Human Review rate | < 5% (critical quality failures) |
