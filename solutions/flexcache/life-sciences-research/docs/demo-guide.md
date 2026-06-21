# FC5: Life Sciences Research — デモガイド

## Executive Summary

研究データの自動分類・メタデータ抽出を実演する。

**デモの核心メッセージ**: 研究データの整理・カタログ化を自動化し、データ再利用性を向上。

**想定時間**: 3〜5 分

---

## Demo Scenario

1. **データ検出**: FSx for ONTAP 上の研究データを S3 AP 経由で自動検出
2. **分類**: ファイル形式・内容に基づく自動分類
3. **メタデータ抽出**: 顕微鏡パラメータ、シーケンス品質等
4. **レポート**: 研究データカタログの自動生成

---

## 出力サンプル

```json
{
  "file": "microscopy/experiment-2026-05/sample-A/z-stack-001.nd2",
  "classification": "fluorescence_microscopy",
  "metadata": {
    "microscope": "Nikon Ti2-E",
    "objective": "60x/1.4 Oil",
    "channels": ["DAPI", "GFP", "mCherry"],
    "z_slices": 50,
    "pixel_size_um": 0.108,
    "acquisition_date": "2026-05-15"
  },
  "quality_metrics": {
    "signal_to_noise": 12.3,
    "focus_score": 0.87,
    "saturation_pct": 0.2
  }
}
```


## スクリーンショット

![Phase 13 — CloudFormation Stacks](../../docs/screenshots/masked/phase13-cloudformation-stacks.png)
![Phase 13 — Lambda Functions](../../docs/screenshots/masked/phase13-lambda-functions.png)
