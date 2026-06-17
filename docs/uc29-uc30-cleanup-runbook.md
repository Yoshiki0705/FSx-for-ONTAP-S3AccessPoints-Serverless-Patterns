# UC29 / UC30 teardown & rebuild runbook

両UC の検証環境を**スクリプト一発**で安全に撤去し、必要時に再構築する手順。
過去の削除作業で得た学び（依存順序・FSx S3 AP・Athena WG・Bedrock KB の削除順）を
スクリプトに内包済み。共有の FSx for ONTAP ファイルシステム本体は既定で**保持**する。

## TL;DR

```bash
# ---- Teardown（UC29/UC30 検証リソースを全撤去、FS 本体は保持）----
bash scripts/teardown-uc29-uc30.sh

# ---- Rebuild（KB スタックを再作成：AOSS+index+KB+DataSource+取り込み）----
source scripts/uc29-kb-manifest.local.env        # 実環境値（gitignored）
.venv/bin/python scripts/rebuild-uc29-kb.py

# ---- スタック再デプロイ（必要時。UC29/30 は make ターゲット無し、sam 直接）----
cd genai-kb-selfservice-curation  && sam build && sam deploy   # UC29（samconfig.toml 要）
cd genai-quick-agentic-workspace && sam build && sam deploy   # UC30（samconfig.toml 要）
```

> スクリプトは**冪等**。途中失敗（非同期依存）後はそのまま再実行すれば残りを片付ける。

## 汎用ツールとの関係（重要：整合性・再利用性）

このスクリプトは **UC29/UC30 専用**であり、全 UC 汎用ではない。理由と使い分け:

| 対象 | 撤去ツール | 理由 |
|------|-----------|------|
| UC1–UC28 / SAP / FC1–6 | `scripts/cleanup_generic_ucs.py`（＋ `cleanup_stacks.sh`） | 純粋な CloudFormation スタックのみ。汎用ツールが Athena WG・バージョン付き S3・VPC Endpoint SG・DELETE_FAILED 修復を網羅 |
| **UC29 / UC30** | **`scripts/teardown-uc29-uc30.sh`** | スタック外で手動作成した非 CFN リソース（AOSS コレクション/ポリシー、Managed AD、Windows EC2、FSx SVM/ボリューム、FSx S3 Access Point、Bedrock KB）を含むため専用処理が必要 |

整合性のための約束:
- CFn スタック削除のブロッカー対処（Athena WG recursive・バージョン付き S3 空化）は
  汎用ツール（`cleanup_stacks.sh` / `cleanup_generic_ucs.py`）と**同じ規約**に揃えている。
- 本スクリプト固有で汎用ツールに無い知見（**FSx S3 AP detach**・**Bedrock KB RETAIN**）は、
  横展開のため `docs/operational-runbooks/cleanup-troubleshooting.md`（Failure Mode 7/8）にも記載。
- 将来 UC29/30 を汎用 `cleanup_generic_ucs.py` に統合する場合は、UC_DIR_MAP 追加に加え
  非 CFN リソースの削除フックが必要（現状は UC17 までの CFn 前提）。

## 撤去対象（スクリプトが自動解決・名前ベース）

| 種別 | リソース |
|------|---------|
| CFn スタック | `fsxn-s3ap-uc29-selfservice-kb` / `fsxn-s3ap-uc30-quick-workspace` |
| Bedrock KB | `uc29-selfservice-kb`（＋ `DELETE_UNSUCCESSFUL` 状態の残骸 KB も掃除） |
| AOSS | コレクション `uc29-kb-vectors` ＋ encryption/network/access ポリシー |
| IAM ロール | `fsxn-s3ap-bedrock-kb-role` |
| Managed AD | `uc29demo.local` |
| Windows EC2 + SG | `uc29-windows-demo` |
| FSx S3 AP | `uc29-ai-knowledge-smb` / `uc30-quick-workspace-smb`（detach+delete） |
| FSx ボリューム / SVM | `ai_knowledge` / `quick_workspace` / `uc29demosvm` |
| Glue テーブル / Athena WG | `sales_pipeline`,`it_incidents` / `quick-workspace-wg` |
| EventBridge バス | `fsxn-fpolicy-events` |
| S3 デモバケット | `uc29-demo-sample-<ACCOUNT_ID>` |

## 保持（再利用）リソース

- FSx for ONTAP ファイルシステム本体（全28+パターン共有）
- KB データソースが指す共有 S3 Access Point（別パターンの AP を再利用）

> ファイルシステムも消す場合のみ: `DELETE_FSX_FILESYSTEM=true bash scripts/teardown-uc29-uc30.sh`
> （安全のため自動削除はせず、手動コマンドを表示するだけ）

## 削除順序で踏んだ落とし穴（スクリプト内に対策済み）

1. **FSx ボリューム削除前に S3 Access Point を detach** すること。
   付いたままだと `Cannot delete volume while it has one or multiple S3 access points`。
   これは s3control の AP ではなく **FSx の `DetachAndDeleteS3AccessPoint`** API で消す。
2. **Athena WorkGroup は保存クエリがあると CFn 削除が失敗**（`WorkGroup ... is not empty`）。
   スタック削除前に `delete-work-group --recursive-delete-option` で先に空にする。
3. **Bedrock KB は AOSS コレクション/ロールより先に消す**こと。
   `dataDeletionPolicy=DELETE` のままだと削除時にベクトルストアを purge しようとし、
   コレクションやロールが先に消えていると **`DELETE_UNSUCCESSFUL`** で詰まる。
   → スクリプトは削除前に全データソースを **`RETAIN`** に切り替え、KB 削除がストアに
   依存しないようにしてから削除し、消えるまで待機する。
   （既に詰まった KB の救済も同手順：DS を RETAIN→削除→KB 削除）
4. **非空 S3 バケットは事前に空に**（バージョン・削除マーカー含む）。
5. **IAM ロールは inline/attached ポリシーを外してから** `delete-role`。
6. **AD 削除は非同期**（~15-30分）。`delete-directory` を投げて完了待ちは省略可。

## Rebuild の要点（`scripts/rebuild-uc29-kb.py`）

### 所要時間の目安

| フェーズ | 所要時間 |
|---------|---------|
| AOSS collection 起動（CREATING→ACTIVE） | ~5 分 |
| vector index 作成 + data-plane 伝播待ち | ~1 分 |
| Bedrock KB + DataSource 作成 | ~30 秒 |
| Ingestion ジョブ完了（20 ドキュメント規模） | ~3 分 |
| **合計（rebuild 一回通し）** | **~10 分** |

> ドキュメント数が多い（数百件）場合は Ingestion が 10-30 分に延びる。AOSS 起動時間はドキュメント数に依存しない。

- **S3 Vectors ストアは CLI/boto3 で作成不可**（コンソール quick-create のみ）。
  本スクリプトは **OPENSEARCH_SERVERLESS** を使う。
- 埋め込みは `amazon.titan-embed-text-v2:0` / **256 次元**。knn index の dimension と一致必須。
- KB データソースの「バケット」は **FSx ONTAP S3 AP のエイリアス**（`arn:aws:s3:::<alias>`）。
  実エイリアスは公開リポジトリに含めない → `scripts/uc29-kb-manifest.local.env`（gitignored）から供給。
- AOSS data-access ポリシーには **KB ロールと呼び出し元の両方**を含める
  （index はカレント認証情報で作成するため）。
- ロール/ポリシー伝播と collection ACTIVE は結果整合 → スクリプトはポーリング/リトライ。

## Amazon Quick の扱い（重要・コスト）

UC30 検証で **Amazon Quick を有効化済み**。ユーザー/アカウントが有効な間は**月額課金**。
スタック削除では止まらない（CFn 外）。不要なら手動で停止:

- Quick コンソール → アカウント管理 → 不要ユーザーのアクセス権を取り消す
- 解約: Quick「アカウント設定 → サブスクリプション解約」（QuickSight 資産も削除される点に注意）

## 残留物の確認

```bash
bash scripts/teardown-uc29-uc30.sh   # 末尾に Residual check を表示（再実行で冪等確認）
```
