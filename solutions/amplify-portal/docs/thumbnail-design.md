# ファイル一覧のサムネイル — 設計と制約

🌐 **Language / 言語**: **日本語** | [English](thumbnail-design.en.md)

一覧の行に画像のサムネイルを出す機能の設計。素朴な実装が高くつく理由と、実際に採った経路を残す。

## 要件

- 一覧の行で画像の中身が分かること
- ファイル 1 件あたりの Lambda 呼び出しを増やさないこと
- スマートフォン（セルラー回線）で開いても転送量が増えないこと
- 1 件でも扱えないファイルがあったときにページ全体が壊れないこと
- 一覧と同じ認可境界の内側で動くこと

## 素朴な実装を採らなかった理由

`<img>` に presigned URL を入れるのが最短だが、2 つの費用がかかる。

| 素朴な実装 | 費用 |
|---|---|
| ファイルごとに presigned URL を取る | 100 件のページで **Lambda 呼び出しが 100 回**増える |
| 原本をそのまま `<img>` に渡す | 48px の表示のために**原本を全部ダウンロード**する。20MB の写真なら 20MB |

2 つ目がスマートフォンでは特に効く。サムネイルのために原本を落とすなら、サムネイルは無いほうが速い。

## 採った経路

生成をバックエンドに寄せ、**1 ページ 1 回**の呼び出しにする。

```
FileExplorer（1 ページ分のキーをまとめる）
  └─ thumbnailQuery / getThumbnails（1 回）
       └─ ThumbnailsFunction（Pillow）
            ├─ HeadObject で ETag とサイズを確認（S3 AP 経由）
            ├─ キャッシュに有れば presign して返す
            └─ 無ければ GetObject → 縮小 → JPEG → キャッシュへ PUT → presign
```

| 要素 | 実体 |
|---|---|
| エンドポイント | `thumbnailQuery`（action は `getThumbnails` のみ） |
| Lambda | `functions/thumbnails/handler.py`、1024MB / 60s、ARM64 |
| レイヤー | `PillowLayer`（Pillow）と `SharedPythonLayer`（認可境界） |
| キャッシュ | `ThumbnailCacheBucket`、30 日で失効 |
| フロント | `src/hooks/useThumbnails.ts` → `FilePreview` の `thumbnailUrl` |

### なぜ一覧の Lambda に action を足さなかったか

`fileQuery` と `fileMutation` はどちらも一覧の Lambda（`ListFilesLambdaDataSource`）に束ねられている。ここに action を足すと**生成が一覧用 Lambda の中で走る**。6MB のレイヤーとメモリ増が、サムネイルと関係のない全ての一覧のコールドスタートに乗る。ZIP 生成が別 Lambda になっているのと同じ理由で分けた。

### キャッシュキーに ETag を含める理由

キーが「オブジェクトのパス」だけだと、ファイルを差し替えても**前の絵を出し続ける**。キャッシュキーは
`sha256(AP エイリアス + キー + ETag + 一辺のピクセル数)` なので、内容が変われば別のエントリになる。AP エイリアスを含めるのは、同じキーが 2 つの Access Point の下では別のオブジェクトだからである。

### 認可

このエンドポイントは**クライアントからオブジェクトキーを受け取る**。したがって一覧と同じ境界を通す必要がある。`shared.portal_path_scope`（`reject_key` / `allowed_prefixes`）を一覧・エージェントと共有しており、呼び出し元のグループの prefix 外のキーは **HeadObject の前に**拒否する。読み取り後に拒否すると、拒否そのものが「そのオブジェクトが存在するかどうか」を漏らす。

`groups` は resolver が検証済みトークンから入れる。リクエスト本文からは受け取らない。

### 生成しない条件と、しなかったときの見え方

「1 件のせいでページが壊れる」を避けるため、扱えないものは `skipped` に理由を入れて返し、その行は従来のアイコンのままにする。

| 条件 | 挙動 |
|---|---|
| 対応していない拡張子 | ダウンロードせずに skip |
| 25MB 超（既定値） | ダウンロードせずに skip |
| 拡張子は画像だが中身が違う | skip（`not a readable image`） |
| 4,000 万画素超 | Pillow が拒否。小さいファイルが巨大な寸法を主張する形の防御 |
| 1 回あたりの生成上限（12 件）超 | `pending` で返し、フロントが数秒後に再要求 |

`pending` があるのは、タイムアウトさせないため。100 件がすべてキャッシュミスのフォルダを 1 回で処理しようとすると 60s に収まらず、**それまでに生成した分も失われる**。

### サムネイルに EXIF を持ち越さない

縮小した画像を新しい JPEG として保存するので、メタデータは引き継がれない。スマートフォンが記録した撮影場所が、行を見られる全員に配られる絵の中に残らない。回転（Orientation）だけは**破棄する前にピクセルへ適用**する。適用しないと縦写真が横向きのまま出る。

## Pillow を入れた判断

このリポジトリで最初のサードパーティ Python 依存になる。

- **Docker を使わない**。`pip install --target --platform manylinux2014_aarch64 --python-version 3.13` で ARM64 の wheel を展開する。レイヤーのビルドがラップトップで動く状態を壊さない
- **バージョンは 1 か所**。`functions/thumbnails/requirements.txt` が唯一の出所で、CDK はそこから読む。`requirements-dev.txt` も同じ版に固定し、`scripts/tests/test_thumbnail_pins_agree.py` が一致を検査する。テストが本番と違う Pillow で画像をデコードしていたら、それは別のものを検査している
- **12.2.0**。cp313 の manylinux2014_aarch64 wheel がある最新版。wheel が無い版は Docker 無しでは staging できない

代替案として「JPEG に埋め込まれた EXIF サムネイルの抽出のみ（標準ライブラリだけ）」も検討した。スマートフォンやカメラの写真には当たるが、PNG やスクリーンショットは対象外になり「一部の画像だけ絵が出る」状態になるため採らなかった。自前の画像デコーダを書く案は、未検証の入力を解析する面と保守性から採らない。

## コスト

| 項目 | 目安 |
|---|---|
| 生成 | 1 画像あたり Lambda 1024MB × 数百 ms。同じ ETag なら 2 回目以降は生成しない |
| キャッシュ保管 | サムネイル 1 件で数十 KB。30 日で失効 |
| 呼び出し回数 | 1 ページ 1 回（+ `pending` があれば数回） |

金額は時点情報なので、見積りを出すときは Pricing API で確認する。

## 制約（未対応）

- **SVG は対象外**。Pillow がラスタライズしないため。`FilePreview` が「開ける」形式の一覧とは別のリストを持っており、`tests/hooks/useThumbnails.test.ts` が両者の一致を検査している
- **RAW と EXR は対象外**。Pillow が読めない、またはこのレイヤーに無いプラグインを要する
- **動画のサムネイルは無い**。フレーム抽出は別の依存（ffmpeg）になる
- **実機での見た目は未確認**。ユニットテストは通っているが、実 ONTAP のフォルダに対する表示は確認していない

## 参考

- 一覧側の認可境界: `shared/portal_path_scope.py`
- 生成の上限とその理由: `functions/thumbnails/handler.py` の冒頭
- 呼び出し回数の検査: `tests/hooks/useThumbnailsBatching.test.tsx`
