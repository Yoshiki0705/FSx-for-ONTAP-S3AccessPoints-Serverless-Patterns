# アーキテクチャ

## 全体構成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  デモ会場 (オンプレミス環境)                                                    │
│                                                                             │
│  ┌──────────┐     HTTP      ┌──────────────┐                  ┌────────┐    │
│  │ スマホ/PC │ ───────────▶  │  Sync Server │                  │ ONTAP  │    │
│  │(ブラウザ) │               │  (Python)    │                  │ (SRC)  │    │
│  └──────────┘               └──────┬───────┘                  └───┬────┘    │
│       ▲                            │                              │         │
│       │ 進捗のポーリング              │ ONTAP REST API               │         │
│       └────────────────────────────┘ (HTTPS/443)                  │         │
│                                      │                            │ 　      │
└──────────────────────────────────────│────────────────────────────│─────────┘
                                       │ VPN Tunnel                 │ SnapMirror
                                       ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS Cloud (ap-northeast-1)                                                 │
│                                                                             │
│  ┌──────────────────┐    S3 Access Point    ┌───────────────────────────┐   │
│  │ FSx for ONTAP    │ ──────────────────▶   │ Amazon Quick              │   │
│  │ (DST)            │                       │ (AI検索・分析・活用)         │   │
│  │ ← REST API here  │                       └───────────────────────────┘   │
│  └──────────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**重要**: Sync Server は FSx for ONTAP（Destination 側）の REST API を呼び出します。
SnapMirror XDP 関係は Destination クラスタが所有するため、転送トリガーは FSx 側に発行する必要があります。
Sync Server → FSx 間は VPN トンネル経由で通信します。

## コンポーネント詳細

### 1. フロントエンド (ブラウザ)

- **技術**: 静的 HTML + CSS + JavaScript（フレームワーク不要）
- **レスポンシブ**: スマートフォン、タブレット、PC すべてに対応
- **通信**: REST API ポーリング (1.5〜3秒間隔)
- **安全機構**: ボタン即時無効化 + サーバー側ロック

### 2. Sync Server (バックエンド)

- **技術**: Python FastAPI
- **役割**:
  - フロントエンド配信 (静的ファイル)
  - ONTAP REST API プロキシ
  - 同期状態管理（二重実行防止）
  - 転送進捗監視
- **デプロイ**: Docker または直接実行

### 3. ONTAP REST API

Sync Server は **FSx for ONTAP（Destination クラスタ）** の REST API を呼び出す。
SnapMirror XDP 関係は Destination 側が所有するため。

使用するエンドポイント:

| API | メソッド | 用途 |
|-----|--------|------|
| `/api/snapmirror/relationships/{uuid}` | GET | 関係のステータス取得 |
| `/api/snapmirror/relationships/{uuid}/transfers` | GET | 転送履歴取得 |
| `/api/snapmirror/relationships/{uuid}/transfers` | POST | 転送トリガー |

**接続先**: FSx for ONTAP の管理 DNS エンドポイント（`management.fs-xxx.fsx.ap-northeast-1.amazonaws.com`）
**経路**: Sync Server → VPN Tunnel → FSx Management LIF

### 4. SnapMirror

- **方向**: オンプレミス ONTAP (Source) → FSx for NetApp ONTAP (Destination)
- **種類**: Asynchronous SnapMirror (XDP)
- **定期スケジュール**: 5分毎に自動で増分転送（ONTAP の `job schedule` で制御）
- **ワンクリック割り込み**: このツールから `POST /transfers` で即時追加転送
- **転送内容**: ブロックレベルの差分のみ（変更されたブロックだけを効率的に転送）

```
┌────────────────────────────────────────────────┐
│  SnapMirror 転送トリガー                         │
│                                                │
│  [定期スケジュール]──5分毎──▶ snapmirror update   │
│         +                                      │
│  [ワンクリック]──即時──▶ snapmirror update       │
│                          (= POST /transfers)   │
│                                                │
│  → 両方ともブロックレベル差分のみ転送                │
│  → 定期実行中に割り込みが来ると 409 で待機           │
└────────────────────────────────────────────────┘
```

スケジュール設定の詳細は [docs/snapmirror-schedule-ja.md](../docs/snapmirror-schedule-ja.md) を参照。

### 5. FSx for NetApp ONTAP

- **役割**: AWS クラウド側のデータストア
- **接続**: S3 Access Points による読み取りアクセスを提供

### 6. Amazon Quick

- **役割**: FSx for ONTAP 上のデータを AI エージェント・BI・検索で活用
- **機能**: Quick Sight（可視化・ダッシュボード）、Quick Index（ドキュメント検索）、Quick Research（AI リサーチ）
- **データソース**: S3 Access Points for FSx for NetApp ONTAP 経由でエンタープライズファイルデータに接続

> **検証が必要な想定**: Amazon Quick の Quick Index が FSx ONTAP の S3 Access Point を
> データソースとして直接サポートしているかは、デプロイ時に検証が必要です。
> 通常の S3 バケットと異なり、FSx ONTAP の S3 AP には `GetBucketLocation` 挙動の差異や
> ページネーション特性の違いがある場合があります。
> Day -3 の構成時に接続テストを行い、問題がある場合は Quick Sight のみでのデモ
> （S3 AP 経由のファイル内容を Lambda で整形 → S3 → Quick Sight で可視化）を Plan B とします。

## 二重実行防止メカニズム

```
[ユーザークリック]
       │
       ▼
┌─────────────────┐
│ フロントエンド     │ ① ボタンを即座に disabled に変更
│ (即時無効化)      │
└────────┬────────┘
         │ POST /api/sync
         ▼
┌─────────────────┐
│ バックエンド      │  ② asyncio.Lock で排他制御
│ (ロック確認)      │    → _is_running == True なら 409 返却
└────────┬────────┘
         │ 転送トリガー
         ▼
┌─────────────────┐
│ ONTAP REST API  │  ③ ONTAP 側でも同時転送を拒否 (409)
│ (サーバー側制御)   │
└─────────────────┘
```

3層の防御により、いかなる状況でも二重実行が発生しない設計。

## 状態遷移図

```
         ┌──────────┐
    ┌──▶ │  READY   │ ◀─────────────────┐
    │    └────┬─────┘                   │
    │         │ (ボタンクリック)          │
    │         ▼                         │
    │    ┌──────────┐                   │
    │    │ STARTING │                   │
    │    └────┬─────┘                   │
    │         │ (トリガー成功)            │
    │         ▼                         │
    │    ┌──────────┐                   │
    │    │ SYNCING  │ ← ポーリング監視    │
    │    └────┬─────┘                   │
    │         │                         │
    │    ┌────┴────┐                    │
    │    ▼         ▼                    │
    │ ┌──────┐  ┌───────┐               │
    │ │ DONE │  │ ERROR │               │
    │ └──┬───┘  └──┬────┘               │
    │    │         │                    │
    │    └─────────┴────────────────────┘
    │         (10秒後 or リトライ)
    └───────────────────────────────────
```

## ネットワーク要件

- Sync Server は ONTAP 管理 LIF に HTTPS (TCP 443) でアクセス可能であること
- クライアントデバイスは Sync Server に HTTP (TCP 8080) でアクセス可能であること
- 同一 LAN / WiFi ネットワーク内での利用を想定

## セキュリティ考慮事項

| リスク | 対策 |
|--------|------|
| ONTAP 認証情報の漏洩 | `.env` で管理、Docker volume でマウント |
| 不正な同期トリガー | デモ環境限定、信頼できるネットワーク内のみ |
| 中間者攻撃 | ONTAP 側は HTTPS（自己署名証明書許容） |
| サーバーダウン | Docker restart policy + ヘルスチェック |

本番環境で利用する場合は、認証・認可機構の追加が必要です。
