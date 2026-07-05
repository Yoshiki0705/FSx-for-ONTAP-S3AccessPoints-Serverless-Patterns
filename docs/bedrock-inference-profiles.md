# Amazon Bedrock 推論プロファイル ガイド / Inference Profile Guide

> このドキュメントは、本リポジトリの各パターンが Amazon Bedrock を呼び出す際の
> **モデル ID / クロスリージョン推論プロファイル / IAM / データレジデンシー** に関する
> 共通ガイダンスです。各パターンの `BedrockModelId` パラメータ説明からここへリンクしています。

---

## 日本語

### なぜ推論プロファイルが必要か

Amazon Nova（`amazon.nova-lite-v1:0` 等）や新しい Claude モデルは、**オンデマンドではベアな
モデル ID を直接呼び出せません**。次のエラーになります。

```
ValidationException: Invocation of model ID amazon.nova-lite-v1:0 with on-demand throughput
isn't supported. Retry your request with the ID or ARN of an inference profile that contains
this model.
```

これらのモデルは **クロスリージョン推論プロファイル ID**（geo 接頭辞付き）で呼び出します。

| リージョン系 | 接頭辞 | 例 |
|---|---|---|
| アジアパシフィック | `apac.` | `apac.amazon.nova-lite-v1:0` |
| 米国 | `us.` | `us.amazon.nova-lite-v1:0` |
| 欧州 | `eu.` | `eu.amazon.nova-lite-v1:0` |

本リポジトリの既定は **主要デプロイ先(ap-northeast-1 系)に合わせて `apac.`** です。
他リージョンにデプロイする場合は `BedrockModelId` を該当接頭辞に変更してください。

### 前提条件: モデルアクセスの有効化

推論プロファイルが利用する各リージョンで、対象モデルの **モデルアクセスを有効化** してください
（Bedrock コンソール → Model access）。有効な推論プロファイル ID は次で確認できます。

```bash
aws bedrock list-inference-profiles --region <your-region> \
  --query "inferenceProfileSummaries[].inferenceProfileId" --output table
```

### IAM 要件

推論プロファイル経由の呼び出しには、**推論プロファイル ARN** と、プロファイルが
ルーティングする **各リージョンの foundation-model ARN** の両方に対する `bedrock:InvokeModel`
権限が必要です。本リポジトリの各テンプレートは次の形で付与しています。

```yaml
- Sid: BedrockInvokeModel
  Effect: Allow
  Action:
    - bedrock:InvokeModel
  Resource:
    - !Sub "arn:aws:bedrock:*::foundation-model/*"
    - !Sub "arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/*"
```

### ⚠️ データレジデンシー / データ主権(重要)

クロスリージョン推論プロファイルは、**geo 内の複数リージョンにリクエストをルーティング**します
（例: `apac.` はデプロイリージョン以外の APAC リージョンへ転送されうる）。規制・データ主権要件の
あるワークロードでは、**推論データがデプロイリージョン外で処理される可能性**を必ず評価してください。

代替オプション:

- **リージョン内 Provisioned Throughput** を購入し、そのモデル ARN を `BedrockModelId` に指定する。
- **Bedrock VPC エンドポイント(PrivateLink)** を使い、Bedrock トラフィックをプライベート経路に限定する
  （生成系 Lambda は VPC-external のため、必要に応じて VPC 構成を追加）。
- 対象リージョンで **ベア ID のオンデマンド呼び出しに対応するモデル** を選ぶ。

監査は不変です。`CloudTrail` と Bedrock の **model invocation logging** で呼び出しを追跡できます。

### CI による強制

`scripts/check_bedrock_inference_profile.py`（CI の "Bedrock inference-profile guard"）が、
**テンプレートの既定値**（ベアな Nova/Claude ID の禁止 + `inference-profile` ARN を含む IAM）に加えて、
**README のパラメータ表/CLI 例** に残ったベア ID も検出します。許可リストは空で、全 Bedrock 利用パターンに
対して常時強制されます。

### 検証レベル

| レベル | 手段 | ネットワーク | CI |
|---|---|---|---|
| 静的（テンプレート/README） | 上記 guard + cfn-lint | 不要 | 常時 |
| Converse 契約（リクエスト/レスポンス形状） | `shared/tests/test_bedrock_helper_contract.py`（botocore Stubber で実サービスモデル検証） | 不要 | 常時 |
| ライブ E2E（実呼び出し） | `scripts/bedrock_inference_profile_smoke.py`（オプトイン） | **要**・課金あり | 手動のみ |

ライブ確認例（認証情報とモデルアクセスが必要、少額課金あり）:

```bash
python3 scripts/bedrock_inference_profile_smoke.py \
  --model-id apac.amazon.nova-lite-v1:0 --region ap-northeast-1
```

### コスト注記

- 本リポジトリのサンプル既定は **コスト優先で `nova-lite`** です。品質要件がある場合は
  `nova-pro` や Claude 系へ変更してください（Sample run vs Production estimate を区別）。
- クロスリージョン推論のデータ転送は、**テキスト用途では一般に軽微**です。実コストは
  トークン量・モデル・リージョンで変動します。[Cost Calculator](cost-calculator.md) を参照。

---

## English

### Why an inference profile is required

Amazon Nova (e.g. `amazon.nova-lite-v1:0`) and newer Claude models **cannot be invoked on-demand
by the bare model ID**. Doing so fails with:

```
ValidationException: Invocation of model ID amazon.nova-lite-v1:0 with on-demand throughput
isn't supported. Retry your request with the ID or ARN of an inference profile that contains
this model.
```

Invoke them with a **cross-region inference profile ID** (geo prefix):

| Region group | Prefix | Example |
|---|---|---|
| Asia Pacific | `apac.` | `apac.amazon.nova-lite-v1:0` |
| United States | `us.` | `us.amazon.nova-lite-v1:0` |
| Europe | `eu.` | `eu.amazon.nova-lite-v1:0` |

This repository defaults to **`apac.`** to match the primary deployment region family (ap-northeast-1).
When deploying elsewhere, set `BedrockModelId` to the profile ID for your region.

### Prerequisite: enable model access

Enable **model access** for the target model in every region the inference profile spans
(Bedrock console → Model access). List valid inference profile IDs with:

```bash
aws bedrock list-inference-profiles --region <your-region> \
  --query "inferenceProfileSummaries[].inferenceProfileId" --output table
```

### IAM requirements

Invoking through an inference profile requires `bedrock:InvokeModel` on **both** the
**inference-profile ARN** and the **cross-region foundation-model ARNs** the profile routes to.
Each template in this repository grants:

```yaml
- Sid: BedrockInvokeModel
  Effect: Allow
  Action:
    - bedrock:InvokeModel
  Resource:
    - !Sub "arn:aws:bedrock:*::foundation-model/*"
    - !Sub "arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/*"
```

### ⚠️ Data residency / sovereignty (important)

A cross-region inference profile **routes requests across multiple regions within the geo**
(e.g. `apac.` may forward to APAC regions other than your deployment region). For regulated or
data-sovereignty-sensitive workloads, evaluate whether inference data may be **processed outside
your deployment region**.

Alternatives:

- Purchase **in-region Provisioned Throughput** and set its model ARN as `BedrockModelId`.
- Use a **Bedrock VPC endpoint (PrivateLink)** to keep Bedrock traffic on a private path
  (generation Lambdas are VPC-external; add VPC configuration as needed).
- Choose a **model that supports bare on-demand invocation** in your region.

Auditing is unchanged: track invocations via `CloudTrail` and Bedrock **model invocation logging**.

### CI enforcement

`scripts/check_bedrock_inference_profile.py` (the CI "Bedrock inference-profile guard") checks both
**template defaults** (no bare Nova/Claude ID + IAM that includes an `inference-profile` ARN) and any
bare IDs left in **README parameter tables / CLI examples**. The allowlist is empty, so the rule is
always enforced for every Bedrock-using pattern.

### Verification levels

| Level | Mechanism | Network | CI |
|---|---|---|---|
| Static (templates / READMEs) | guard above + cfn-lint | none | always |
| Converse contract (request/response shape) | `shared/tests/test_bedrock_helper_contract.py` (botocore Stubber validates the real service model) | none | always |
| Live E2E (real invoke) | `scripts/bedrock_inference_profile_smoke.py` (opt-in) | **required**, small cost | manual only |

Live check example (needs credentials + model access; incurs a small cost):

```bash
python3 scripts/bedrock_inference_profile_smoke.py \
  --model-id apac.amazon.nova-lite-v1:0 --region ap-northeast-1
```

### Cost note

- Sample defaults use **`nova-lite` for cost**; switch to `nova-pro` or Claude for higher quality
  (keep the Sample-run vs Production-estimate distinction).
- Cross-region inference data transfer is **generally negligible for text**. Actual cost depends on
  token volume, model, and region. See the [Cost Calculator](cost-calculator.md).

---

## Related Documents

- [Comparison & Alternatives](comparison-alternatives.md)
- [Cost Calculator](cost-calculator.md)
- [Incident Response Playbook](incident-response-playbook.md)
