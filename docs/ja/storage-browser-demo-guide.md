# Storage Browser for S3 + FSx for ONTAP S3 Access Points — デモガイド

FSx for ONTAP ボリューム上のファイルを、React Web アプリから直接閲覧・プレビュー・ダウンロード・アップロードする [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) の構成手順。

---

## 概要

Storage Browser for S3 は Amplify UI の React コンポーネント（2024年12月 GA）。S3 データに対するファイルエクスプローラー体験を提供する。FSx for ONTAP S3 Access Points は標準 S3 API（`ListObjectsV2`, `GetObject`, `PutObject`, `DeleteObject`）を公開するため、Storage Browser は S3 AP エイリアスを通常のバケット名と同様に扱える。

### 提供される機能

| 機能 | Storage Browser が提供 |
|---|---|
| ファイル一覧・フォルダナビゲーション | ページネーション付きリスト + ブレッドクラム |
| ファイルプレビュー | 画像・動画・テキストをブラウザ内レンダリング |
| ファイルダウンロード | Presigned URL による直接ダウンロード |
| ファイルアップロード | ドラッグ＆ドロップ、最大 5 GB（FSx for ONTAP S3 AP 制約） |
| コピー＆削除 | 単一ファイルまたはフォルダ丸ごと |
| フォルダ作成 | 新規フォルダ作成（S3 プレフィクス作成） |

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  ブラウザ (React + @aws-amplify/ui-react-storage)     　   　 │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Storage Browser コンポーネント                    │       │
│  │  - createManagedAuthAdapter (IAM 資格情報)        │       │
│  │  - S3 Client → ListObjectsV2 / GetObject / etc.  │       │
│  └──────────────────┬───────────────────────────────┘       │
└─────────────────────┼───────────────────────────────────────┘
                      │ HTTPS (SigV4)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  S3 Access Point エンドポイント                               │
│  エイリアス: xxx-ext-s3alias                                　│
│  ネットワークオリジン: Internet                             　　│
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP ボリューム                         　          │
│  - NFS/SMB と S3 AP から同時アクセス可能              　        │
│  - FileSystemIdentity が ONTAP レベルの権限を適用       　　    │
└─────────────────────────────────────────────────────────────┘
```

---

## 前提条件

| 項目 | 要件 |
|---|---|
| FSx for ONTAP | AVAILABLE、1 つ以上のボリュームがマウント済み（ジャンクションパスあり） |
| S3 Access Point | ボリュームにアタッチ済み、Internet origin、Lifecycle = AVAILABLE |
| IAM 資格情報 | S3 AP ARN に対する `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` 権限 |
| Node.js | v18+ |

---

## 3 つの認証方式

### 方式 1: Amplify Auth (Cognito)

用途: 顧客・パートナー向けポータル（ソーシャルログイン / エンタープライズ SSO）

**Note**: Amplify Storage カテゴリが S3 AP をネイティブサポートしていないため（FR-6）、現時点では方式 2 を推奨。

### 方式 2: Managed Auth Adapter（カスタム資格情報）— S3 AP に推奨

用途: IAM 資格情報を自前で管理する構成（Cognito Identity Pool + STS AssumeRole）

```typescript
import { createManagedAuthAdapter, createStorageBrowser } from '@aws-amplify/ui-react-storage/browser';
import '@aws-amplify/ui-react-storage/styles.css';

// ===== 設定 — 自環境に合わせて変更 =====
const CONFIG = {
  // FSx for ONTAP S3 AP エイリアス
  // 取得: aws fsx describe-s3-access-point-attachments --query '...Alias'
  s3ApAlias: 'your-ap-alias-ext-s3alias',
  // S3 AP のリージョン（FSx for ONTAP と同じ）
  region: 'ap-northeast-1',
  // AWS アカウント ID
  accountId: '123456789012',
};
// ===== 設定ここまで =====

export const { StorageBrowser } = createStorageBrowser({
  config: createManagedAuthAdapter({
    credentialsProvider: async () => {
      // バックエンド API から一時資格情報を取得
      const response = await fetch('/api/credentials');
      const creds = await response.json();
      return {
        credentials: {
          accessKeyId: creds.accessKeyId,
          secretAccessKey: creds.secretAccessKey,
          sessionToken: creds.sessionToken,
          expiration: new Date(creds.expiration),
        },
      };
    },
    region: CONFIG.region,
    accountId: CONFIG.accountId,
    registerAuthListener: () => {},
  }),
});
```

### 方式 3: S3 Access Grants（エンタープライズ規模）

用途: IAM Identity Center + S3 Access Grants を使う大規模組織。本ガイドでは割愛 — [AWS ドキュメント](https://docs.aws.amazon.com/AmazonS3/latest/userguide/setup-storagebrowser.html)を参照。

---

## クイックスタート（方式 2）

### 1. プロジェクト作成

```bash
npm create vite@latest storage-browser-fsxn -- --template react-ts
cd storage-browser-fsxn
npm install @aws-amplify/ui-react-storage aws-amplify
```

### 2. Storage Browser コンポーネントの設定

`src/StorageBrowserFSxN.tsx` を作成（上記の方式 2 コード）。

### 3. Location Provider の設定

`src/locations.ts`:

```typescript
export const getLocations = () => ({
  locations: [
    {
      bucket: 'your-ap-alias-ext-s3alias', // S3 AP エイリアスをバケット名として指定
      id: 'fsxn-volume',
      permissions: ['delete', 'get', 'list', 'write'],
      prefix: '',
      type: 'PREFIX' as const,
    },
  ],
});
```

### 4. App.tsx でレンダリング

```tsx
import { StorageBrowser } from './StorageBrowserFSxN';

function App() {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 20 }}>
      <h1>FSx for ONTAP ファイルポータル</h1>
      <StorageBrowser />
    </div>
  );
}

export default App;
```

### 4. CLI で S3 AP を作成（検証済み構文）

```bash
# JSON 入力ファイル作成（S3AccessPoint ブロック省略 = Internet origin）
cat <<EOF > create-ap.json
{
    "Name": "my-storage-browser-ap",
    "Type": "ONTAP",
    "OntapConfiguration": {
        "VolumeId": "fsvol-XXXXXXXXXXXXXXXXX",
        "FileSystemIdentity": {
            "Type": "UNIX",
            "UnixUser": {
                "Name": "root"
            }
        }
    }
}
EOF

# S3 AP 作成
aws fsx create-and-attach-s3-access-point \
  --cli-input-json file://create-ap.json \
  --region ap-northeast-1

# AVAILABLE になるまで待機（10 秒間隔でポーリング）
watch -n 10 "aws fsx describe-s3-access-point-attachments \
  --region ap-northeast-1 \
  --query 'S3AccessPointAttachments[?Name==\`my-storage-browser-ap\`].{Lifecycle:Lifecycle,Alias:S3AccessPoint.Alias}' \
  --output table"
```

**検証で得た知見（2026-07-19）**:
- `--cli-input-json` が複雑な構造を渡す確実な方法（位置引数は脆弱）
- `S3AccessPoint` ブロック省略 → Internet origin（デフォルト）。VPC 制限する場合は `"S3AccessPoint": {"VpcConfiguration": {"VpcId": "vpc-XXX"}}` を追加
- WINDOWS identity は AD DC が SVM から到達可能でなければエラー（"Failed to lookup the provided user in ONTAP"）
- UNIX identity（例: `root`）は AD 不要 — デモに最適

### 5. 起動・確認

```bash
npm run dev
# http://localhost:5173 を開く
```

---

## パラメータリファレンス

| パラメータ | 確認方法 | 例 |
|---|---|---|
| `s3ApAlias` | `aws fsx describe-s3-access-point-attachments --query '...Alias'` | `myap-abc123-ext-s3alias` |
| `region` | FSx for ONTAP と同じリージョン | `ap-northeast-1` |
| `accountId` | `aws sts get-caller-identity --query Account` | `123456789012` |
| `credentials` | Cognito Identity Pool or STS AssumeRole | 一時セッション資格情報 |

---

## IAM ポリシー（最小権限）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name/object/*"
      ]
    }
  ]
}
```

**重要**: S3 AP ARN 形式（`arn:aws:s3:{region}:{account}:accesspoint/{name}`）を使用。バケット ARN 形式（`arn:aws:s3:::{name}`）では動作しない。

---

## 本番デプロイ時の考慮事項

### 資格情報バックエンド

フロントエンドに AWS 資格情報を埋め込まないこと。以下のいずれかを使用:

| 方式 | 概要 |
|---|---|
| Cognito Identity Pool | フェデレーション ID → S3 AP スコープの一時 STS 資格情報 |
| API Gateway + Lambda | バックエンドが STS AssumeRole で一時資格情報を返す |
| Amplify Auth | FR-6 解決後、Amplify Storage の直接フロー |

### FileSystemIdentity の選択

| ID タイプ | ユースケース | 備考 |
|---|---|---|
| UNIX (uid/gid) | NFS 主体のボリューム、Linux ワークロード | 最もシンプル、AD 不要 |
| WINDOWS (AD ユーザー) | SMB 主体のボリューム、AD 連携エンタープライズ | SVM AD-join 必須、NTFS ACL 適用 |

---

## 制約と回避策

| 制約 | 詳細 | 回避策 |
|---|---|---|
| アップロードサイズ | 5 GB（FSx for ONTAP S3 AP 制約） | Storage Browser は 5 GB まで自動対応 |
| 公式ロードマップ | "Support for S3 Access Points" が評価中 | 方式 2（managed auth + AP alias）で動作 |
| Presigned URL ドキュメント | FSx docs で "Not supported" 記載 | 動作確認済み（client-side SigV4）。[詳細](../s3ap-compatibility-notes.en.md) |

---

## 関連リソース

- [Storage Browser for S3 — Amplify UI ドキュメント](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)
- [Storage Browser セットアップ — S3 ユーザーガイド](https://docs.aws.amazon.com/AmazonS3/latest/userguide/setup-storagebrowser.html)
- [FSx for ONTAP S3 AP 互換性](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [S3 AP と AWS サービスの連携](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [AWS Storage Blog: S3 AP + AD + Quick Suite](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
