# SnapMirror スケジュールと同期間隔の設計

[日本語](snapmirror-schedule-ja.md) | [English](snapmirror-schedule-en.md)

## このツールの位置づけ

SnapMirror には2つの転送トリガーがあります:

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ① 定期スケジュール（自動）                                       │
│     ONTAP が設定間隔で自動的に snapmirror update を実行           │
│     → バックグラウンドで継続的にデータを同期                       │
│                                                                  │
│  ② 手動トリガー（このツール = 割り込み実行）                       │
│     POST /api/snapmirror/relationships/{uuid}/transfers          │
│     = CLI の snapmirror update -destination-path <svm:vol>       │
│     → 「今すぐ」追加で1回増分転送を実行                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**両方を組み合わせて使います**:
- 定期スケジュール = ベースライン保護（デモ中もデータを定期的に同期し続ける）
- ワンクリック = 「来場者がファイルを保存した直後に、今すぐ同期」する割り込み

---

## SnapMirror ポリシーとスケジュールの設定

### Step 1: スケジュールの確認・作成

```bash
# FSx ONTAP CLI に SSH 接続
ssh fsxadmin@<FSx_Management_DNS>

# 既存のスケジュールを確認
job schedule show

# デモ用に 5 分間隔のスケジュールを作成（存在しない場合）
job schedule cron create -name 5min -minute 0,5,10,15,20,25,30,35,40,45,50,55
```

**よく使われるスケジュール例**:

| スケジュール名 | 間隔 | 用途 |
|--------------|------|------|
| `5min` | 5分 | デモ向け — データ変更を高頻度で反映 |
| `15min` | 15分 | 一般的な PoC/検証 |
| `hourly` | 1時間 | ビルトインスケジュール |
| `daily` | 1日 | バックアップ目的 |

### Step 2: SnapMirror ポリシーにスケジュールを付与

```bash
# 方法 A: SnapMirror 関係にスケジュールを直接設定（推奨）
snapmirror modify -destination-path svm_demo:vol_demo -schedule 5min

# 方法 B: カスタムポリシーを作成してスケジュールを含める
snapmirror policy create -policy demo-sync-policy \
  -type async-mirror \
  -transfer-schedule 5min

# ポリシーを関係に適用
snapmirror modify -destination-path svm_demo:vol_demo -policy demo-sync-policy
```

### Step 3: 動作確認

```bash
# スケジュールが適用されていることを確認
snapmirror show -destination-path svm_demo:vol_demo -fields schedule,policy

# 期待される出力:
#                          Schedule  Policy
# svm_demo:vol_demo        5min      MirrorAllSnapshots (or demo-sync-policy)
```

### REST API でスケジュールを設定する場合

```bash
# PATCH でスケジュールを追加
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"policy": {"name": "MirrorAllSnapshots"}, "transfer_schedule": {"name": "5min"}}'
```

---

## 定期実行とワンクリック割り込みの関係

```
時間軸 →
──┬────────┬────────┬────────┬────────┬──
  │        │        │        │        │
  ▼        ▼        ▼        ▼        ▼    ← 5分毎の定期 update（自動）
  
     ▲              ▲                      ← ワンクリック割り込み（手動）
     │              │
  来場者が        別の来場者が
  ファイル保存    ファイル保存
```

### 各パターンの挙動

| 状況 | 挙動 |
|------|------|
| 定期スケジュール間にワンクリック | 即座に増分転送を開始（次の定期を待たない） |
| 定期転送中にワンクリック | ONTAP が HTTP 409 → UI に「既に実行中」表示 |
| ワンクリック転送中に定期スケジュールが到来 | 定期はキューに入る or スキップ（ONTAP が制御） |
| 定期完了直後にワンクリック | 差分がない場合は瞬時に完了（転送データ 0 bytes） |

### デモシナリオでの典型的な流れ

```
1. [定期 5min] ONTAP が自動 update → 差分なし → 即完了
2. 来場者がファイルを共有フォルダに保存
3. [ワンクリック] 担当者がボタンを押す → 差分転送（数秒）→ 完了
4. Amazon Quick で検索 → ファイルが見つかる！
5. [定期 5min] ONTAP が自動 update → 差分なし → 即完了
```

---

## 同期間隔のチューニング

### デモ用途の推奨設定

| パラメータ | 推奨値 | 理由 |
|-----------|--------|------|
| SnapMirror スケジュール | **5分** | デモ中にワンクリックを忘れても 5 分以内にデータが反映される |
| ワンクリックのタイムアウト | **600秒（10分）** | 通常は数秒だが、大きなファイルに対応 |
| ポーリング間隔 | **2秒** | 素早い UI 応答 |

### スケジュール間隔を短くする場合の注意

| 間隔 | メリット | デメリット |
|------|---------|-----------|
| 1分 | Near real-time（注: FSx for ONTAP の最短サポート間隔は5分） | ONTAP 負荷増、ログ大量 | 
| 5分 | FSx for ONTAP 推奨最短間隔（near real-time） | ワンクリックなしでも 5 分で同期 |
| 15分 | ONTAP 負荷最小 | ワンクリックがほぼ必須になる |

**デモには 5 分を推奨**。「定期でも同期されるが、ワンクリックで今すぐ」という使い分けを見せるのに最適。

### スループットへの影響

```
FSx スループットキャパシティ（例: 128 MBps）
  = NFS/SMB + S3 AP + SnapMirror の合計

定期 SnapMirror update:
  - 差分なし → 数秒で完了、スループット消費ほぼゼロ
  - 差分あり（数MB） → 数秒間だけ転送、影響軽微

ワンクリック update:
  - 同上（差分のみ転送）

SnapMirror Initialize（初回同期）:
  - 全データ転送 → スループットを大量消費
  → Initialize は事前に完了させておくこと！
```

---

## SnapMirror スケジュールの変更方法

### デモ中にデータ鮮度を上げたい場合

```bash
# 1分間隔に変更
job schedule cron create -name 1min -minute */1
snapmirror modify -destination-path svm_demo:vol_demo -schedule 1min
```

### デモ終了後に通常間隔に戻す

```bash
# 1時間に戻す
snapmirror modify -destination-path svm_demo:vol_demo -schedule hourly
```

### REST API でスケジュールを変更

```bash
# 5分間隔に設定
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"transfer_schedule": {"name": "5min"}}'

# スケジュールを無効化（ワンクリックのみにする）
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"transfer_schedule": {"name": ""}}'
```

---

## トラブルシューティング

### 「差分なし」で同期が瞬時に完了してしまう

**原因**: SnapMirror はブロックレベルの差分検出。ファイルの保存（write → close）が完了するまで差分として認識されない。

**対策**:
- ファイルを保存（close）してからボタンを押すよう案内
- Excel / Word は「保存」ボタンを明示的に押してもらう

### 定期スケジュールが実行されない

```bash
# スケジュールが正しく設定されているか確認
snapmirror show -fields schedule
job schedule show -name 5min

# 最後の転送時刻を確認
snapmirror show -fields last-transfer-end-timestamp
```

### SnapMirror 関係が `quiesced` 状態になった

```bash
# quiesce 状態を解除
snapmirror resume -destination-path svm_demo:vol_demo
```

---

## まとめ: デモ当日の設定

```bash
# 1. スケジュール確認（5min が設定済みであること）
snapmirror show -destination-path svm_demo:vol_demo -fields schedule

# 2. 関係が Idle であること
snapmirror show -destination-path svm_demo:vol_demo -fields status

# 3. ワンクリックツールが正常であること
curl -s http://<Sync_Server>:8080/api/health

# 4. テスト実行
curl -s -X POST http://<Sync_Server>:8080/api/sync
```

**ポイント**: 定期スケジュール（5分）はバックグラウンドで継続的にデータを保護し、ワンクリックは「来場者がファイルを保存した直後の near real-time 同期」を演出するためのものです。SnapMirror on FSx for ONTAP は volume-level の非同期レプリケーションであり、Synchronous SnapMirror や SVMDR はサポートされていません。
