# FPolicy UC 別ルーティングマッピング

## 概要

FPolicy イベント駆動パイプラインでは、EventBridge カスタムバス `fsxn-fpolicy-events` に到着したイベントを、ファイルパスのプレフィックスおよび拡張子（サフィックス）に基づいて各 UC の Step Functions / Lambda にルーティングする。

## アーキテクチャ

```
FSx ONTAP → FPolicy Server (ECS Fargate) → SQS → Bridge Lambda → EventBridge Bus
                                                                         │
                                    ┌────────────────────────────────────┼────────────────────────────┐
                                    │                                    │                            │
                              UC1 Rule                             UC2 Rule                     UC17 Rule
                              (prefix/suffix)                      (prefix/suffix)              (prefix/suffix)
                                    │                                    │                            │
                              UC1 Step Functions               UC2 Step Functions          UC17 Lambda
```

## ルーティングテーブル

| UC | ディレクトリ | プレフィックスフィルタ | 拡張子フィルタ | 対象操作 | ターゲット |
|---|---|---|---|---|---|
| UC1 | legal-compliance | `/legal/`, `/compliance/`, `/audit/` | `.pdf`, `.docx`, `.xlsx` | create, write, rename, delete | ComplianceStateMachine |
| UC2 | financial-idp | `/finance/`, `/invoices/`, `/contracts/` | `.pdf`, `.tiff`, `.png`, `.jpg` | create, write | IdpStateMachine |
| UC3 | manufacturing-analytics | `/manufacturing/`, `/iot/`, `/sensors/` | `.csv`, `.json`, `.parquet` | create, write | ManufacturingStateMachine |
| UC4 | media-vfx | `/media/`, `/vfx/`, `/renders/` | `.exr`, `.dpx`, `.mov`, `.mp4` | create, write, rename | VfxStateMachine |
| UC5 | healthcare-dicom | `/healthcare/`, `/dicom/`, `/medical/` | `.dcm`, `.dicom` | create, write | DicomStateMachine |
| UC6 | insurance-claims | `/insurance/`, `/claims/` | `.pdf`, `.jpg`, `.png`, `.tiff` | create, write | InsuranceClaimsStateMachine |
| UC7 | construction-bim | `/construction/`, `/bim/`, `/cad/` | `.ifc`, `.rvt`, `.dwg`, `.nwd` | create, write, rename | ConstructionBimStateMachine |
| UC8 | genomics-pipeline | `/genomics/`, `/sequencing/` | `.fastq`, `.bam`, `.vcf`, `.fasta` | create, write | GenomicsStateMachine |
| UC9 | logistics-ocr | `/logistics/`, `/shipping/`, `/warehouse/` | `.pdf`, `.jpg`, `.png`, `.tiff` | create, write | LogisticsOcrStateMachine |
| UC10 | retail-catalog | `/retail/`, `/catalog/`, `/products/` | `.jpg`, `.png`, `.csv`, `.json` | create, write, rename | RetailCatalogStateMachine |
| UC11 | autonomous-driving | `/autonomous/`, `/lidar/`, `/camera/` | `.pcd`, `.bag`, `.mp4`, `.json` | create, write | AutonomousDrivingStateMachine |
| UC12 | semiconductor-eda | `/eda/`, `/design/`, `/simulation/` | `.gds`, `.oasis`, `.spice`, `.lib` | create, write, rename | EdaStateMachine |
| UC13 | energy-seismic | `/energy/`, `/seismic/`, `/survey/` | `.segy`, `.sgy`, `.las`, `.json` | create, write | SeismicStateMachine |
| UC14 | education-research | `/education/`, `/research/`, `/papers/` | `.pdf`, `.tex`, `.docx`, `.ipynb` | create, write, rename | EducationResearchStateMachine |
| UC15 | defense-satellite | `/defense/`, `/satellite/`, `/imagery/` | `.tiff`, `.nitf`, `.jp2`, `.geotiff` | create, write | DiscoveryFunction (Lambda) |
| UC16 | government-archives | `/government/`, `/archives/`, `/records/` | `.pdf`, `.tiff`, `.xml` | create, write, rename, delete | DiscoveryFunction (Lambda) |
| UC17 | smart-city-geospatial | `/smartcity/`, `/geospatial/`, `/gis/` | `.geojson`, `.shp`, `.tiff`, `.las` | create, write | DiscoveryFunction (Lambda) |

## EventBridge イベントスキーマ

FPolicy Bridge Lambda が EventBridge に送信するイベントの形式:

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "operation_type": "create",
    "file_path": "/legal/contracts/2026/agreement-001.pdf",
    "volume_uuid": "9ae87e42-068a-11f1-b1ff-ada95e61ee66",
    "svm_uuid": "...",
    "client_ip": "10.0.1.100",
    "user_name": "domain\\user",
    "timestamp": "2026-05-14T10:30:00Z",
    "protocol": "SMB"
  }
}
```

## フィルタリングロジック

EventBridge のコンテンツフィルタリングは **OR** ロジックで動作する:

- **プレフィックス**: `file_path` が指定プレフィックスのいずれかで始まる場合にマッチ
- **サフィックス**: `file_path` が指定サフィックスのいずれかで終わる場合にマッチ
- **操作タイプ**: `operation_type` が指定値のいずれかに一致する場合にマッチ

**重要**: EventBridge のフィルタリングでは、同一フィールド内の複数条件は OR で評価される。
つまり、プレフィックスとサフィックスの両方が指定された場合、**いずれかに一致すればルールが発火する**。

### Fan-out 動作

複数の UC ルールが同一イベントに一致した場合、EventBridge は一致した全ルールのターゲットを実行する。
例: `/manufacturing/sensors/data.json` は UC3 (manufacturing) と他の `.json` を監視する UC の両方にマッチする可能性がある。

**推奨**: プレフィックスを主フィルタ（所有権境界）として使用し、サフィックスは補助フィルタとして扱う。`.pdf`, `.json`, `.csv` のような汎用拡張子は複数 UC にまたがる fan-out を引き起こす。厳密な単一 UC ルーティングが必要な場合はプレフィックスのみに依存すること。

プレフィックスを適切に設計することで、意図しない fan-out を防止できる。

## TriggerMode との連携

| TriggerMode | EventBridge Scheduler | FPolicy EventBridge Rule |
|---|---|---|
| POLLING (デフォルト) | ✅ 有効 | ❌ 無効 (Condition: IsEventDrivenOrHybrid) |
| EVENT_DRIVEN | ❌ 無効 (Condition: IsPollingOrHybrid) | ✅ 有効 |
| HYBRID | ✅ 有効 | ✅ 有効 (Idempotency Store で重複排除) |

## カスタマイズ方法

### プレフィックス/サフィックスの変更

各 UC テンプレートの `FPolicy*Rule` リソースの `EventPattern.detail.file_path` を編集:

```yaml
EventPattern:
  detail:
    file_path:
      - prefix: "/your-custom-prefix/"
      - suffix: ".your-extension"
```

### 操作タイプの追加/削除

```yaml
EventPattern:
  detail:
    operation_type:
      - "create"
      - "write"
      # - "delete"  # 不要な場合はコメントアウト
```

## 注意事項

1. **ONTAP ボリュームのディレクトリ構造**: プレフィックスフィルタは ONTAP ボリューム内のパス構造に依存する。デプロイ前にボリュームのディレクトリ構造を確認すること。
2. **パフォーマンス**: EventBridge ルールの評価はミリ秒単位で行われるため、ルール数が増えてもレイテンシへの影響は最小限。
3. **コスト**: EventBridge カスタムバスのイベント配信は $1.00/100万イベント。ルール評価自体は無料。
4. **HYBRID モード**: 重複排除のため、Step Functions の最初のステップで Idempotency Store (DynamoDB) を参照する設計を推奨。


## Routing Drift Detection

UC 数が増えると、EventBridge ルールの重複や意図しない fan-out を人手で管理するのは困難になる。

### 推奨アプローチ

UC ルーティング定義を単一の設定ソース（`scripts/add_eventbridge_rules.py` 内の `UC_ROUTING` 辞書）に集約し、以下を自動生成する:

1. **EventBridge Rules**: CloudFormation テンプレートへの自動挿入
2. **ルーティングドキュメント**: 本ドキュメントの自動更新
3. **Overlap 検出レポート**: prefix/suffix の重複を検出
4. **put-events テストケース**: 各 UC のルーティングを検証するテストイベント
5. **Fan-out expectation テスト**: 意図的な fan-out と意図しない fan-out を区別

### Overlap 検出の例

```python
# scripts/check_routing_overlap.py (Phase 12 候補)
from itertools import combinations

for (uc1, cfg1), (uc2, cfg2) in combinations(UC_ROUTING.items(), 2):
    suffix_overlap = set(cfg1["suffixes"]) & set(cfg2["suffixes"])
    if suffix_overlap:
        print(f"  ⚠️ {uc1} ↔ {uc2}: shared suffixes {suffix_overlap}")
```

### 変更時のチェックリスト

- [ ] `scripts/add_eventbridge_rules.py` の `UC_ROUTING` を更新
- [ ] スクリプトを再実行してテンプレートを更新
- [ ] 本ドキュメントのルーティングテーブルを更新
- [ ] overlap 検出を実行して意図しない fan-out がないか確認
- [ ] `aws events put-events` でテストイベントを送信して検証
