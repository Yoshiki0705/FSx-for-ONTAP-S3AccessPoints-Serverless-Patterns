# パートナー引き渡しガイド

## 引き渡し物一覧

| # | 成果物 | 内容 |
|---|--------|------|
| 1 | ソースコード一式 | このリポジトリ全体 |
| 2 | デモモード | ONTAP 接続なしで即座に UI 動作確認可能 |
| 3 | CloudFormation テンプレート | AWS インフラをワンコマンドで構築 |
| 4 | セットアップスクリプト | SnapMirror / S3 AP の構成手順を生成 |
| 5 | 運用ガイド | デモ当日の操作手順 + フォールバック計画 |
| 6 | コスト見積もり | AWS 月額 / 週額の概算 |
| 7 | デプロイメントタイムライン | Day -7 から Day 0 までの作業計画 |
| 8 | ネットワーク代替方式 | 会場で VPN が使えない場合の接続方法 |

---

## すぐに動かしてみる（5分）

ONTAP 環境がなくても UI の動きを確認できます:

```bash
# 1. リポジトリを取得
git clone <repository-url>
cd snapmirror-one-click-sync

# 2. デモモードで起動
cp .env.example .env
# .env を編集: DEMO_MODE=true に変更

# 3. Docker で起動
docker compose up -d

# 4. ブラウザでアクセス
open http://localhost:8080
```

→ オレンジのボタンを押すと、5-12 秒の模擬同期が実行されます。

---

## 本番構成に切り替える

デモモードで動作確認ができたら、本番構成へ切り替えます:

1. [docs/deployment-timeline-ja.md](deployment-timeline-ja.md) のタイムラインに従う
2. `DEMO_MODE=false` に変更
3. `ONTAP_HOST`, `SNAPMIRROR_UUID` を実環境の値に設定
4. E2E テスト実行: `./scripts/e2e-test.sh`

---

## ドキュメント一覧

| ドキュメント | 対象者 | 内容 |
|-------------|--------|------|
| [README.md](../README.md) | 全員 | プロジェクト概要 |
| [setup-guide-ja.md](setup-guide-ja.md) | エンジニア | 環境構築手順 |
| [deployment-timeline-ja.md](deployment-timeline-ja.md) | PM/エンジニア | 作業計画 |
| [architecture.md](architecture.md) | エンジニア | 技術アーキテクチャ |
| [operation-guide-ja.md](operation-guide-ja.md) | デモ担当者 | 当日の操作手順 |
| [network-alternatives-ja.md](network-alternatives-ja.md) | ネットワーク担当 | VPN 代替方式 |
| [cost-estimate-ja.md](cost-estimate-ja.md) | PM | コスト概算 |

---

## よくある質問

### Q: デモ当日に必要な機材は？

- オンプレミス NetApp ONTAP（搬入済み）
- Sync Server 用 PC（Docker 実行可能、macOS/Windows/Linux）
- **モバイルホットスポット用のネットワーク接続**（PC のモバイル回線 or 会場 WiFi）
- AWS VPN 接続手段（Client VPN 推奨）
- スマートフォン（操作デモ用 — PC のホットスポットに接続）
- （オプション）ポータブル WiFi ルーター
- （オプション）QR コードを印刷した紙、または PC で QR を表示

### Q: 来場者に見せる画面は？

1. **Sync Server の画面**（スマートフォンまたは PC のブラウザ）— ワンクリック同期
2. **Amazon Quick の画面**（PC ブラウザ）— 同期されたデータの検索・分析

### Q: ONTAP 側の準備は？

- CIFS/NFS 共有フォルダを用意（来場者がファイルを保存できるように）
- デモ用テンプレートファイルを事前配置推奨
- SnapMirror 関係が Idle 状態であることを確認

### Q: デモが失敗したら？

[operation-guide-ja.md](operation-guide-ja.md) のフォールバックプランを参照。
最終手段として事前録画のデモ動画を USB に準備しておいてください。

### Q: 問題が発生した場合の連絡先は？

GitHub Issues に報告してください。

---

## デモ成功のチェックリスト

### Day -7
- [ ] AWS CloudFormation デプロイ完了
- [ ] VPN 接続確認

### Day -5
- [ ] SnapMirror Initialize 完了
- [ ] S3 Access Point 構成完了

### Day -3
- [ ] Amazon Quick 接続完了
- [ ] Quick で検索結果が返ることを確認

### Day -1
- [ ] Sync Server 起動確認
- [ ] E2E テスト成功
- [ ] 全フロー通しリハーサル完了
- [ ] フォールバック確認（デモ動画 USB 準備）
- [ ] バックアップ VPN 接続テスト

### Day 0（当日）
- [ ] 機材搬入完了
- [ ] ネットワーク接続確認
- [ ] VPN UP 確認
- [ ] テスト同期 1 回実行
- [ ] デモ開始 🎉
