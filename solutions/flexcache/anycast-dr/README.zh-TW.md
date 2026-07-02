# FlexCache AnyCast / DR 模式

🌐 **Language / 語言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

本模式提供設計指南、模擬演示和維運設計文件，用於實現 ONTAP FlexCache AnyCast 和 DR（災難復原）配置與 FSx for ONTAP × S3 Access Points × AWS Serverless 服務的結合。

## 解決的問題

| 問題 | FlexCache AnyCast / DR 解決方案 |
|------|-------------------------------|
| 地理分散團隊的讀取效能 | 從最近的 FlexCache 提供熱資料 |
| EDA/媒體/HPC 雲端爆發 | 本地 Origin + 雲端 FlexCache 減少 WAN 傳輸 |
| DR 期間的讀取連續性 | Origin 故障時快取讀取持續 |
| WAN 傳輸量減少 | 僅快取熱資料，增量傳輸 |
| 用戶端掛載配置複雜性 | 透過 AnyCast IP 實現單一掛載點 |

## 成功指標

| 指標 | 目標 |
|------|------|
| 故障偵測時間 | < 30 秒 |
| DNS 傳播時間 | < 60 秒 |
| 故障轉移期間讀取連續性 | > 99.9% |
| 快取命中率（熱資料） | > 80% |
| WAN 傳輸減少率 | > 60% |

---

## 部署

使用 AWS SAM CLI 部署（請將佔位參數替換為您的環境值）：

```bash
# パラメータファイルを編集
cp params/staging.json params/flexcache-anycast-demo.json
# 必要なパラメータを設定

# デプロイ
# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name flexcache-anycast-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    SimulationMode=true \
    CacheEndpoints="cache-a.example.com,cache-b.example.com" \
    HealthCheckIntervalMinutes=5
```

> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。

## Governance Note

> 本模式提供技術架構指導。不構成法律、合規或監管建議。組織應諮詢合格的專業人員。
