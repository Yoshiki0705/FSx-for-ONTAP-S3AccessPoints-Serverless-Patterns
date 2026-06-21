# アーキテクチャ — Content Edge Delivery

## 設計原則

1. **FSx for ONTAP = Single Source of Truth** — 制作・管理・機微データはマスターに残す。
2. **配信は承認済み成果物のみ** — 公開配信は NFS/SMB ACL を経由しないため、配信境界は運用で担保する。
3. **CDN 非依存** — 統合メカニズムを `DeliveryMode` で切り替え、CloudFront / サードパーティ CDN を差し替え可能にする。

## データフロー

1. 制作/AI 処理パイプライン（例: media-vfx UC）が、QC 合格後の成果物を S3 AP の `delivery-approved/` に配置。
2. **Publish Lambda** が `delivery-approved/` 配下を列挙し、`DeliveryMode` に応じて処理:
   - `ORIGIN_PULL`: オリジン参照マニフェストを生成（複製なし）。
   - `PUBLISH_PUSH`: S3 互換ストアへ複製（DemoMode はスキップ記録）。
3. 配信マニフェストを `delivery-manifests/` に書き戻し。
4. CDN（CloudFront 等）が配信。視聴者トークンは CDN ネイティブ機構。
5. **Delivery Log Sync Lambda** が配信ログを正規化（IP マスク）し `delivery-log-summaries/` に書き戻し、
   制作データと突合可能にする。

## 統合メカニズムと CDN の対応

詳細は [../../docs/cdn-comparison.md](../../docs/cdn-comparison.md) を参照。要点:

- SigV4 オリジン直引き（ORIGIN_PULL）は CloudFront(OAC) で実績、Fastly/Akamai/Google で機能あり（S3 AP alias は要検証）。
- SigV4 を持たない CDN は Workers 等のエッジ署名、または PUBLISH_PUSH で対応。

## ネットワーク設計

- 配信用 Lambda は **VPC 外**（Internet-origin S3 AP へアクセス）。
- ONTAP REST API（管理 LIF）へのアクセスは本 UC では不要（配信成果物は S3 AP 経由で取得）。

## 性能・スループット設計（Storage 観点）

- FSx for ONTAP のプロビジョンドスループットは NFS/SMB/S3AP で共有される。ORIGIN_PULL のキャッシュミス時に
  CDN→S3 AP のオリジンフェッチが業務帯域と競合しうるため、キャッシュミス率と同時接続数を見積もる。
- CDN の Origin Shield / 高 TTL でオリジンフェッチを削減。大容量メディアは Range GET を活用。
- 配信読み取りを業務ボリュームから分離したい場合、**FlexCache** ボリュームを介す設計を検討（ONTAP ネイティブ）。
- PUBLISH_PUSH は初回複製後の定常配信で FSx 読み取りを発生させない。
- 定量値は構成依存のため本番見積もりは実測に基づくこと。

### サイジング / コストの注意（Storage / FinOps）

- **tail latency 重視**: オリジンフェッチのサイジングは平均ではなく **P95/P99（tail latency）** を主信号とする。
- **S3AP ≠ フル S3 バケット**: S3 AP は S3 互換の「アクセス境界」であり、S3 バケットの全機能等価ではない
  （Presigned URL 非対応等）。配信設計でバケット同等を前提にしない。
- **sample vs production**: デモ/サンプル実行のコストと本番見積もりを混同しない。本番は対象トラフィック量で
  各社最新料金により算出（[コスト試算](../../docs/cost-calculator.md) 参照）。

## 冪等性 / トリガーモード

- 本雛形は `POLLING` を主対象とする。`EVENT_DRIVEN` / `HYBRID` はパラメータ定義のみで、
  FPolicy 連携と `shared/idempotency_checker.py` による重複排除は未実装（拡張ポイント）。

## 制約（FSx for ONTAP S3 AP 由来）

- Block Public Access 強制（無効化不可）
- オリジン認証は SigV4 必須
- Presigned URL 非対応 → 視聴者トークンは CDN ネイティブ
- PutObject 上限 5 GB（大容量はマルチパート）
