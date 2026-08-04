# ファイルポータル — クイックリファレンス

> 🌐 Language: [English](../en/portal-quick-reference.md) | **日本語** | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

日常のポータル操作を 1 ページにまとめたチートシート。印刷またはブックマークしてください。

---

## ナビゲーション

| サイドバーセクション | 機能 |
|:---:|------|
| 📂 All Files | ブラウズ、プレビュー、ダウンロード、共有、AI Q&A |
| ⭐ Favorites | ピン留めしたファイル |
| 🕐 Recent | アクセス履歴 |
| 📤 Upload | ドラッグ＆ドロップアップロード（最大 50 GB/ファイル） |
| ⚡ AI Processing | フォルダに対する AI/ML ワークフローの実行 |
| 📋 Job History | 過去のジョブ結果とステータス |
| 📊 Analytics | Athena SQL クエリ |
| 📸 Snapshots | ポイントインタイムコピー + FlexClone リストア |
| 🔒 Lock | SnapLock / S3 Object Lock / 改ざん防止 |
| 🛡️ ARP/AI | ランサムウェア保護ステータス |
| 🔧 Resources | ストレージ管理パネル（管理者のみ） |
| 🔄 Version Diff | スナップショット間のファイル比較 |
| 🔍 Audit Trail | 誰が何にいつアクセスしたか |

---

## 主な操作（全ユーザー）

| やりたいこと | 操作方法 |
|------------|---------|
| ファイルをブラウズ | サイドバー → 📂 All Files → フォルダをクリック |
| PDF をプレビュー | ファイル横の 📕 をクリック |
| Word ドキュメントをプレビュー | ファイル横の 📝 をクリック |
| ファイルをダウンロード | ファイル横の 📄 をクリック |
| ファイルの共有リンクを作成 | 🔗 をクリック → TTL を選択 → URL をコピー |
| ファイルについて AI に質問 | ファイルを選択 → 右パネルに質問を入力 |
| 画像内オブジェクトの検出 | 画像を選択 → 右パネルの「Detect Objects」 |
| ファイルをアップロード | サイドバー → 📤 Upload → ドラッグ＆ドロップ |
| フォルダに AI を実行 | All Files でファイルリスト上部の ⚡ をクリック |
| ジョブ結果を確認 | サイドバー → 📋 Job History → ジョブをクリック |
| スナップショットから復元 | サイドバー → 📸 Snapshots → 「Restore」ボタン |
| 言語を切り替え | トップバーの 🌐 をクリック |

---

## 主な操作（コンプライアンス / セキュリティ）

| やりたいこと | 操作方法 |
|------------|---------|
| ランサムウェアステータスの確認 | サイドバー → 🛡️ ARP/AI |
| WORM ロックの確認 | サイドバー → 🔒 Lock → SnapLock タブ |
| 出力バケットのロック確認 | サイドバー → 🔒 Lock → S3 Object Lock タブ |
| ロック済みスナップショットの閲覧 | サイドバー → 🔒 Lock → Tamperproof タブ |
| アクセス監査の確認 | サイドバー → 🔍 Audit Trail |
| PHI ガードレールの確認 | All Files → `/dicom/` に移動 → ボタンに 🚫 が表示 |

---

## 主な操作（ストレージ管理者）

| やりたいこと | 操作方法 |
|------------|---------|
| ヘルスダッシュボードの表示 | サイドバー → 🔧 Resources（ダッシュボードが最初に表示） |
| ボリュームの管理 | Resources → Storage → Volumes |
| エクスポートポリシーの設定 | Resources → Access Control → Export Policies |
| ボリュームの ARP 有効化 | Resources → Protection → ARP Admin |
| スナップショットのロック | Resources → Protection → Snapshot Admin → Lock フォーム |
| 侵害ユーザーのブロック | サイドバー → 🛡️ ARP/AI → Contain タブ → Block SMB User |
| 解決後のブロック解除 | サイドバー → 🛡️ ARP/AI → Unblock タブ |
| EMS アラートの確認 | Resources →（モニタリングに EMS イベント表示） |

---

## キーボードショートカット

| キー | アクション |
|-----|---------|
| `Tab` | インタラクティブ要素間の移動 |
| `Enter` | ボタンの実行 / フォルダを開く |
| `Escape` | モーダルを閉じる / パネルを非表示 |

---

## ステータスインジケータ

| アイコン | 意味 |
|:---:|------|
| 🟢 | 正常 / 脅威なし / 解決済み |
| 🔴 | 脅威検出 / エラー |
| 🟠 | 封じ込め済み（インシデント対応中） |
| 🟡 | 調査中 |
| 🚫 | PHI — AI ブロック（ガードレール有効） |
| ⚠️ | 警告（容量 85% 超過など） |

---

## アクセスレベル

| グループ | できること | できないこと |
|---------|----------|------------|
| `authenticated` | ブラウズ、ダウンロード、アップロード、AI、保護状態の閲覧 | ストレージ設定の変更 |
| `storage-admin` | 上記すべて + ボリューム作成/削除、スナップショットロック、ユーザーブロック、ポリシー管理 | — |

---

## トラブルシューティング早見表

| 症状 | 対処方法 |
|-----|---------|
| 「ONTAP Connection Required」 | DemoMode では正常です。管理者に VPC 設定を依頼してください。 |
| AI ボタンに 🚫 が表示 | PHI 保護フォルダ内にいます。別のフォルダに移動してください。 |
| 共有リンクの有効期限切れ | 新しいリンクを生成してください（🔗）。最大 TTL = 1 時間。 |
| NFS 書き込み後にファイルが表示されない | ファイルリストを更新してください。通常は即座に反映されます。 |
| 読み込みが終わらない | インターネット接続を確認。サインアウト → サインインを試してください。 |

---

## ドキュメントマップ

| あなたの役割 | 読むべきドキュメント |
|------------|-----------------|
| エンドユーザー（日常操作） | [ユーザーガイド](portal-user-guide.md) |
| セキュリティ / コンプライアンス担当者 | [コンプライアンスガイド](portal-compliance-guide.md) |
| ストレージ管理者 | [管理者デモガイド](admin-resource-management-demo.md) |
| IT 管理者（デプロイ） | [Getting Started](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| 開発者（カスタマイズ） | [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
