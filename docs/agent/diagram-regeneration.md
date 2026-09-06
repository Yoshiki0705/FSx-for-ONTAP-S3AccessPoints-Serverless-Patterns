# 構成図の作成と再生成

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/skills/diagram-regeneration/SKILL.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## Architecture Diagrams (draw.io + Official AWS Icons)

> 詳細ルールはユーザーレベル Kiro global steering `global-architecture-diagram-standards.md` を参照。
> ここはこのリポジトリ固有のパス・コマンドと、必ず守る最小セット。

### Layout

```
docs/diagrams/                     # すべて生成物（手編集禁止 / spec は scripts/ 側）
├── architecture-overview.drawio            # Part1
├── amplify-vpc-split.drawio
├── nextcloud-external-storage.drawio
├── coexistence-3path.drawio
├── part2-*.drawio / part3-*.drawio        # Part2・3
├── *-en.drawio                            # spec を翻訳して生成
└── dark/*.drawio                          # ライト版から派生
docs/images/            *.svg              # ライト。GitHub docs 用（相対パス参照）
docs/images/            *-dark.svg         # ダーク
docs/images/png/        *@2x.png           # ライト。ブログ用（絶対 raw URL 参照）
docs/images/png/        *-dark@2x.png      # ダーク
```

### テーマ（ライト = 既定 / ダーク = 併記）

全図を 2 テーマで公開する。**ライトが既定**で、README・docs・ブログに表示するのは常にライト版。ダーク版は同じ内容の選択肢として、図ごとにリンクを併記し、[構成図インデックス](../architecture-diagrams.md)（JA / EN）に一覧を置く。

ダーク版は CSS ではなく**別ソースとして生成する**。draw.io の SVG は `light-dark()` で自前の配色を反転させるが、埋め込み済み AWS アイコンは追随しない（実測: 24 要素中 0 個）。反転だけでは濃紺の線画が黒背景に乗って判読不能になるため、`Res_*_48_Light` → `Res_*_48_Dark`（白い線画）へアイコン素材ごと差し替える。`Arch_*` サービスアイコンは公式に単色タイル 1 種類のみなので両テーマ共通。

エクスポート後は `scripts/pin-svg-theme.py` が `light-dark()` を第 1 引数（= ソースが指定した配色）に解決し、閲覧環境のダークモード設定で勝手に反転しないよう固定する。ライトソースならライト、ダークソースならダークに固定される。

### 単一の生成系統

全図の唯一のソースは `scripts/build-diagrams.py` の宣言的 spec。JA と EN は同じ spec から
生成され、EN は同スクリプトの `EN` 辞書を `translate_diagram()` に渡して spec ごと翻訳する。
**`docs/diagrams/` 配下の `.drawio` は生成物なので直接編集してはいけない**（次回生成で上書き
される）。編集対象はスクリプトだけ。

spec レベルで翻訳するのは、**EN ラベルは JA より幅が広く、レイアウト検査を EN でも再実行する
必要があるため**。完成 XML への文字列置換ではラベル衝突が無言で残る（実際に `agent-teams` の
EN ステップラベルが桁溢れし、`check_edge_labels` が検出した）。

Part1 の 4 図は 2026-09 まで手書き XML で、`apply-official-aws-icons.py` がアイコンを流し込み
`generate-en-diagrams.py` が文字列置換で EN を作っていた。この 2 本は削除済み。手書きだったこと
自体が読めなさの原因で、AI サービス 5 個を横並びに描いたまま幅が 2214px まで伸び、880px の
カラムに入れるとラベルが 4.4px になっていた。spec に移して各図を 1 ボックスへ抽象化した結果、
4 図とも 982〜1010px = 実効 14.8px 以上に収まっている。

### Commands

```bash
# 1. 公式アイコンパッケージを取得（リポジトリ外に展開すること）
#    現行版の URL は必ず https://aws.amazon.com/architecture/icons/ から再取得
curl -s https://aws.amazon.com/architecture/icons/ | grep -oE 'https://[^"]*Icon-package[^"]*\.zip'
unzip -q Icon-package_*.zip -d /tmp/awsicons -x '__MACOSX/*'

# 2. 全図: spec から JA + EN を生成（レイアウト検査は EN でも再実行）
python3 scripts/build-diagrams.py --icon-root /tmp/awsicons

# 3. ダークテーマのソースをライト版から生成（アイコン素材ごと差し替え）
python3 scripts/make-dark-diagrams.py --icon-root /tmp/awsicons

# 4. ライト + ダークを SVG + PNG@2x にエクスポート（テーマ固定まで実行される）
bash scripts/export-diagrams.sh

# 5. 目視確認用に 2000px 以下へ縮小（エージェントが読める形にする）
python3 scripts/preview-diagram.py            # 全 part2/part3
python3 scripts/preview-diagram.py part3-agentchat-modes
python3 scripts/preview-diagram.py --glob 'docs/images/png/*-dark@2x.png' --out-dir /tmp/dark-previews
```

`build-diagrams.py` と `make-dark-diagrams.py` は冪等。spec を編集したら 2→3→4→5 を順に再実行する。**ダーク生成（3）はライト版の変更後に必ず実行する**（漏れはコミット前に `make-dark-diagrams.py --icon-root <dir> --check` を走らせると exit 1 で検出できる。アイコンパッケージはリポジトリに含めないため CI では実行できない = ローカルでの確認が必須）。
`docs/diagrams/` 配下のすべての `.drawio`（`-en`、`dark/` を含む）は生成物。直接編集してはいけない。

### 必ず守る最小セット

| 項目 | ルール |
|------|--------|
| アイコン世代 | 公式 Asset Package の現行四半期版のみ。draw.io 同梱 `mxgraph.aws4` は 2019 世代なので使わない |
| サイズ | サービス 80×80（`Arch_*_64.svg` の native）、リソース 48×48（`Res_*_48.svg`）。リスケール禁止、混在禁止 |
| ラベル | 公式サービス名 + `Amazon`/`AWS` 前置を必須。略称禁止（`ALB` → `Elastic Load Balancing`）。2 行以内 |
| ラベル例外 | 非 AWS 要素（`Web ブラウザ` / `NFS クライアント` / `Nextcloud` 等）は前置不要 |
| 矢印 | 単色プリセット Open Arrow のみ（`endArrow=open;endFill=0;strokeColor=#232F3E`）。色分け・線幅変更・破線での意味付けは禁止 |
| 注記 | `補足` 見出し + `※1`/`※2`（EN は `*1`/`*2`）。太字見出し（体言止め）+ 次行に詳細。段落文で書かない |
| 検証 | `ET.parse()` 通過だけでは不十分。**必ず PNG をレンダリングして目視確認**（JA/EN 個別に） |
| 目視の手順 | `@2x` PNG は 2000px を超えるためエージェントが直接読めない。`scripts/preview-diagram.py` で縮小してから読む（`/tmp` 出力。コミットしない） |
| 一括目視 | 枚数が多いときはコンタクトシートを 1 枚作る。6 列 × 300px セルなら 2000px 制限に収まる（5 列 × 370px は 2358px で拒否された） |
| テーマ | ライトが既定。図を追加・変更したらダーク版も同時に更新し、表示側にはライトを出してダークをリンクで併記する |
| ダークの配色 | アイコンは `Res_*_48_Dark` に差し替え。背景・面・文字は `make-dark-diagrams.py` の `PALETTE` に集約（個別図でハードコードしない） |
| 公開 | アイコン素材そのものをリポジトリにコミットしない（埋め込み済み完成図のみ可） |

### Common Pitfalls（このリポジトリで実際に踏んだもの）

| Pitfall | Solution |
|---------|----------|
| `xml.sax.saxutils.escape()` が `"` をエスケープせず XML 破損 | HTML 属性は単引用符にし、`escape(s, {'"': '&quot;'})` を使う。または定数を事前エスケープ済み文字列にする |
| XML 破損時 drawio が該当セル以降を無言で捨てる（export は成功する） | 書き込み後に `ET.parse()` ゲート必須。さらに PNG 目視 |
| スクリプトが「N 個追加」と報告するが実際は未挿入 | 構築したリストを数えず、出力に `id="..."` が存在するかを検証する |
| エッジラベルが中点に置かれアイコンに重なる | `<mxGeometry x="-0.4" relative="1">` + `<mxPoint as="offset" y="16"/>` で退避。縦線は `x` オフセット |
| アイコン拡大でラベル衝突 | 座標をスケール。横は長い公式名のため 1.6 前後必要、縦は 1.25 程度に圧縮（非対称スケール） |
| EN ラベルが JA より長く衝突 | EN 版は個別にレンダリング確認する。Part2/3 は spec ごと翻訳して EN でも検査を再実行する（`translate_diagram()`） |
| 画像読み込みが `image dimensions exceed max allowed size ... 2000 pixels` で失敗 | `@2x` エクスポートは長辺 2000px 超が普通。`python3 scripts/preview-diagram.py <name>` で縮小コピーを作り、そちらを読む。**PNG を直接読もうとしてセッションを落とさない** |
| 縦線のエッジラベルがノードラベルの 3 行目に見える | アイコンのラベルは真下に描かれ縦線の経路上にある。`vertical_label_shortfall()` が自動で下へ退避（`check_vertical_edge_labels` が明示 `at`/`dy` の取り違えを検出） |
| 注記が枠外へはみ出す / 枠が足りない | `whiteSpace=wrap` はエクスポート時に効かない。`_wrap_note()` で明示改行し、枠高は折り返し後の行数から算出する |
| CJK の折り返しで `の` 直後の半角スペースが消える | トークン化で「CJK 1 文字 + 後続スペース」を 1 トークンにする。`findall` の選択肢から漏れた空白は落ちる |
| ダーク版で AWS リソースアイコンが見えない | `Res_*_48_Light`（濃紺の線画）が残っている。`make-dark-diagrams.py` を通して `Res_*_48_Dark` に差し替える |
| SVG が閲覧環境のダークモードで勝手に反転する | `pin-svg-theme.py` 未適用。draw.io は `light-dark()` + `color-scheme: light dark` を出力するため、固定しないと配色が反転する（アイコンだけ追随せず判読不能になる） |
| ライト版を直したのにダーク版が古い | `make-dark-diagrams.py` の再実行漏れ。コミット前に `--check` を走らせると exit 1 で検出できる（アイコンパッケージが必要なので CI では代替できない） |
| 対角のエッジが中間セルを貫通し、矢印が無関係なアイコンに当たる | builder は直交ルーティングするため、対角の指定は「横に折れてから縦に折れる」経路になり間のセルを通る。**全エッジを隣接セル間の水平・垂直のみに限定する**。結果として中心ノードに引ける本数は上下左右の 4 本が上限で、5 本目が必要になったら要素を削るか行を増やす（削った要素の役割は注記に残す） |
| 1 つのノードから複数行へ分岐させるとラベルが消える | 分岐した 2 本が同じ水平区間を共有し、後から描いたラベルが先のラベルを覆う。**行ごとにソースのセルを複製する**（同じ移行元を 2 つ置く）。図としての重複より、経路名が読めることを優先する |
| `drawio` が PATH にない（macOS） | `/Applications/draw.io.app/Contents/MacOS/draw.io` を直接呼ぶ |
| ヘルパースクリプトを別ディレクトリへ移動して repo root 解決が壊れる | `dirname` からの相対階層を見直し、ソースディレクトリ存在チェックを入れる |
| ブログの画像が 404 | ブログは `raw.githubusercontent.com/.../main/...` 参照。`docs/images/` を main に push してから公開する |
| ラベル変更後に alt text が古いまま | alt text は図の記述なので公式サービス名に追随させる（本文プロースの機能名はそのままでよい） |

## ラベルサイズの下限

図のラベルは、画像が読者のカラム幅に縮小された**後**の大きさで表示される。したがって
`fontSize` の値だけでは可読性を判定できない。下限と、収まらないときの手順、既存の負債は
[diagram-label-size](diagram-label-size.md) にある。**キャンバスを広げると必要な
`fontSize` が上がる**ので、幅を決めるときに一緒に読むこと。
