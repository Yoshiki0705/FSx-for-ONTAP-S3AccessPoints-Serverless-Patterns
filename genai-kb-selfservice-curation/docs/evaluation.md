# UC29 RAG 品質評価（GENOPS01）

Well-Architected 生成AIレンズ GENOPS01-BP01「定期的な機能評価」に沿い、RAG の品質を
ground truth と評価基準に対して定期測定する。本書は評価の観点と最小データセットを提供する。

> 評価は特定データセットでの相対比較。スコアは sizing/品質傾向の参照であり保証値ではない。

## 評価観点

| 観点 | 指標 | 説明 |
|------|------|------|
| Retrieval 適合率 | 期待引用元が上位に含まれる割合 | 質問に対し正しいソースを取得できるか |
| Citation 整合 | 回答の根拠が引用元に存在する割合 | ハルシネーション抑制 |
| No-answer 挙動 | 情報不足時に「分からない」と返す割合 | 推測回答の抑制 |
| 権限/ロール フィルタ精度 | role フィルタ時に他ロール文書を出さない割合 | メタデータフィルタの正しさ |
| レイテンシ | p50/p95/p99 | 体感性能 |

## 評価データセット

`evaluation/uc29-eval-dataset.json` に質問と期待引用元（ファイルパス）を定義。
各質問を Query Lambda に投げ、citations に期待ソースが含まれるかを判定する。

## 実行方法（概念）

```bash
# 各質問を Query Lambda に投げ、citations を期待値と突合（簡易ハーネスは別途）
for q in $(jq -c '.cases[]' evaluation/uc29-eval-dataset.json); do
  query=$(echo "$q" | jq -r '.query')
  aws lambda invoke --function-name <QueryFn> \
    --payload "{\"query\": \"$query\"}" --cli-binary-format raw-in-base64-out out.json >/dev/null
  # out.json の citations に expected_source が含まれるか判定
done
```

## マネージド評価の推奨

- **Amazon Bedrock Knowledge Base 評価ジョブ**: retrieval/retrieve-and-generate の品質を
  マネージドで評価（ground truth 比較、メトリクス出力）
- **RAGAS** 等の OSS フレームワークを CI/定期ジョブで実行
- 重要回答は citation 必須、根拠がない場合は no-answer を返すことを評価基準に含める

## 注意

- 評価データは架空・マスク済みのサンプル。実データでの評価は別途実施
- メタデータフィルタ（role）評価は `.metadata.json` 投入＋再同期後に有効
