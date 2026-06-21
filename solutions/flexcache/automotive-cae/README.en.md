# Automotive CAE — Simulation Result Analysis

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## Overview

Automated analysis pipeline for automotive CAE (Computer-Aided Engineering) simulation results. Reads solver outputs (LS-DYNA, STAR-CCM+, Nastran, etc.) from FSx for ONTAP via S3 Access Points and automates quality checks, statistical aggregation, and report generation.

## Problems Solved

| Problem | Solution |
|---------|----------|
| Manual review of simulation results | Automated quality check + AI summary |
| Scattered solver outputs across file servers | Centralized discovery via S3 AP |
| Lack of cross-simulation analytics | Athena/Glue integration for trend analysis |
| Slow data access for HPC clusters | FlexCache near compute for fast reads |

## Supported Solvers

| Solver | Output Format | Extracted Metrics |
|--------|--------------|-------------------|
| LS-DYNA | d3plot, binout | Energy, displacement, stress |
| STAR-CCM+ | .sim, .csv | Flow velocity, pressure, temperature |
| Nastran | .op2, .f06 | Mode frequency, stress |
| Abaqus | .odb | Displacement, stress, strain |
| OpenFOAM | postProcessing/ | Residuals, force coefficients |

## Role of FlexCache

- **Design-to-analysis data sharing**: Origin (design team) → FlexCache (near HPC cluster)
- **Fast read of large results**: Cache multi-GB result files
- **Multi-site sharing**: Share data across analysis teams at multiple locations

## Success Metrics

| Metric | Target |
|--------|--------|
| Solver outputs processed per run | > 50 files |
| Quality check pass rate | > 85% |
| Report generation time | < 3 min |
| Cost per execution | < $5 |
| Human Review rate | < 15% (quality failures) |
