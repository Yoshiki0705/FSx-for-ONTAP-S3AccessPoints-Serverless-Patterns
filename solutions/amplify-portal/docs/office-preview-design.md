# Office ファイルプレビュー — 設計調査と選択肢

## 要件

ポータルの「All Files」セクションで `.docx`, `.xlsx`, `.pptx`, `.pdf` をブラウザ内でプレビューしたい。現在は Presigned URL 経由のダウンロードのみ（画像ファイルはインラインプレビュー済み）。

## 選択肢比較

| アプローチ | コールドスタート | コスト | 制約 | 推奨度 |
|-----------|:---:|------|------|:---:|
| **A. Lambda Container Image + LibreOffice** | 3-8s (初回) | ~$0.002/変換 | イメージサイズ ~500MB、x86_64 のみ | ⭐⭐⭐ |
| **B. Lambda Layer (Brotli 圧縮)** | 1-2s (解凍) | ~$0.001/変換 | 250MB 制限に収まる (95MB 圧縮) | ⭐⭐⭐ |
| **C. Textract → テキスト表示** | 0.5s | $1.50/1000 ページ | テキスト + テーブルのみ（レイアウト消失） | ⭐⭐ |
| **D. クライアントサイド (pdf.js + docx-preview)** | 0s | $0 | PDF/DOCX のみ、xlsx 非対応 | ⭐⭐ |
| **E. 外部 SaaS (CloudConvert, etc.)** | 0s | $0.01/変換 | データが外部に送信される（コンプライアンス問題） | ⭐ |

## 推奨: B → D のハイブリッドアプローチ

### Phase 1（即時対応可能）: クライアントサイドプレビュー

コストゼロ、Lambda 追加不要。ブラウザ内で直接レンダリング:

| ファイル形式 | ライブラリ | サイズ | 備考 |
|------------|-----------|------|------|
| PDF | [pdf.js](https://mozilla.github.io/pdf.js/) (Mozilla) | 350KB | 業界標準、Canvas レンダリング |
| DOCX | [docx-preview](https://github.com/nicholasguo/docx-preview) | 80KB | XML → HTML 変換 |
| XLSX | — | — | クライアントサイドでは困難 |
| PPTX | — | — | クライアントサイドでは困難 |

**実装イメージ**:
```typescript
// FilePreview.tsx
if (key.endsWith(".pdf")) {
  const url = await getPresignedUrl(key);
  return <iframe src={url} style={{ width: "100%", height: "600px" }} />;
}
if (key.endsWith(".docx")) {
  const blob = await fetch(presignedUrl).then(r => r.blob());
  renderAsync(blob, previewContainer); // docx-preview
}
```

**トレードオフ**:
- PDF: Presigned URL を `<iframe>` に渡すだけ（ブラウザ内蔵ビューアで表示）
- DOCX: レイアウト再現度は 70-80%（複雑なスタイルは崩れる）
- XLSX/PPTX: このアプローチでは非対応

### Phase 2（将来）: Lambda Container Image + LibreOffice

XLSX/PPTX 対応が必要になった場合:

```dockerfile
FROM ghcr.io/shelfio/libreoffice-lambda-base-image:node20-x86_64-26.2-01

COPY handler.py ${LAMBDA_TASK_ROOT}
CMD ["handler.handler"]
```

- [shelfio/libreoffice-lambda-base-image](https://github.com/shelfio/libreoffice-lambda-base-image): LibreOffice 26.2、Python 3.12/3.13 対応
- Container Image なので 250MB Layer 制限を回避（最大 10GB）
- x86_64 のみ（ARM64 は LibreOffice が対応していない）
- コールドスタート: 3-8 秒（Provisioned Concurrency で緩和可能）

**フロー**:
```
Browser → AppSync → Lambda (Container, x86_64)
                      ↓
                S3 AP GetObject (Office ファイル取得)
                      ↓
                LibreOffice --convert-to pdf
                      ↓
                S3 PutObject (PDF を一時バケットに保存)
                      ↓
                Presigned URL → Browser (<iframe>)
```

## Lambda Layer サイズ問題の詳細

| 制約 | 値 |
|------|-----|
| Lambda Layer 合計上限 (解凍後) | 250 MB |
| Lambda Container Image 上限 | 10 GB |
| Lambda /tmp ディレクトリ | 512 MB (最大 10 GB に拡張可能) |

[shelfio/libreoffice-lambda-layer](https://github.com/shelfio/libreoffice-lambda-layer) は Brotli 圧縮で **95 MB** に収めており、Layer 制限内に収まります。ただし:
- 実行時に /tmp に解凍 → 1-2 秒のオーバーヘッド
- Python 3.12 ARM64 では動作しない（x86_64 ビルドのみ）
- **このプロジェクトの Lambda は ARM64 統一** → Layer アプローチは互換性なし

→ Container Image (x86_64) が現実的な選択肢。

## 現時点の判断

**Phase 1 (クライアントサイド PDF + DOCX) を実装する。**

理由:
1. コストゼロ、追加インフラ不要
2. PDF はプレビュー需要の 80%+ をカバー
3. ARM64 統一ポリシーを維持できる
4. Container Image は XLSX/PPTX の明確な需要が出てから

## 実装タスク (Phase 1)

- [ ] `npm install docx-preview` (DOCX レンダリング)
- [ ] `FilePreview.tsx` に PDF iframe + DOCX preview 分岐を追加
- [ ] 対応形式: `.pdf` (iframe), `.docx` (docx-preview), 画像 (既存 Presigned URL)
- [ ] 非対応形式: ダウンロードリンク表示 (現状維持)
- [ ] サイズ上限: 10MB 超は「ファイルが大きすぎます」表示

## 参考

- [shelfio/libreoffice-lambda-layer](https://github.com/shelfio/libreoffice-lambda-layer) — 95MB Brotli 圧縮 Layer
- [shelfio/libreoffice-lambda-base-image](https://github.com/shelfio/libreoffice-lambda-base-image) — Container Image ベース
- [docx-preview](https://github.com/nicholasguo/docx-preview) — クライアントサイド DOCX レンダリング
- [pdf.js](https://mozilla.github.io/pdf.js/) — Mozilla PDF レンダラー
