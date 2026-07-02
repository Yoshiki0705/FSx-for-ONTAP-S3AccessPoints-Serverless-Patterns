# Gaming Build Pipeline — ゲームアセット共有・ビルドパイプライン

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概要

ゲーム開発スタジオのファイルサーバー（FSx for ONTAP）上のゲームアセット（テクスチャ、モデル、シェーダー、ビルド成果物）を FlexCache でグローバルスタジオ間共有し、S3 Access Points 経由でビルドパイプラインの品質チェック・ログ分析を自動化するパターン。

## 解決する課題

| 課題 | 本パターンによる解決 |
|------|-------------------|
| グローバルスタジオ間のアセット同期遅延 | FlexCache で拠点間キャッシュ |
| ビルド成果物の品質チェック手動化 | S3 AP + Lambda で自動 QC |
| シェーダーコンパイルログの分析 | Athena + Bedrock で自動分析 |
| CI/CD パイプラインのストレージボトルネック | FlexCache で読み取り高速化 |
| アセットバージョン管理の複雑化 | メタデータ自動抽出・カタログ化 |

## アーキテクチャ

```mermaid
graph TB
    subgraph "メインスタジオ（Origin）"
        ORIGIN[FSx for ONTAP<br/>Game Assets<br/>Build Artifacts]
    end
    subgraph "リモートスタジオ A"
        CACHE_A[FlexCache A<br/>Assets Cache]
        DEV_A[開発者 PC<br/>NFS/SMB]
    end
    subgraph "リモートスタジオ B"
        CACHE_B[FlexCache B<br/>Assets Cache]
        DEV_B[開発者 PC<br/>NFS/SMB]
    end
    subgraph "ビルドパイプライン"
        S3AP[S3 Access Point]
        EBS[EventBridge Scheduler]
        SFN[Step Functions]
        DISC[Discovery Lambda<br/>新規ビルド検出]
        QC[QC Lambda<br/>品質チェック]
        LOG[Log Analysis Lambda<br/>ログ分析]
        RPT[Report Lambda]
    end
    subgraph "AI/ML"
        BEDROCK[Amazon Bedrock<br/>ログ要約・異常検知]
        REKOGNITION[Amazon Rekognition<br/>テクスチャ品質]
    end
    ORIGIN --> CACHE_A --> DEV_A
    ORIGIN --> CACHE_B --> DEV_B
    ORIGIN --> S3AP
    EBS --> SFN
    SFN --> DISC --> S3AP
    SFN --> QC --> REKOGNITION
    SFN --> LOG --> BEDROCK
    SFN --> RPT
```

## ゲームアセット分類

| アセット種別 | アクセスパターン | FlexCache 適用 | S3 AP 利用 |
|------------|---------------|:---:|:---:|
| テクスチャ (.png, .tga, .dds) | 読み取り中心 | ✅ | ✅ 品質チェック |
| 3D モデル (.fbx, .obj, .usd) | 読み取り中心 | ✅ | ⚠️ バイナリ |
| シェーダー (.hlsl, .glsl) | 読み取り中心 | ✅ | ✅ コンパイルログ |
| ビルド成果物 (.exe, .pak) | 書き込み → 配布 | ❌ | ✅ メタデータ |
| CI ログ (.log, .json) | 書き込み → 分析 | ❌ | ✅ 分析 |
| アニメーション (.anim, .fbx) | 読み取り中心 | ✅ | ⚠️ バイナリ |

## FlexCache の役割

- メインスタジオのアセットをリモートスタジオにキャッシュ
- ビルドサーバーからの大量読み取りを高速化
- アーティストの作業環境を改善（低レイテンシ）
- S3 AP 経由でビルドパイプラインの自動化に提供

## 期待される効果

| KPI | FlexCache なし | FlexCache あり | 改善率 |
|-----|--------------|---------------|--------|
| アセット同期時間 | 30-60分 | 3-5分 | 90% |
| ビルド時間 | 45分 | 25分 | 44% |
| アーティスト待ち時間 | 5-10分/ファイル | <1分 | 80% |
| WAN 転送量/日 | 200GB | 20GB | 90% |

## ディレクトリ構成

```
gaming-build-pipeline/
├── README.md
├── template.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── quality_check/handler.py
│   ├── log_analysis/handler.py
│   └── report/handler.py
├── tests/
├── events/
│   └── sample-input.json
└── docs/
    ├── architecture.md
    ├── demo-guide.md
    └── poc-checklist.md
```

## 対象ゲームエンジン

- Unreal Engine 5
- Unity
- Godot
- カスタムエンジン

## 関連リンク

- [media-vfx/](../media-vfx/README.md) — レンダリングパイプライン
- [Dynamic FlexCache Render Workflow](../dynamic-flexcache-render-workflow/README.md)
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md)
- [業界・ワークロード マッピング](../docs/industry-workload-mapping.md)


## Success Metrics

### Outcome
ゲームアセット品質チェック・ログ分析の自動化により、ビルドパイプラインの品質管理を効率化する。

### Metrics
| メトリクス | 目標値（例） |
|-----------|------------|
| QC 処理アセット数 / 実行 | > 500 assets |
| 品質チェック通過率 | > 95% |
| ログ分析処理時間 | < 5 分 |
| ビルド品質問題の早期検出率 | > 80% |
| Human Review 対象率 | < 10%（品質不合格アセット） |

### Measurement Method
Step Functions 実行履歴、QC 結果メタデータ、ログ分析レポート、CloudWatch Metrics。




---

## AWS ドキュメントリンク

| サービス | ドキュメント |
|---------|------------|
| FSx for ONTAP | [ユーザーガイド](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points for FSx for ONTAP | [S3 AP ガイド](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Amazon Rekognition | [開発者ガイド](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon Bedrock | [ユーザーガイド](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |
| Amazon GameLift | [開発者ガイド](https://docs.aws.amazon.com/gamelift/latest/developerguide/gamelift-intro.html) |
| Step Functions | [開発者ガイド](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |

### Well-Architected Framework 対応

| 柱 | 対応 |
|----|------|
| 運用上の優秀性 | 構造化ログ、CloudWatch Metrics、ビルドログ分析 |
| セキュリティ | IAM 最小権限、KMS 暗号化、アセット保護 |
| 信頼性 | Step Functions Retry/Catch、Map state 並列処理 |
| パフォーマンス効率 | Lambda ARM64、テクスチャ品質チェック並列化 |
| コスト最適化 | サーバーレス、オンデマンド実行 |
| 持続可能性 | 不要ビルドアーティファクトの自動削除 |

### 関連 AWS ソリューション

- [AWS for Games](https://aws.amazon.com/gametech/)
- [Amazon GameLift](https://aws.amazon.com/gamelift/)
- [AWS Game Tech Blog](https://aws.amazon.com/blogs/gametech/)



---

## コスト見積もり（月額概算）

> **注記**: 以下は ap-northeast-1 リージョンの概算であり、実際のコストは使用量により異なります。最新の料金は [AWS Pricing Calculator](https://calculator.aws/) で確認してください。

### サーバーレスコンポーネント（従量課金）

| サービス | 単価 | 想定使用量 | 月額概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 4 関数 × 50 assets/日 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/日 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/日 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/実行 | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/日 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |
| Rekognition | $0.001/image |


### 固定コスト（FSx for ONTAP — 既存環境前提）

| コンポーネント | 月額 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (既存環境を共有) |
| S3 Access Point | 追加料金なし（S3 API 料金のみ） |

### 合計概算

| 構成 | 月額概算 |
|------|---------|
| 最小構成（日次 1 回実行） | ~$5-15 |
| 標準構成（時次実行） | ~$15-50 |
| 大規模構成（高頻度 + アラーム） | ~$50-150 |

> **Governance Caveat**: コスト見積もりは概算であり、保証値ではありません。実際の請求額は使用パターン、データ量、リージョンにより異なります。

---

## ローカルテスト

### Prerequisites チェック

```bash
# 前提条件の確認
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 認証情報
```

### sam local invoke

```bash
# ビルド
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build

# Discovery Lambda のローカル実行
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 環境変数オーバーライド付き
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### ユニットテスト

```bash
python3 -m pytest tests/ -v
```

詳細は [ローカルテスト クイックスタート](../docs/local-testing-quick-start.md) を参照してください。

---

## 出力サンプル (Output Sample)

ゲームビルドパイプライン品質チェックの出力例:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 30,
    "categories": {"texture": 15, "model": 8, "build_log": 7}
  },
  "texture_qc": [
    {
      "key": "builds/v2.1/textures/character_hero.dds",
      "resolution": "4096x4096",
      "format": "BC7",
      "mip_levels": 12,
      "quality_score": 0.95,
      "issues": []
    }
  ],
  "build_log_analysis": {
    "total_warnings": 23,
    "total_errors": 0,
    "critical_issues": [],
    "build_time_sec": 1847,
    "asset_count": 1234
  },
  "report": {
    "build_version": "v2.1",
    "overall_quality": "PASS",
    "textures_passed": 14,
    "textures_failed": 1,
    "recommendation": "1 texture below minimum resolution - review before release"
  }
}
```

> **注記**: 上記はサンプル出力であり、実際の値は環境・入力データにより異なります。ベンチマーク数値は sizing reference であり、service limit ではありません。

---

## Performance Considerations

- FSx for ONTAP のスループットキャパシティは NFS/SMB/S3AP で共有されます
- S3 Access Point 経由のレイテンシは数十ミリ秒のオーバーヘッドが発生します
- 大量ファイル処理時は Step Functions Map state の MaxConcurrency で並列度を制御してください
- Lambda メモリサイズの増加はネットワーク帯域幅の向上にも寄与します

> **注記**: 本パターンのパフォーマンス数値は sizing reference であり、service limit ではありません。実環境での性能は FSx for ONTAP スループットキャパシティ、ネットワーク構成、同時実行ワークロードにより異なります。

---

## デプロイ

AWS SAM CLI でデプロイします（プレースホルダは環境に合わせて置き換えてください）:

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build

sam deploy \
  --stack-name fsxn-gaming-build-pipeline \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **注意**: `template.yaml` は SAM CLI（`sam build` + `sam deploy`）で使用します。
> `aws cloudformation deploy` コマンドで直接デプロイする場合は `template-deploy.yaml` を使用してください（Lambda zip ファイルの事前パッケージングと S3 アップロードが必要です）。

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。組織は適格な専門家に相談してください。
