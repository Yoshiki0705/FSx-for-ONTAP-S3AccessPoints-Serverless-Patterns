# コスト見積もり

デモ環境の概算コスト（東京リージョン、2026年6月時点の公開料金に基づく）。

> **注意**: 料金は変動する可能性があります。最新の正確な料金は各サービスの公式料金ページをご確認ください。

---

## Amazon Quick 料金

Amazon Quick は 4 つのプランを提供しています（[公式料金ページ](https://aws.amazon.com/quicksuite/pricing/)）:

| プラン | 月額 | 特徴 | AWS アカウント |
|--------|------|------|---------------|
| **Free** | $0 | AI チャット、リサーチ、Flows、アプリ作成、外部アプリ連携 | 不要（メール/SNS で登録） |
| **Plus** | $20/ユーザー/月 | Free + デスクトップアプリ、共有スペース、組織内ナレッジベース共有、ブラウザ拡張 | 不要 |
| **Professional** | 要問合せ | Plus + 企業ID管理、ガバナンス、Quick Sight BI | 必要 |
| **Enterprise** | $40/ユーザー/月 | 全機能 + 高度なガバナンス、監査、大規模展開 | 必要 |

### デモに必要なプラン

S3 Access Point 経由で FSx ONTAP のデータを Amazon Quick に接続するには、**Professional 以上**（AWS アカウント連携、S3 データソース接続機能）が必要です。

- Quick Sight（BI ダッシュボード機能）は Professional/Enterprise に含まれる
- Quick Index（ドキュメント検索）で S3 データソースを接続可能
- 30日間の無料トライアルあり（Plus レベル機能）

### Quick Sight 単体利用の場合

Quick Sight は Amazon Quick の一部として、以下の料金体系も存在します:

| タイプ | 月額 |
|--------|------|
| Reader（閲覧のみ） | $3〜/ユーザー/月（セッション課金も可） |
| Author（作成） | $24/ユーザー/月 |
| Admin | $24/ユーザー/月 |

※ Enterprise プランの既存 Quick Sight ユーザーは追加コストなしで Quick 全機能にアップグレード可能

---

## FSx for NetApp ONTAP 料金

| 項目 | 単価（東京リージョン概算） | デモ構成 | 月額概算 |
|------|--------------------------|---------|---------|
| SSD ストレージ | ~$0.120/GiB-月 | 1,024 GiB | ~$123 |
| スループットキャパシティ | ~$1.536/MBps-月 (Single-AZ) | 128 MBps | ~$197 |
| SSD IOPS（プロビジョニング超過分） | ~$0.036/IOPS-月 | 基本含まれる | $0 |
| キャパシティプール | ~$0.021/GiB-月 | 未使用時 | $0 |
| バックアップ | ~$0.025/GiB-月 | オプション | - |

**FSx ONTAP 月額概算: ~$320/月**（Single-AZ, 1TB, 128MBps）

> ※ デモ期間のみ利用する場合、使用日数で按分（時間課金）

---

## VPN 料金（Site-to-Site VPN）

| 項目 | 単価 | 月額概算 |
|------|------|---------|
| VPN 接続 | ~$0.048/時間 | ~$35/月 |
| データ転送（OUT） | ~$0.114/GB | デモ規模なら数ドル |

**VPN 月額概算: ~$37/月**

---

## デモ全体のコスト概算

### 最小構成（デモ期間1週間の場合）

| コンポーネント | 概算 |
|---------------|------|
| FSx for ONTAP (1週間) | ~$80 |
| VPN (1週間) | ~$9 |
| Amazon Quick (Professional, 1ユーザー, トライアル) | $0（30日無料トライアル） |
| Sync Server (ローカル PC 実行) | $0 |
| **合計** | **~$89** |

### フル構成（1ヶ月運用）

| コンポーネント | 月額概算 |
|---------------|---------|
| FSx for ONTAP | ~$320 |
| VPN | ~$37 |
| Amazon Quick (Professional, 2ユーザー) | ~$80（推定） |
| データ転送 | ~$5 |
| **合計** | **~$442/月** |

---

## コスト最適化のポイント

1. **デモ期間のみ FSx を起動**: CloudFormation で作成/削除を繰り返す
2. **Single-AZ を使用**: デモ用途なら HA 不要で約 50% コスト削減
3. **最小スループット (128 MBps)**: デモデータ量なら十分
4. **Amazon Quick 無料トライアル**: 30日間は Plus 機能が無料
5. **VPN の代替**: イベント会場では AWS Client VPN や WireGuard でも代替可能

---

## 参考リンク

- [Amazon Quick 料金](https://aws.amazon.com/quicksuite/pricing/)
- [Amazon Quick Sight 料金](https://aws.amazon.com/quick/quicksight/pricing/)
- [FSx for NetApp ONTAP 料金](https://aws.amazon.com/fsx/netapp-ontap/pricing/)
- [AWS VPN 料金](https://aws.amazon.com/vpn/pricing/)
