# FC4: Automotive CAE — デモガイド

## Executive Summary

自動車 CAE シミュレーション結果の自動品質チェック・統計集計を実演する。

**デモの核心メッセージ**: 解析結果の品質確認を自動化し、設計イテレーションを加速する。

**想定時間**: 3〜5 分

---

## Demo Scenario

### ワークフロー

```
ソルバー実行完了 → S3 AP で結果検出 → パース → 品質チェック → レポート生成
```

### デモステップ

1. **サンプルソルバー出力の確認**: FSx ONTAP 上の解析結果ファイル
2. **ワークフロー実行**: Step Functions で自動解析パイプライン起動
3. **パース結果確認**: メトリクス抽出結果（エネルギー、変位、応力）
4. **品質チェック**: 閾値超過の自動検出
5. **レポート**: Bedrock による自然言語サマリー

---

## 出力サンプル

```json
{
  "solver": "LS-DYNA",
  "job_id": "crash-sim-2026-05-001",
  "metrics": {
    "total_energy": 45230.5,
    "max_displacement_mm": 127.3,
    "max_stress_mpa": 892.1,
    "termination_time_ms": 120.0
  },
  "quality_check": {
    "energy_balance_error_pct": 0.3,
    "hourglass_energy_pct": 2.1,
    "negative_volume_elements": 0,
    "overall_pass": true
  }
}
```
