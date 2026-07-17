# Nextcloud External Storage と FSx for ONTAP S3 Access Points の統合

## エグゼクティブサマリ

Nextcloud の External Storage アプリを使うことで、FSx for ONTAP ボリューム上のファイルを S3 Access Point 経由で Nextcloud のファイルブラウザに表示できます。データ移行なしに、エンタープライズ NAS ファイルを Web インターフェースで閲覧・操作できる構成です。

**結果**: NFS/SMB ユーザーは同じボリューム上で従来通り作業を続け、Nextcloud ユーザーも同じファイルを Web ブラウザから閲覧・アップロード・ダウンロードできます — データのコピーは不要。

---

## 目次

1. [前提条件](#前提条件)
2. [アーキテクチャ選択肢](#アーキテクチャ選択肢)
3. [IAM 設定](#iam-設定)
4. [Nextcloud External Storage セットアップ](#nextcloud-external-storage-セットアップ)
5. [動作確認手順](#動作確認手順)
6. [処理ワークフロー統合](#処理ワークフロー統合)
7. [本番堅牢化](#本番堅牢化)
8. [制約事項と回避策](#制約事項と回避策)
9. [トラブルシューティング](#トラブルシューティング)
10. [FAQ](#faq)
11. [関連ドキュメント](#関連ドキュメント)

---

## 前提条件

| 要件 | 説明 |
|------|------|
| FSx for ONTAP ファイルシステム | ジャンクションパスを持つボリュームが最低1つ必要 |
| S3 Access Point | 対象ボリュームにアタッチ済み（Internet-origin 推奨） |
| Nextcloud インスタンス | v25+（External Storage アプリは管理者権限が必要） |
| IAM 認証情報 | S3 AP 権限を持つ Access Key / Secret Key |
| ネットワーク接続 | Nextcloud サーバー → S3 AP エンドポイント（Internet or VPC） |

**用語**:
- **S3 AP エイリアス**: 自動生成される S3 Access Point エイリアス（例: `myap-abc123-s3alias`）。Nextcloud では「バケット名」として使用。
- **Internet-origin AP**: IAM 認証情報があればどこからでもアクセス可能な S3 AP（VPC 束縛なし）。
- **External Storage App**: リモートストレージをローカルフォルダとしてマウントする Nextcloud 管理プラグイン。

---

## アーキテクチャ選択肢

### 選択肢 A: Internet-Origin S3 AP（シンプルさ重視の推奨構成）

```
┌───────────────────────┐         ┌─────────────────────────────┐
│  Nextcloud サーバー    │         │  FSx for ONTAP              │
│  (EC2 / ECS / 外部    │  HTTPS  │  ┌───────────────────────┐  │
│   ホスティング)        │────────▶│  │ S3 Access Point       │  │
│                       │         │  │ (Internet-origin)     │  │
│  External Storage App │         │  └───────────┬───────────┘  │
│  (Amazon S3 バックエンド) │      │              │              │
└───────────────────────┘         │  ┌───────────▼───────────┐  │
                                  │  │ ONTAP Volume          │  │
                                  │  │ (/vol/data)           │  │
                                  │  │ NFS + SMB + S3        │  │
                                  │  └───────────────────────┘  │
                                  └─────────────────────────────┘
```

- Nextcloud はどこでも動作可能（AWS、オンプレミス、他クラウド）
- Nextcloud サーバーに VPC 配置の要件なし
- S3 AP エイリアスをバケット名として使用

### 選択肢 B: VPC-Origin S3 AP + 同一 VPC 内 Nextcloud

```
┌──────────────── VPC ────────────────────────────────────────┐
│  ┌───────────────────┐      ┌─────────────────────────────┐ │
│  │  Nextcloud (EC2)  │      │  FSx for ONTAP              │ │
│  │  + NFS マウント    │──────│  Volume (/vol/data)         │ │
│  │  (オプション)      │ NFS  │                             │ │
│  │                   │      │  S3 AP (VPC-origin)         │ │
│  │  External Storage │──────│                             │ │
│  │  (S3 バックエンド)  │ S3   └─────────────────────────────┘ │
│  └───────────────────┘                                      │
│         ▲                                                    │
│         │ S3 Gateway VPC Endpoint                            │
└─────────┼────────────────────────────────────────────────────┘
          │
     (Internet-origin AP では動作しない)
```

- 低レイテンシ（同一 VPC）
- オプションで NFS マウントによる高速プレビュー生成
- VPC-origin S3 AP + S3 Gateway VPC Endpoint が必要

> **重要**: S3 Gateway VPC Endpoint は Internet-origin S3 AP では動作しません。VPC 内から Internet-origin AP を使う場合、トラフィックは NAT Gateway または Internet Gateway 経由でルーティングされます。

### 選択肢 C: NFS マウントのみ（S3 AP なし）

ファイル閲覧層に S3 AP が不要な環境向け:

- Nextcloud EC2 が FSx for ONTAP ボリュームを NFS でマウント
- サブミリ秒のレイテンシでファイル閲覧・プレビュー
- 処理ワークフローは別途 S3 AP を使用（関心事の分離）
- 同一 VPC 内配置が必要

---

## IAM 設定

S3 Access Point にスコープした権限を持つ専用 IAM ユーザー（または EC2 インスタンスプロファイル用 IAM ロール）を作成します。

### IAM ポリシー（最小権限）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "NextcloudS3APAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>",
        "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"
      ]
    }
  ]
}
```

置換:
- `<REGION>`: AWS リージョン（例: `ap-northeast-1`）
- `<ACCOUNT_ID>`: 12桁の AWS アカウント ID
- `<AP_NAME>`: S3 Access Point 名

### セキュリティに関する補足

- Nextcloud 専用の IAM ユーザーを作成 — 他アプリケーションと認証情報を共有しない
- アクセスキーを定期的にローテーション（Secrets Manager での自動化を検討）
- EC2 上で Nextcloud を動かす場合は、静的アクセスキーより IAM インスタンスプロファイルを推奨
- 同一アカウント内アクセスでは S3 AP リソースポリシーは不要（IAM アイデンティティポリシーで十分）

---

## Nextcloud External Storage セットアップ

### ステップ 1: External Storage アプリの有効化

1. Nextcloud に管理者としてログイン
2. **アプリ**に移動（右上メニュー → アプリ）
3. 「**External storage support**」を検索
4. **有効にする**をクリック

### ステップ 2: S3 バックエンドの設定

1. **設定** → **管理** → **外部ストレージ** に移動
2. **ストレージを追加** → **Amazon S3** を選択
3. 以下の設定を入力:

| フィールド | 値 | 補足 |
|---|---|---|
| **フォルダ名** | `FSxONTAP-Data`（任意） | Nextcloud ファイル内でフォルダとして表示される |
| **認証** | アクセスキー | |
| **バケット** | `<S3-AP-ALIAS>` | S3 AP エイリアス（例: `myap-abc123-s3alias`） |
| **ホスト名** | `s3.<REGION>.amazonaws.com` | リージョナル S3 エンドポイント |
| **ポート** | （空欄） | デフォルト 443 |
| **リージョン** | `<REGION>` | 例: `ap-northeast-1` |
| **SSL を有効にする** | ✅ チェック | 常に HTTPS を使用 |
| **パススタイルを有効にする** | ✅ チェック | **S3 AP エイリアスでは必須** |
| **アクセスキー** | `<IAM_ACCESS_KEY_ID>` | 専用 IAM ユーザーから取得 |
| **シークレットキー** | `<IAM_SECRET_ACCESS_KEY>` | 専用 IAM ユーザーから取得 |
| **利用可能ユーザー** | （ユーザー/グループを選択） | 必要に応じてアクセスを限定 |

> **重要**: **パススタイルを有効にする**を必ずチェックしてください。S3 Access Point エイリアスはパススタイルアドレッシング（`https://s3.region.amazonaws.com/ap-alias/key`）を使用し、バーチャルホストスタイルではありません。

### ステップ 3: 接続確認

保存後、マウントの横にカラーサークルが表示されます:
- 🟢 緑: 接続成功
- 🔴 赤: 接続失敗（認証情報、エンドポイント、ネットワークを確認）
- 🟡 黄: 設定不完全

上部ナビゲーションの **ファイル** をクリック。設定したフォルダ名が表示されるはずです。フォルダに入ると FSx for ONTAP ボリュームの中身が見えます。

---

## 動作確認手順

設定後、以下の操作を確認してください:

```bash
# Nextcloud UI から:
# 1. 閲覧: 外部ストレージフォルダに移動 → ファイルが見える
# 2. ダウンロード: ファイルをクリック → ローカルにダウンロード
# 3. アップロード: ファイルをフォルダにドラッグ → NFS/SMB で確認

# NFS/SMB クライアントから（マルチプロトコル可視性の確認）:
# 1. NFS でファイル書き込み: echo "test" > /mnt/fsxn/test-from-nfs.txt
# 2. Nextcloud を更新 → ファイルが即座に表示される
# 3. Nextcloud からアップロード → NFS マウントでファイルが見える
```

| テスト | 期待結果 | 失敗時 |
|--------|---------|--------|
| ファイル一覧 | FSx for ONTAP ボリュームの内容が表示される | IAM ポリシー、バケット名（AP エイリアス使用）を確認 |
| ダウンロード | ブラウザにダウンロードされる | `s3:GetObject` 権限を確認 |
| アップロード (< 5GB) | NFS/SMB マウントにファイルが表示される | `s3:PutObject` 権限を確認 |
| アップロード (> 5GB) | マルチパートで成功 | マルチパート権限を確認 |
| 削除 | ボリュームからファイルが削除される | `s3:DeleteObject` 権限を確認 |
| NFS 書き込み → Nextcloud 表示 | 即座に反映 | Nextcloud のファイル一覧を更新 |

---

## 処理ワークフロー統合

Nextcloud でのファイル閲覧と、本リポジトリのサーバーレス処理パターンを連携させることができます。ユーザーが Nextcloud でファイルを閲覧・タグ付けし、処理ワークフローが同じデータを S3 AP 経由で処理する構成です。

### 選択肢 1: Webhook トリガー（推奨）

```
ユーザーが Nextcloud でファイルにタグ付け
  → Nextcloud Flow/Workflow App が HTTP webhook を発火
    → API Gateway
      → Step Functions StartExecution
        → Processing Lambda が S3 AP 経由でファイルを読み取り
          → 結果を書き戻し（Nextcloud で閲覧可能）
```

**Nextcloud Flow の設定**:
1. **設定** → **フロー**（または旧バージョンの **ワークフロー**）に移動
2. ルール作成: 「ファイルに `process-ai` タグが付いた時」
3. アクション: 「Web リクエストを送信」→ `POST https://<api-gw-url>/start`
4. ボディ: `{"file_path": "{file}", "pattern": "uc1-legal"}`

### 選択肢 2: スケジュールスキャン（既存パターン）

既存の EventBridge Scheduler パターンがボリュームを定期的にスキャンします。Nextcloud 固有の設定は不要 — Nextcloud からアップロードされたファイルは次のスキャンサイクルで自動的に検出されます。

### 選択肢 3: 手動 API 呼び出し

カスタム Nextcloud アプリまたは「External sites」アプリで処理 API を呼び出すボタンを埋め込み:

```javascript
// Nextcloud カスタムアプリ（簡略版）
async function triggerProcessing(filePath) {
  const response = await fetch('https://<api-gw-url>/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath, pattern: 'uc1-legal' })
  });
  return response.json();
}
```

---

## 本番堅牢化

### セキュリティチェックリスト

| 項目 | アクション |
|------|----------|
| HTTPS 必須 | ALB に ACM 証明書を設定 |
| WAF | AWS WAF を ALB にアタッチ（レート制限、地域制限） |
| IAM キーローテーション | Secrets Manager + Nextcloud occ コマンドで自動化 |
| Nextcloud 更新 | 定期的なアップデートスケジュール（セキュリティパッチ） |
| データベース暗号化 | RDS の保存時暗号化を有効化 |
| アクセスログ | ALB アクセスログ + Nextcloud 監査ログアプリを有効化 |
| バックアップ | RDS 自動バックアップ + Nextcloud 設定バックアップ |
| MFA | Nextcloud TOTP または WebAuthn プラグインを有効化 |
| サーバーディスク暗号化 | EBS/EFS 暗号化を有効化（Nextcloud キャッシュ/一時ファイル保護） |

> **Security note**: FSx for ONTAP ボリュームは NVE（保存時暗号化）で保護され、S3 AP は TLS（転送時暗号化）で通信します。ただし、Nextcloud サーバー上のキャッシュ・一時ファイルはサーバーディスクに書き込まれるため、EBS/EFS の暗号化を必ず有効にしてください。

### 推奨 Nextcloud アプリ

| アプリ | 用途 |
|--------|------|
| **External storage support** | S3 AP 統合のコア要件 |
| **Auditing / Logging** | コンプライアンス監査証跡 |
| **Flow** | 処理ワークフローの Webhook トリガー |
| **Two-Factor TOTP** | 管理者・ユーザーアカウントの MFA |
| **LDAP user and group backend** | AD/LDAP 統合 |
| **Brute-force settings** | ログイン保護 |
| **Files access control** | 細粒度ファイルアクセスルール |

### モニタリング

```bash
# 監視すべき CloudWatch メトリクス:
# - S3 AP: リクエスト数、レイテンシ（CloudTrail 経由）
# - EC2: CPU、メモリ、ディスク（Nextcloud サーバー）
# - ALB: リクエスト数、5xx エラー、レイテンシ
# - RDS: コネクション数、CPU、ストレージ

# Nextcloud ヘルスエンドポイント:
curl -s https://nextcloud.example.com/status.php | jq .
# 期待値: {"installed":true,"maintenance":false,"needsDbUpgrade":false,...}
```

---

## 制約事項と回避策

| 制約 | 影響 | 回避策 |
|------|------|--------|
| **Presigned URL（ドキュメント上 Not supported だが動作する）** | Nextcloud が S3 AP への直接ダウンロードリンクを Presigned URL で生成可能（GetObject の署名付きリクエストとして動作）。ただし AWS は本番依存を非推奨 | 選択肢 A: Presigned URL を利用しダイレクトダウンロード（サーバー負荷軽減）。選択肢 B: サーバープロセス経由プロキシ（ガバナンス重視）。 |
| **PutObject 最大 5 GB** | 大ファイルアップロードに制限 | Nextcloud はマルチパートアップロードを使用。ONTAP バージョン（9.15.1+）での S3 AP マルチパートサポートを確認。 |
| **ListObjectsV2 最大 1000/リクエスト** | 大規模ディレクトリにページネーションが必要 | Nextcloud の S3 バックエンドライブラリが自動処理。 |
| **S3 イベント通知なし** | S3 AP アップロードイベントでトリガーできない | Nextcloud Flow/Workflow の webhook、FPolicy（ONTAP ネイティブイベント）、またはスケジュールスキャンを使用。 |
| **AD-joined SVM: DC 到達性必須** | AD DC がダウンすると全 S3 AP 操作が失敗（AccessDenied） | AD DC の健全性を監視。[AD-Joined SVM S3 AP 前提条件](./en/ad-joined-svm-s3ap-prerequisites.md)を参照。 |
| **Nextcloud ファイルロック** | Nextcloud のファイルロックは NFS/SMB クライアントに及ばない | Nextcloud + NFS からの同時編集は競合の可能性あり。ONTAP の oplock/バイトレンジロックで調整。 |
| **サムネイル/プレビュー生成** | プレビューごとに S3 AP GetObject が発生しレイテンシ増加 | 選択肢 A: レイテンシを許容。選択肢 B: NFS マウントでプレビュー生成（同一 VPC のみ）。 |

### S3 AP vs NFS マウント: Nextcloud でどちらを使うか

| ユースケース | 推奨バックエンド | 理由 |
|---|---|---|
| リモート/マルチサイトアクセス | S3 AP (Internet-origin) | VPC 要件なし、どこからでもアクセス可能 |
| 同一 VPC で低レイテンシが必要 | NFS マウント or VPC-origin S3 AP | サブミリ秒のレイテンシで閲覧 |
| 大規模プレビュー/サムネイル | NFS マウント | ファイルごとの S3 API コールオーバーヘッドを回避 |
| 閲覧 + 処理のハイブリッド | S3 AP（Nextcloud と Lambda の両方） | 一貫したアクセスパターン |
| 読み取り多・書き込み少 | S3 AP | 典型的なファイルポータル用途に十分 |

---

## トラブルシューティング

### よくある問題

**設定後に赤丸（接続失敗）が表示される:**

1. IAM 認証情報が正しく有効であることを確認
2. バケットフィールドに **S3 AP エイリアス**（ボリューム名やバケット ARN ではない）が入っていることを確認
3. **パススタイルを有効にする**がチェックされていることを確認
4. リージョンが S3 AP のリージョンと一致していることを確認
5. Nextcloud サーバーからテスト: `aws s3 ls s3://<ap-alias>/ --region <region>`

**ファイルが表示されない（空のリスト）:**

1. S3 AP がファイルを含むボリュームにアタッチされていることを確認
2. IAM ポリシーに AP ARN（`/object/*` なし）に対する `s3:ListBucket` が含まれていることを確認
3. ボリュームにジャンクションパスがあること（SVM ネームスペースにマウントされていること）を確認

**アップロードが失敗する:**

1. `accesspoint/<name>/object/*` に対する `s3:PutObject` 権限を確認
2. 単一 PutObject ではファイルサイズ < 5 GB であることを確認（それ以上はマルチパート）
3. ONTAP ボリュームに空き容量があることを確認

**Nextcloud からアップロードしたファイルが NFS で見えない:**

1. FSx for ONTAP S3 AP の書き込みは NFS で即座に反映される — 遅延は想定されない
2. NFS クライアントのキャッシュが古い可能性: `ls -la` または `noac` オプションで再マウント
3. 正しいパスに書き込まれたことを確認（S3 AP ルート = ボリュームのジャンクションパス）

**AD-joined SVM で AccessDenied:**

1. これは IAM の問題ではなく AD DC 接続の問題の可能性が高い
2. 確認: `HeadBucket` は成功するが `ListObjectsV2` が失敗 = AD DC 到達不能
3. AD DC が稼働中で FSx SVM ENI から到達可能であることを確認
4. [AD-Joined SVM S3 AP 前提条件](./en/ad-joined-svm-s3ap-prerequisites.md)を参照

---

## FAQ

**Q: Nextcloud ユーザーは FSx for ONTAP ボリューム上のファイルを直接編集できますか？**
A: はい。PutObject（S3 AP 経由）は ONTAP ボリュームに直接書き込みます。ファイルは NFS/SMB ユーザーに即座に反映されます。ただし Nextcloud の協調編集（Collabora/OnlyOffice）は一時コピーを使い、編集後に書き戻します。

**Q: Nextcloud Desktop Client の同期は External Storage で動きますか？**
A: はい（注意あり）。外部ストレージフォルダはデスクトップクライアントで同期可能ですが、パフォーマンスはファイル数と S3 AP エンドポイントへのネットワークレイテンシに依存します。大規模ボリューム（10万ファイル以上）では選択的同期を検討してください。

**Q: どの Nextcloud ユーザーに FSx for ONTAP ファイルを見せるか制限できますか？**
A: はい。External Storage 設定の「利用可能ユーザー」フィールドで特定のユーザーやグループにアクセスを制限できます。Nextcloud の「Files access control」アプリと組み合わせれば、さらに細粒度のルールを適用可能です。

**Q: S3 AP がデタッチされた場合やボリュームがアンマウントされた場合どうなりますか？**
A: Nextcloud は外部ストレージフォルダへのアクセス時にエラーを表示します。他の Nextcloud 機能には影響しません。AP を再アタッチすればアクセスが復旧します。

**Q: 1つの Nextcloud インスタンスで複数の S3 AP（異なるボリューム）を使えますか？**
A: はい。External Storage エントリを複数追加し、それぞれ異なる S3 AP エイリアスを指定します。Nextcloud では別々のフォルダとして表示されます。

**Q: Nextcloud 経由のアップロードにファイルサイズ制限はありますか？**
A: FSx for ONTAP S3 AP は PutObject で最大 5 GB、マルチパートアップロードでそれ以上をサポートします。Nextcloud の PHP アップロード制限（`upload_max_filesize`、`post_max_size`）も適用されるため、必要に応じて `php.ini` で調整してください。

**Q: Nextcloud の External Storage で S3 AP を使う際の重要設定は？**
A: **パススタイルを有効にする**が最も重要です。S3 AP エイリアスはバーチャルホストスタイル（`ap-alias.s3.region.amazonaws.com`）に対応しないため、パススタイル（`s3.region.amazonaws.com/ap-alias`）を使用する必要があります。

---

## 関連ドキュメント

- [ファイルポータル UI の選択肢 (Amplify Gen2 / Nextcloud / カスタムビルド)](./file-portal-amplify-gen2.md) — アーキテクチャ比較と選択ガイド
- [S3AP 互換性ノート](./s3ap-compatibility-notes.md) — Presigned URL 制限を含む既知の制約
- [AD-Joined SVM S3 AP 前提条件](./en/ad-joined-svm-s3ap-prerequisites.md) — AD DC 到達性要件
- [S3AP パフォーマンス考慮事項](./s3ap-performance-considerations.md) — スループット設計ガイダンス
- [代替アーキテクチャ比較](./comparison-alternatives.md) — S3 AP vs EFS vs NFS vs DataSync
- [AWS Blog: Scale your Nextcloud with Storage on Amazon S3](https://aws.amazon.com/blogs/opensource/scale-your-nextcloud-with-storage-on-amazon-simple-storage-service-amazon-s3/) — Nextcloud + S3 のリファレンスアーキテクチャ
- [Nextcloud Admin Manual: Amazon S3 External Storage](https://docs.nextcloud.com/server/stable/admin_manual/configuration_files/external_storage/amazons3.html) — Nextcloud 公式 S3 設定ドキュメント

---

*最終更新: 2025-07 | 対象: Nextcloud 25+ / FSx for ONTAP S3 AP (ONTAP 9.14.1+)*
