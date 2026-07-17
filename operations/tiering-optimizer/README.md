# OPS3: Tiering Optimizer — FabricPool ティアリング最適化

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

---

## 概要

FSx for ONTAP のボリュームティアリングポリシーを分析し、コールドデータの
Capacity Pool ティアへの最適な階層化を推奨するパターン。
ポリシー変更によるコスト削減額を事前に試算します。

**参考リンク**:
- [Volume data tiering (AWS Docs)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-data-tiering.html)
- [Best practices for enterprise deployments](https://docs.aws.amazon.com/prescriptive-guidance/latest/fsx-ontap-enterprise-deployment/best-practices.html)
- [How a customer reduced storage TCO by 28%](https://aws.amazon.com/blogs/storage/how-a-customer-reduced-storage-tco-by-28-with-amazon-fsx-for-netapp-ontap/)

---

## 推奨ロジック

| 現在のポリシー | 条件 | 推奨 |
|:-------------:|------|------|
| `none` | — | `auto` (31日クーリング) に変更 |
| `snapshot-only` | Capacity Pool > 50 GB | `auto` にアップグレード |
| `auto` | cooling > 14日 & Pool > 100 GB | cooling を 14日に短縮 |
| `all` | — | 推奨なし (既に最大階層化) |

---

## コスト試算

| ティア | 単価 (ap-northeast-1) | 備考 |
|-------|:---------------------:|------|
| SSD | ~$0.125/GB/月 | プライマリ |
| Capacity Pool | ~$0.021/GB/月 | コールドデータ |
| **差額** | **~$0.104/GB/月** | SSD → Pool 移行時の節約 |

---

## テスト

```bash
python3 -m pytest operations/tiering-optimizer/tests/ -v
make test-ops3
```

## Governance Note

ティアリングポリシーの変更は可逆的ですが、policy=all への変更は
全ユーザデータを Capacity Pool に移動するため、読み取りレイテンシが
数十ミリ秒に増加します。本番ワークロードへの適用前にテスト環境で検証してください。
