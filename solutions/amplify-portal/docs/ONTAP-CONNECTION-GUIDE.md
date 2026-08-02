# ONTAP REST API 接続ガイド — File Portal

> ファイルポータルと FSx for ONTAP の接続アーキテクチャ、トラブルシューティング、およびデプロイ時の重要な注意事項。

## 接続アーキテクチャ

```
┌──────────────────────────────────────────────────────────────────┐
│ Amplify Gen2 Backend (CDK)                                        │
│                                                                    │
│  AppSync → Lambda (VPC 内) → ONTAP REST API (HTTPS/443)          │
│                 │                    │                              │
│                 │                    ├── https://<mgmt-ip>/api/...  │
│                 │                    │   (Basic Auth: fsxadmin)     │
│                 │                    │                              │
│                 ├── Secrets Manager ─┘                              │
│                 │   (fsxadmin credentials)                         │
│                 │                                                    │
│                 └── VPC Endpoint (Secrets Manager)                  │
│                     VPC Endpoint (S3 Gateway)                      │
└──────────────────────────────────────────────────────────────────┘
```

### 接続先の違い（ファイルシステム vs SVM）

| エンドポイント | 接続先 | ユーザー | 用途 |
|-------------|--------|---------|------|
| **ファイルシステム管理 IP** | クラスタースコープ | `fsxadmin` | FlexCache, SnapMirror, Volume, QoS, Export Policy, Snapshot Policy |
| SVM 管理 LIF | SVM スコープ | `vsadmin` | SVM 内の操作のみ（制限あり） |

**重要**: 本ポータルは**ファイルシステム管理 IP** を使用します。FlexCache や SnapMirror はクラスタースコープの操作であり、SVM 管理 LIF ではアクセスできません（HTTP 401 になります）。

### IP アドレスの確認方法

```bash
# ファイルシステム管理 IP（本ポータルが使用）
aws fsx describe-file-systems --file-system-ids <fs-id> \
  --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]" \
  --output text

# SVM 管理 LIF IP（本ポータルでは使用しない）
aws fsx describe-storage-virtual-machines \
  --filters "Name=file-system-id,Values=<fs-id>" \
  --query "StorageVirtualMachines[0].Endpoints.Management.IpAddresses[0]" \
  --output text
```

## Secrets Manager の管理

### シークレット形式

```json
{
  "username": "fsxadmin",
  "password": "<fsxadmin-password>"
}
```

### シークレット作成

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_SECURE_PASSWORD"}' \
  --region <your-region>
```

> **Security note**: Secrets Manager はデフォルトで AWS マネージド KMS キー (`aws/secretsmanager`) による暗号化が有効です。規制要件（FISC, PCI DSS, HIPAA 等）でカスタマーマネージドキー（CMK）が必要な場合は `--kms-key-id` を指定してください。自動ローテーションを有効化する場合は [AWS ドキュメント: Rotate secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html) を参照。

### パスワード変更手順

FSx for ONTAP の `fsxadmin` パスワードを変更する場合、**必ず両方を同時に更新**してください:

```bash
# Step 1: FSx for ONTAP 側のパスワード変更
aws fsx update-file-system \
  --file-system-id <fs-id> \
  --ontap-configuration '{"FsxAdminPassword":"NewSecureP@ss2026!"}' \
  --region <your-region>

# Step 2: Secrets Manager の値を同期
aws secretsmanager put-secret-value \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"NewSecureP@ss2026!"}' \
  --region <your-region>
```

> **注意**: Step 1 と Step 2 の間にポータルが API 呼び出しを行うと、古いパスワードで認証失敗します。ONTAP は認証失敗を記録し、一定回数超過でアカウントをロックアウトする場合があります。

## トラブルシューティング

### HTTP 401 "User is not authorized"

| 原因 | 確認方法 | 対処 |
|------|---------|------|
| パスワード不一致 | Secrets Manager の値と FSx の実パスワードが異なる | 上記「パスワード変更手順」で両方を同期 |
| アカウントロックアウト | 多数の認証失敗（自動化テスト等）で閾値超過 | `aws fsx update-file-system` でパスワードリセット → ロック解除 |
| 接続先 IP 間違い | SVM 管理 LIF に `fsxadmin` で接続 | `describe-file-systems` でファイルシステム管理 IP を確認 |
| VPC 接続不可 | Lambda が ONTAP IP に到達できない | Security Group のoutbound TCP/443 と subnet routing を確認 |

### CloudWatch ログでの確認

```bash
# Lambda ログでONTAP API エラーを検索
aws logs filter-log-events \
  --log-group-name "/aws/lambda/<ResourceMgmtFunction名>" \
  --start-time $(( $(date +%s) - 300 ))000 \
  --region <your-region> \
  --query 'events[*].message' --output text \
  | grep -i "ONTAP API error\|401\|flexcache\|snapmirror"
```

### Lambda タイムアウト (120s 超過)

FlexCache 作成や SnapMirror 初期化は ONTAP 側で非同期ジョブとして実行されます。`return_timeout=0` パラメータにより ONTAP は即座に 202 Accepted + job UUID を返しますが、ONTAP への初回接続（TLS handshake + Basic Auth）に 4-5 秒かかります。

Lambda タイムアウト: 120 秒（`backend.ts` で設定）。通常の API 呼び出しは 4-8 秒で完了します。

## FlexCache 操作の注意点

### FSx for ONTAP 固有の仕様

- **Aggregate 指定不要**: FSx for ONTAP は単一の自動管理 aggregate を使用するため、`aggregate_name` パラメータは省略可能です（ONTAP REST API がデフォルト aggregate を自動選択）。オンプレ ONTAP では明示指定が必要な場合があります。
- **SVM 作成は AWS API のみ**: ONTAP CLI/REST では SVM 作成不可。`aws fsx create-storage-virtual-machine` を使用。
- **FlexCache は同一クラスター内でも作成可能**: クラスターピアリングなしで同一 FS の別ボリュームをオリジンに指定できます。

### 作成

```
POST /storage/flexcache/flexcaches?return_timeout=0
```

- `return_timeout=0` を指定しないと、ONTAP が同期的に完了を待機（30-120秒かかり Lambda タイムアウトの原因に）
- 作成は非同期ジョブ。完了まで 30 秒〜数分。ポータルは 10s/30s/60s の間隔でリスト自動更新

### 削除（3 ステップ必須）

FlexCache ボリュームがマウント中の場合、直接削除はできません:

```
1. PATCH /storage/volumes/{uuid} → {"nas": {"path": ""}}      // unmount
2. PATCH /storage/volumes/{uuid} → {"state": "offline"}       // offline
3. DELETE /storage/flexcache/flexcaches/{uuid}?return_timeout=0  // delete
```

ポータルの `_delete_flexcache` はこの3ステップを自動化しています。

## SnapMirror 操作の注意点

### 状態遷移

| 状態 | 意味 | 許可される操作 |
|------|------|---------------|
| `snapmirrored` | 正常同期中 | sync, break, quiesce |
| `broken_off` | DP ボリュームが読み書き可能 | resync |
| `transferring` | データ転送中 | abort |
| `quiesced` | 同期一時停止 | resume, break |

### 初期化（既存リレーションシップ）

SnapMirror リレーションシップの作成は通常 `volume create -type DP` → `snapmirror create` → `snapmirror initialize` の手順ですが、本ポータルでは**既存リレーションシップの管理**に特化しています（FSx Console または CLI で初期作成）。

## Amplify Sandbox の挙動

### ファイル変更検知の範囲

| ディレクトリ | 変更検知 | Lambda コード更新 |
|------------|:--------:|:--------------:|
| `amplify/` | ✅ 自動 | `backend.ts` 変更時にバンドル再生成 |
| `functions/` | ⚠️ 間接的 | `amplify/` 内のファイルが変更されて初めて再バンドル |
| `src/` (frontend) | ✅ Vite HMR | Lambda には影響なし |

**重要**: `functions/resource-management/handler.py` を変更した場合、sandbox が自動検知しない場合があります。以下のいずれかで強制トリガー:
1. `backend.ts` の Lambda `description` を変更（アセットハッシュが変わるため）
2. sandbox を Ctrl+C → 再起動

### `authMode: "userPool"` の必要性

Amplify Gen2 で複数の認証プロバイダー（Cognito User Pools + IAM）が設定されている場合、`generateClient<Schema>()` に `authMode` を明示指定しないと、Cognito ID Token が AppSync に送信されず「User is not authorized」エラーになります。

```typescript
// ❌ 動作しない（authMode 未指定）
const client = generateClient<Schema>();

// ✅ 正しい（Cognito token を確実に送信）
const client = generateClient<Schema>({ authMode: "userPool" });
```

## 新規環境へのデプロイ手順（一気通貫）

```bash
# 1. リポジトリ取得
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. 依存関係
npm install

# 3. 設定ファイル（FSx for ONTAP の情報を自動取得）
./scripts/setup-prerequisites.sh --fs-id <your-fs-id>
cp amplify/portal-config.example.ts amplify/portal-config.ts
# 出力された値を portal-config.ts に転記

# 4. Secrets Manager にクレデンシャル登録
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-password>"}'

# 5. 起動
npm start

# 6. 初回ユーザー作成（自動で Cognito サインアップ画面が表示される）
# ブラウザで http://localhost:5173 → Create Account
```

## 他の SaaS ツールとの併用パターン

| 利用シーン | 併用アプローチ | ポータルの役割 |
|-----------|-------------|-------------|
| クラウドファイル共有 SaaS を利用中 | 日常のファイル共有は SaaS で継続 | NAS 上の大規模データ（EDA, 映像, HPC 結果）への AI 処理・監査 |
| セルフホスト型ファイル共有を運用中 | External Storage で S3 AP を追加するだけ | 既存 UI から NAS データを直接ブラウズ + ポータルで管理操作 |
| グループウェア（M365 等）を利用中 | グループウェア連携はそのまま | オンプレ NAS ↔ FSx for ONTAP の SnapMirror レプリケーション管理 |
| ハイブリッドファイルサービスを利用中 | ファイルサービスは継続利用 | データ保護（Tamperproof Snapshot）とランサムウェア対策（ARP/AI）の可視化 |

**設計思想**: 本ポータルは既存ファイル共有ツールの「置き換え」ではなく、NAS データへの **AI 処理 + データ保護可視化 + 管理操作** のレイヤーです。日常のファイル共有は既存ツールで続けつつ、NAS 固有の機能（Snapshot, FlexClone, FlexCache, SnapMirror, ARP）をブラウザから操作可能にします。


## 将来の改善計画 (Future Improvements)

以下は 20 ペルソナレビューで特定された改善項目です:

### パフォーマンス可視化
- **キャッシュヒット率表示** (EDA/VFX ペルソナ): ONTAP REST API の `cache_hit_ratio` フィールドを使用してリアルタイムのヒット率をダッシュボード表示
- **スループット/IOPS グラフ**: CloudWatch メトリクス or ONTAP REST メトリクス API を活用

### 運用自動化
- **RPO アラート**: SnapMirror Lag が閾値超過時に SNS 通知 + UI 警告バッジ (実装済み: UI 警告)
- **FlexCache プリポピュレート**: 作成時に初期ウォームアップディレクトリを指定可能に
- **Secrets ローテーション自動化**: Lambda rotation function による定期パスワード更新

### UX 改善
- **FlexCache 作成ウィザード**: オリジンボリュームドロップダウン (実装済み: datalist)、サイズ自動推奨 (オリジンの 10%)
- **削除確認のインライン UI**: window.confirm() → カスタム確認ダイアログ (ARIA 対応)
- **マルチ FS 切り替え**: portal-config で複数ファイルシステムを定義し UI で切り替え

### 監査・コンプライアンス
- **操作監査証跡**: DynamoDB への全操作ログ書き込み (誰が/いつ/何を)
- **mTLS 対応**: ONTAP 自己署名証明書の CA 検証オプション化

### アクセシビリティ
- **ARIA dialog パターン**: 確認ダイアログの aria-modal + focus trap
- **ステータスバッジの aria-label**: スクリーンリーダー対応
