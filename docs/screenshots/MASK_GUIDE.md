# Screenshot Masking Guide (v7, OCR-precision)

**Last updated**: 2026-05-11 (revised from v6 heavy-mask to v7 OCR-precision)

公開リポジトリにスクリーンショットを追加する前に、環境固有情報を自動マスクする。
本ガイドは v7 の OCR ベースワークフローの使い方、対象情報、検証手順を説明する。

---

## 1. 前提ツール

```bash
# macOS (Homebrew)
brew install tesseract tesseract-lang

# Python deps (any venv works)
pip3 install pillow pytesseract
```

`tesseract-lang` で `jpn` 訓練データもインストールされる。AWS コンソールが
日本語表示の場合に必須。

---

## 2. 初回セットアップ（contributor ごと）

`scripts/_sensitive_strings.py` と OCR helper 類は **gitignored**。各自がローカルで
`.example` 版をコピーして初期化する。

```bash
cp scripts/_sensitive_strings.py.example scripts/_sensitive_strings.py
cp scripts/_check_sensitive_leaks.py.example scripts/_check_sensitive_leaks.py
cp scripts/_inplace_ocr_mask.py.example scripts/_inplace_ocr_mask.py

# 編集: 自分の環境固有の機微リテラルを列挙
$EDITOR scripts/_sensitive_strings.py
```

`_sensitive_strings.py` に登録すべきカテゴリ（placeholder 値でイメージ）:

| カテゴリ | 例 (実値ではない) |
|---|---|
| AWS account ID (12 桁) | `"123456789012"` |
| FSx file system ID | `"fs-xxxxxxxxxxxxxxxxx"` |
| FSx volume ID | `"fsvol-xxxxxxxxxxxxxxxxx"` |
| SVM ID | `"svm-xxxxxxxxxxxxxxxxx"` |
| UUID (volume, SVM) | `"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"` |
| VPC / Subnet / SG | `"vpc-xxx"`, `"subnet-xxx"`, `"sg-xxx"` |
| ENI | `"eni-xxx"` |
| Private / public IPs | `"10.0.x.x"`, EC2 public IP |
| Secret / credential name | `"my-env-credentials"` |
| S3 Access Point alias | `"my-env-s3ap-xxxx-ext-s3alias"` |
| KMS key ID | `"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"` |
| Notification email | `"user@company.tld"` |

**重要**: 実値を `_sensitive_strings.py` に書く時点で、そのファイルは **git に
コミットされない** ことを確認（`git check-ignore scripts/_sensitive_strings.py`
が exit 0 + ファイル名を返せば OK）。

---

## 3. マスク実行ワークフロー

### 3-1. 通常フロー (originals あり)

```bash
# originals/ 配下に PNG を配置
#   docs/screenshots/originals/ucN-demo/<name>.png
#   docs/screenshots/originals/phaseN/<name>.png

# マスク実行 (単一フォルダ)
python3 scripts/mask_uc_demos.py uc11-demo

# マスク実行 (複数フォルダ)
python3 scripts/mask_uc_demos.py uc11-demo uc14-demo phase7

# マスク実行 (全フォルダ)
python3 scripts/mask_uc_demos.py

# 結果は docs/screenshots/masked/<dir>/ に保存される
```

### 3-2. In-place マスク (originals なし)

phase5 や過去に originals が破棄された masked ファイルを追加保護したい場合:

```bash
python3 scripts/_inplace_ocr_mask.py \
  docs/screenshots/masked/phase5/phase5-dynamodb-global-table.png

# ワイルドカードでもよい
python3 scripts/_inplace_ocr_mask.py docs/screenshots/masked/phase7/phase7-uc15-*.png
```

---

## 4. マスクアルゴリズム (v7 OCR)

1. `pytesseract.image_to_data(lang="eng+jpn")` で単語単位の bounding box を取得
2. 各単語を `SENSITIVE_STRINGS` の全文字列と照合（substring match）
3. マッチした単語の box 上に小さい黒矩形を描画
4. 最大 4 パスで再 OCR（長い URI 等の tokenisation ばらつき対策）
5. AWS console 画像は右上のアカウントウィジェット領域を常時マスク
6. HTML preview mock も OCR 対象（S3 URI 等に account ID が埋まっているため）

**UI/UX 保持率**: おおむね 99% 以上。ステータスバー・表・ナビ・タブ等は可視。
黒塗りされるのは `SENSITIVE_STRINGS` に列挙された特定トークンのみ。

---

## 5. 検証 (mandatory — Rule E)

マスク実行後、必ず OCR ベースのリークチェッカを走らせて 0 leak を確認する。

```bash
python3 scripts/_check_sensitive_leaks.py
# 期待出力:
#   Scanned: NNN masked images
#   Images with detectable sensitive substrings: 0
```

1 件でも leak が検出された場合:
- まず `scripts/_sensitive_strings.py` に該当文字列を追加
- `python3 scripts/mask_uc_demos.py <該当フォルダ>` で再マスク
- originals がないファイルは `python3 scripts/_inplace_ocr_mask.py <該当 PNG>` で
  in-place マスク
- 再度 `_check_sensitive_leaks.py` で 0 leak を確認

---

## 6. コミット前チェックリスト

- [ ] `scripts/_sensitive_strings.py` が `git check-ignore` で ignored 判定
- [ ] `python3 scripts/_check_sensitive_leaks.py` の出力が **0 leak**
- [ ] 追加した PNG が `docs/screenshots/masked/` 配下
- [ ] 必要なら `docs/screenshots/originals/` にも配置（originals は任意、
      gitignore していないので公開 repo に入る。originals にも OCR マスクを
      適用することで「元画像も公開可」状態を保つ）
- [ ] 対応する `demo-guide.md` / README の UI/UX セクションを更新（画面枚数、
      主な画面内容、掲載場所）
- [ ] 1 コミット = 1 論理単位（例: UC ごと、phase ごと）

---

## 7. Deep scan (任意)

OCR 単一パスで見えないリークを網羅的に確認したい場合、PSM モード 4 種を
試行する `_deep_scan.py` を使う（時間がかかる）:

```bash
cp scripts/_check_sensitive_leaks.py.example scripts/_deep_scan.py
# _deep_scan.py を編集して PSM_MODES = [3, 6, 11, 12] のループにする
# (元の _deep_scan.py テンプレート化は Phase 8 roadmap)

python3 scripts/_deep_scan.py
# 20-30 分 (116 枚 x 4 PSM)
```

通常は 6 (`_check_sensitive_leaks.py`) で十分。PR マージ前の最終チェックとして
deep scan を推奨。

---

## 8. 既知の制約・注意点

### 8-1. OCR 言語
- 必ず `lang="eng+jpn"` を使う。`eng` 単独だと日本語ラベル横の英数字トークンを
  見逃す場合あり (2026-05-11 検証で phase1-fsx-filesystem-detail.png と
  phase7-uc15-s3-satellite-uploaded.png で実際に発生)

### 8-2. HTML preview mock
- v6 では `copy-as-is` 扱いだったが、実体では S3 URI (`s3://bucket-<account_id>/`)
  が rendered されて account ID がリークしていた
- v7 ではすべての HTML preview も OCR マスク対象

### 8-3. ステップ関数 Graph view
- ノード ID / リソースパスに ARN 要素が含まれる場合あり
- graph 内で見える範囲（execution ARN header, IAM role ARN）が対象

### 8-4. Originals の扱い
- `docs/screenshots/originals/` は **gitignored ではない**（公開 repo に含まれる）
- 理由: マスクの再現性保証、将来の再マスクのため
- したがって originals 自体にも機微文字列が含まれないこと（= 上記 OCR マスクで
  検出される語は originals にも無い、もしくは `_sensitive_strings.py` に
  登録済み）が望ましい
- 実運用では OCR マスクは masked/ のみに適用、originals はマスクしない運用で OK
  （originals は **個人の判断で OCR マスク対象外のスクショだけ** を置く）

---

## 9. Troubleshooting

### 9-1. `OCR failed: ...`
- tesseract / tesseract-lang が未インストール
- `brew install tesseract tesseract-lang` で解消

### 9-2. Leak が残る
- 対象文字列が `_sensitive_strings.py` にない → 追加
- OCR が当該単語を認識できていない → PSM モード変更 (`_deep_scan.py` 相当) で再試行
- それでも駄目な場合 → 手動マスク (macOS Preview で黒矩形)

### 9-3. マスク後のファイルサイズが急増
- v6 では grey 大矩形で圧縮が効いていた
- v7 は UI 要素が visible に戻るので PNG サイズが大きくなる（2〜5倍）
- 想定内の挙動

---

## 10. 関連ドキュメント

- `scripts/mask_uc_demos.py` — v7 OCR マスク本体
- `scripts/_check_sensitive_leaks.py.example` — 検証ツール template
- `scripts/_inplace_ocr_mask.py.example` — in-place マスク template
- `scripts/_sensitive_strings.py.example` — 機微リテラル template
- `docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md` — 並行スレッド間の
  マスク運用ルール（別スレッドで記述中）
- `docs/screenshots/uc-industry-mapping.md` — UC と業種の対応表（同上）

---

## Appendix A: v6 からの移行履歴

v6 (2026-05-10 以前) は「AWS console の main content area を grey 大矩形で
まとめて隠す」safe-by-default 方針。結果として UI/UX のほとんどが覆われ、
PR レビュアーが画面を見られない問題があった。

v7 (2026-05-11, PR #2) は OCR で word-level bounding box を検出し、
特定の機微トークンのみを小さい黒矩形で塗る方針に変更。UI は 99% 以上 visible、
機微情報のみピンポイントで redacted。

v6 → v7 の切り替え時 (PR #2) に、全 116 masked images の再マスク実施。
検証は `_check_sensitive_leaks.py` で 0 leak を確認済み。
