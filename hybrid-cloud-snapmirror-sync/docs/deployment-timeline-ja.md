# デプロイメントタイムライン

パートナーエンジニアが End-to-End で環境を構築するための手順と所要時間。

---

## 前提条件

- [ ] AWS アカウント（CloudFormation, FSx, VPN の権限）
- [ ] オンプレミス NetApp ONTAP 9.8+ が稼働中
- [ ] オンプレミス側にパブリック IP を持つ VPN ゲートウェイ（またはルーター）
- [ ] Amazon Quick Professional/Enterprise プラン（または30日トライアル）
- [ ] デモ用 PC（Docker 実行可能）

---

## タイムライン

```
Day -7 ┃ AWS インフラ構築
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [1] SSM パラメータ作成              (5分)
       ┃ [2] CloudFormation デプロイ         (30分)  ← FSx 作成に時間がかかる
       ┃ [3] Site-to-Site VPN 構成           (1-2時間) ← トンネル UP 確認含む
       ┃
Day -5 ┃ SnapMirror 構成
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [4] Cluster Peering                 (15分)
       ┃ [5] SVM Peering                     (15分)
       ┃ [6] SnapMirror 関係作成             (10分)
       ┃ [7] SnapMirror Initialize           (数時間) ← データ量に依存
       ┃ [8] 定期スケジュール設定 (5分間隔)   (5分)
       ┃
Day -3 ┃ S3 Access Point + Amazon Quick
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [8] S3 Access Point 作成            (30分)
       ┃ [9] IAM ポリシー設定                (15分)
       ┃ [10] Amazon Quick 接続 + Index 設定 (1時間)
       ┃ [11] Quick Index 初回同期           (データ量依存)
       ┃
Day -1 ┃ Sync Server + リハーサル
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [12] Sync Server 設定(.env)        (10分)
       ┃ [13] Docker 起動 + 動作確認         (15分)
       ┃ [14] E2E テスト実行                 (15分)
       ┃ [15] リハーサル（全フロー通し）       (30分)
       ┃ [16] フォールバック確認              (15分)
       ┃
Day 0  ┃ デモ当日
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [17] 機材搬入 + ネットワーク確認    (30分)
       ┃ [18] VPN 接続確認                   (10分)
       ┃ [19] スマホ接続用ホットスポット起動  (5分)
       ┃ [20] Sync Server 起動 + ヘルスチェック (5分)
       ┃ [21] QR コード表示 + スマホ接続確認  (5分)
       ┃ [22] テスト同期実行                 (5分)
       ┃      → デモ開始
```

---

## 各ステップの詳細

### [1] SSM パラメータ作成

```bash
export FSX_ADMIN_PASSWORD='YourSecurePassword123!'
aws ssm put-parameter \
  --name "/snapmirror-demo/fsx-admin-password" \
  --type "SecureString" \
  --value "${FSX_ADMIN_PASSWORD}" \
  --region ap-northeast-1
```

### [2] CloudFormation デプロイ

```bash
./infra/deploy.sh
```

出力から以下をメモ:
- `FsxFileSystemId`
- `FsxManagementEndpoint`
- `VpcId`

### [3] VPN 構成

1. CloudFormation 出力の VPN 設定をダウンロード
2. オンプレミス VPN ゲートウェイに設定を適用
3. トンネルが UP になることを確認
4. オンプレからFSx管理LIFにping確認

### [4-7] SnapMirror 構成

```bash
# ガイドスクリプトを実行（実行すべきコマンドを表示）
./scripts/setup-snapmirror.sh
```

**所要時間の大部分は [7] Initialize**:
- 1GB データ → 数分
- 100GB データ → 数時間（VPN スループットに依存）
- デモ用途なら小さいデータセットで Initialize を早く完了させる

### [8-11] S3 AP + Amazon Quick

```bash
# ガイドスクリプトを実行
./scripts/setup-s3-access-point.sh
```

Amazon Quick 側:
1. AWS マネジメントコンソール → Amazon Quick（検索バーで「Quick」を入力）
2. Quick Index > Data sources > Add > Amazon S3
3. S3 AP エイリアスを指定
4. 同期スケジュール: On-demand（デモ用）

> ※ コンソール URL は変更される場合があります。AWS コンソールの検索バーから「Amazon Quick」で遷移してください。

### [12-16] Sync Server + リハーサル

```bash
# .env を設定
cp .env.example .env
# ONTAP_HOST = FSx の管理 DNS エンドポイント
# SNAPMIRROR_UUID = Step 7 で取得した UUID

# 起動
docker compose up -d

# E2E テスト
./scripts/e2e-test.sh
```

---

## 所要時間サマリー

| フェーズ | 作業時間 | 待ち時間 |
|---------|---------|---------|
| AWS インフラ | 1時間 | FSx 作成 30分 |
| VPN | 1-2時間 | トンネル確立待ち |
| SnapMirror | 1時間 | Initialize（データ量依存） |
| S3 AP + Quick | 2時間 | Index 同期 |
| Sync Server | 1時間 | — |
| **合計** | **~6-7時間** | **+数時間（Initialize依存）** |

**推奨**: Day -7 から着手し、余裕を持って準備。

---

## チェックリスト（Day -1 時点で全て ✅ であること）

- [ ] FSx for ONTAP が `AVAILABLE` 状態
- [ ] VPN トンネルが `UP`
- [ ] SnapMirror 関係が `snapmirrored` + `Idle`
- [ ] S3 AP 経由で ListObjects / GetObject 成功
- [ ] Amazon Quick で検索結果が返る
- [ ] Sync Server の `/api/health` が `ok` を返す
- [ ] Sync ボタンで同期 → Quick で検索 の全フロー成功
- [ ] フォールバック用デモ動画を USB に保存
- [ ] モバイルテザリングでの VPN バックアップ接続テスト済み
