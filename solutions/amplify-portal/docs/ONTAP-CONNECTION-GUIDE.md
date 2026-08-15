# ONTAP REST API 接続ガイド — File Portal

🌐 **Language / 言語**: 日本語 | [English](ONTAP-CONNECTION-GUIDE.en.md)

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

FSx for ONTAP の `fsxadmin` パスワードを変更する場合、**必ず両方を更新**してください。**Step 1 の成功を確認してから Step 2 を打つこと**（理由は下記）:

```bash
NEWPW='NewSecureP@ss2026!'

# Step 1: FSx for ONTAP 側のパスワード変更
# 成功したときだけ Step 2 に進む。&& でつなぐか、if で明示的に分岐する
if aws fsx update-file-system \
     --file-system-id <fs-id> \
     --ontap-configuration "{\"FsxAdminPassword\":\"$NEWPW\"}" \
     --region <your-region>; then
  # Step 2: Secrets Manager の値を同期
  aws secretsmanager put-secret-value \
    --secret-id fsx-ontap-fsxadmin-credentials \
    --secret-string "{\"username\":\"fsxadmin\",\"password\":\"$NEWPW\"}" \
    --region <your-region>
else
  echo "Step 1 が失敗したのでシークレットは変更しない"
fi
```

> **なぜ分岐が必要か**: この 2 つを無条件に並べて実行し、**Step 1 だけが失敗して Step 2 が成功した**ことがある。結果として、シークレットには ONTAP が一度も受け取っていない値が入り、**不一致は解消されるどころか悪化した**。復旧は「もう一度 Step 1 を通してから Step 2」でしかない。Step 1 は同期的にバリデーションを返すので、確認は容易である。

**パスワードの制約**（Step 1 が拒否する条件。エラーは同期的に返る）:

| 条件 | 内容 |
|------|------|
| 長さ | 8〜128 文字 |
| 必須 | 英字を 1 文字以上、数字を 1 文字以上 |
| **禁止** | **文字列 `admin` を含んではならない** |

> 最後の 1 行は見落としやすい。`fsxadmin` にちなんだ名前（`Fsxadmin-...` 等）を付けると、この規則に触れて Step 1 が
> `Provided FsxAdminPassword is not valid` で失敗する。実際に踏んだ。

> **注意**: Step 1 と Step 2 の間にポータルが API 呼び出しを行うと、古いパスワードで認証失敗します。ONTAP は認証失敗を記録し、一定回数超過でアカウントをロックアウトする場合があります。

変更後は preflight で確認します:

```bash
make ontap-preflight FS_ID=<fs-id> LAMBDA=<ResourceMgmtFunction の名前>
# → 6. [PASS] ONTAP auth / ONTAP accepted the credentials and answered.
```

## トラブルシューティング

### まず `make ontap-preflight` を実行する

ONTAP パネルにデータが出ないとき、原因は 6 つの段のどれかにある。**画面のメッセージから逆算しないこと**（後述の理由により、以前のポータルは違う段を指していた）。次のコマンドが 6 段を順に検査し、壊れている段を名指しする。

```bash
# 段 1・5（設定とシークレット）
make ontap-preflight

# 段 2〜4 を追加（ファイルシステム / SVM / ボリュームの実在確認）
make ontap-preflight FS_ID=fs-0123456789abcdef0

# 段 6 を追加（ONTAP が認証情報を受け付けるか）
make ontap-preflight FS_ID=fs-0123456789abcdef0 LAMBDA=<ResourceMgmtFunction の名前>
```

| 段 | 検査内容 | 失敗したときに見る場所 |
|:--:|---------|---------------------|
| 1 | `portal-config.ts` に 4 つの値があるか | `amplify/portal-config.ts` |
| 2 | ファイルシステムが AVAILABLE で、**管理 IP がそのファイルシステムのものか** | `ontapMgmtIp` |
| 3 | 設定した SVM 名が実在するか | `ontapSvmName` |
| 4 | 設定したボリューム名がその SVM にあるか | `ontapVolumeName` |
| 5 | シークレットが読めて JSON で、パスワードに前後の空白がないか | Secrets Manager |
| 6 | **ONTAP が認証情報を受け付けるか** | 下の HTTP 401 の節 |

段 6 だけは手元の端末から検査できない。管理 LIF はプライベートなので、`LAMBDA=` でデプロイ済み関数に代理で呼ばせる。指定しない場合、段 6 は PASS ではなく **SKIP** と表示される。実際に壊れていた段を一度も試さずに全段グリーンと出すほうが、何も出さないより悪いため。

#### 画面はこう表示される

認証情報が拒否されたときの実際の表示。見出しが原因を名指しし、✅ の行が「ネットワークは調べなくてよい」と明示し、対処コマンドは FSx 側と Secrets Manager 側の 2 段そろっている（片方だけではポータルは直らないため）。エラー詳細には ONTAP 自身のメッセージ・HTTP ステータス・エラーコードがそのまま入る（サポートケースに逐語で貼れるようにするため、ここは翻訳していない）。

![認証情報が拒否されたときの表示（ライトテーマ）](screenshots/portal-ontap-credentials-rejected.png)

ダークテーマ:

![認証情報が拒否されたときの表示（ダークテーマ）](screenshots/portal-ontap-credentials-rejected-dark.png)

パスワードを揃えたあとの同じパネル。preflight が全段 PASS になり、スナップショットが一覧される:

![復旧後のスナップショット一覧](screenshots/portal-snapshots-recovered.png)

> **なぜこの順序が重要か**: 検証環境で実際に起きた事象は「段 1〜5 がすべて PASS し、段 6 だけが FAIL」だった。`aws fsx describe-volumes` はボリュームを CREATED として返し、リクエストは TLS でクラスタに到達していた。原因は Secrets Manager と ONTAP のパスワード不一致である。にもかかわらずポータルは「📡 ONTAP 接続が必要」という見出しで VPC・サブネット・セキュリティグループの確認を促していた。**間違った層を名指しすることは、何も言わないより高くつく。読者はそれを信じるからである。**
>
> 現在は各パネルが原因を 5 クラス（`NOT_CONFIGURED` / `UNREACHABLE` / `CREDENTIALS_REJECTED` / `NOT_FOUND` / `ONTAP_ERROR`）に分類して表示し、認証情報が拒否された場合は「ネットワークを調べる必要はない」と明示する。分類は `shared/ontap_diagnosis.py` にある。

> **利用者から報告を受けて調べている場合**: 利用者に頼むもの（画面の見出し・エラー詳細の中身）と、
> 症状から確認先を引く逆引き表は [引き渡しと問い合わせ対応ガイド](portal-handover-guide.md#利用者の言葉--確認するもの) にある。

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

### 新規作成と初期化

CLI では `volume create -type DP` → `snapmirror create` → `snapmirror initialize` の 3 手順ですが、ポータルの `createSnapmirror` は 1 回の POST で済ませます。

| 引数 | 効果 |
|------|------|
| `create_destination.enabled` | 宛先ボリュームを ONTAP が作成する。事前に `-type DP` で作る必要がない |
| `create_destination.tiering.supported` | FabricPool アグリゲートへの配置を許可する。**既定は false** で、FSx for ONTAP のアグリゲートはすべて FabricPool 付きなので、既定のままだと配置先が無く失敗する（FlexCache の `use_tiered_aggregate` と同じ罠） |
| `state: snapmirrored` | 作成と同時に初期化する。指定しないと `uninitialized` のままで転送履歴が空のまま |

POST は**宛先クラスター**（= ポータルの接続先）に対して発行します。したがって別ファイルシステム上のボリュームを保護する操作が、こちら側だけで完結します。逆に、宛先が別クラスターにある関係はこのポータルからは見えず、操作もできません。

### 前提条件

- クラスターピアが `available`。
- SVM ピアが `peered` で、**用途に `snapmirror` が含まれている**。FlexCache 用に作成したピアは `peered` でありながら SnapMirror を拒否し、`SVM peer permission not found.` のように「ピアされていない」ように見えるエラーを返します。ポータルの SVM ピア一覧の「用途を変更」で `snapmirror` を追加すれば解消し、ピアの作り直しは不要です。

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
