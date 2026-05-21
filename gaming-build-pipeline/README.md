# Gaming Build Pipeline — ゲームアセット共有・ビルドパイプライン

🌐 **Language / 言語**: [日本語](README.md)

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
        ORIGIN[FSx ONTAP<br/>Game Assets<br/>Build Artifacts]
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
