# Amazon Bedrock 推論プロファイル ガイド / Inference Profile Guide

> このドキュメントは、本リポジトリの各パターンが Amazon Bedrock を呼び出す際の
> **モデル ID / クロスリージョン推論プロファイル / IAM / データレジデンシー** に関する
> 共通ガイダンスです。各パターンの `BedrockModelId` パラメータ説明からここへリンクしています。

---

## 日本語

### なぜ推論プロファイルが必要か

Amazon Nova（`amazon.nova-lite-v1:0` 等）や新しい Claude モデルは、**リージョンによっては
オンデマンドでベアなモデル ID を呼び出せません**（オンデマンド対応状況はリージョン・モデル・
時期により異なります）。未対応リージョンでは次のエラーになります。

```
ValidationException: Invocation of model ID amazon.nova-lite-v1:0 with on-demand throughput
isn't supported. Retry your request with the ID or ARN of an inference profile that contains
this model.
```

**推論プロファイル ID の接頭辞は、リクエストのルーティング範囲（＝データがどこで処理されうるか）を
表します。** 接頭辞を選ぶことで、可用性とデータレジデンシー/主権のトレードオフをユーザー自身が制御
できます。二択（グローバル vs 日本）ではなく、**スコープの連続スペクトラム**です。

#### ルーティングスコープ（＝データレジデンシー）

| スコープ | 接頭辞（例） | ルーティング範囲 | 主な用途 |
|---|---|---|---|
| グローバル | `global.` | 世界中の対応リージョン | 最大の可用性・移植性（残留性制約が無い場合） |
| 大陸 / 地域 (geo) | `apac.` / `us.` / `eu.` | 同一 geo 内の複数リージョン | 地域レベルのレジデンシー |
| 国内 / 主権 (sovereign) | `jp.`（日本）/ `au.`（豪州）/ `us.`（米国）… | 単一国内の複数リージョン | 国内完結の厳格なレジデンシー |

> **接頭辞名がそのまま意図を表します**。`jp.`＝日本国内、`au.`＝豪州国内、`eu.`＝欧州、`global.`＝世界。
> AWS は複数の国内リージョンを持つ国（日本・米国・豪州・インド 等）向けに国内スコープのプロファイルを
> 順次拡大しています（例: 上記実測では日本 `jp.`・豪州 `au.` を確認。インド系リージョンは現時点で
> `apac.`/`global.` のみ＝国内スコープは今後拡大の可能性）。**利用可否はモデル・リージョン・時期で
> 変わるため、必ず `aws bedrock list-inference-profiles` で確認してください。**

#### 選び方

`BedrockModelId` に、要件に合うスコープのプロファイル ID を設定するだけです（パラメータは自由入力）。

- **移植性優先（既定）**: 本リポジトリの既定は、全リージョンで動く `global.`（Claude 系）/ APAC 全域の
  `apac.`（Nova 系）。まず「動く」ことを優先。
- **地域レジデンシー**: geo 内に留めたい → `apac.` / `us.` / `eu.`。
- **国内主権**: 国内に閉じたい → `jp.` / `au.` / `us.` 等（自国リージョンのプロファイル）、または
  **リージョン内 Provisioned Throughput**（単一リージョン固定）。

デプロイ時は `BedrockModelId` を上書きするだけで切り替えられます（コード変更不要）:

```bash
# 例: 既定（移植性優先の global.）を、日本国内スコープ（jp.）に変更してデプロイ
sam deploy --parameter-overrides BedrockModelId=jp.anthropic.claude-haiku-4-5-20251001-v1:0
# 自リージョンで利用可能なプロファイル ID は list-inference-profiles で確認（下記）
```

> **確認済み挙動（サンプル観測 / 2026-07 時点）**: 同一モデルでも、あるリージョンではベア ID の
> オンデマンド呼び出しが成功し、別のリージョンでは上記 `ValidationException` になりました。profile ID は
> いずれでも成功。また `apac.` が無いモデル（例: Claude Haiku 4.5 は `jp.`/`global.` のみ）もあります。
> 対応状況は変化するため、デプロイ先で必ず確認してください。

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

クロスリージョン推論プロファイルは、**スコープ内の複数リージョンにリクエストをルーティング**します
（`global.`＝世界、`apac.`＝APAC 全域、`jp.`＝日本国内 など）。規制・データ主権要件のあるワークロードでは、
**推論データがどの範囲で処理されうるか**を上記「ルーティングスコープ」に照らして必ず評価してください。

> AWS の公式整理では、クロスリージョン推論は 2 種類（**Geographic**＝地理境界内 / **Global**＝世界）に
> 分類されます。ルーティングされるのは**推論の一時的な計算**であり、**保存データ（ログ・ナレッジベース・
> 設定）はソースリージョンに留まる**設計です。通信は AWS ネットワーク内で暗号化され、パブリック
> インターネットを経由しません（[cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html)）。
> データ主権要件がある場合は Geographic（`apac.` や国内 `jp.`/`au.` 等）を、可用性・コスト優先なら
> Global（`global.`）を選択します。

残留性を狭める選択肢（強い順）:

- **国内 / 主権スコープのプロファイル** を選ぶ（`jp.` / `au.` / `us.` 等）。国内の複数リージョン内に閉じる。
- **リージョン内 Provisioned Throughput** を購入し、そのモデル ARN を `BedrockModelId` に指定する（単一リージョン固定）。
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
# 単一モデル
python3 scripts/bedrock_inference_profile_smoke.py \
  --model-id apac.amazon.nova-lite-v1:0 --region ap-northeast-1

# リポジトリが出荷する全既定モデルを一括検証（無効なプロファイル ID を検出）
python3 scripts/bedrock_inference_profile_smoke.py --all-repo-defaults --region ap-northeast-1
```

`--all-repo-defaults` は、テンプレートの geo 接頭辞付き既定値をすべて抽出して各 1 回呼び出します。
**存在しないプロファイル ID（例: 特定モデルに `apac.` が無いのに指定した場合）は静的チェックでは検出
できない**ため、この一括ライブ検証が有効です。

### コスト注記

- 本リポジトリのサンプル既定は **コスト優先で `nova-lite`** です。品質要件がある場合は
  `nova-pro` や Claude 系へ変更してください（Sample run vs Production estimate を区別）。
- クロスリージョン推論のデータ転送は、**テキスト用途では一般に軽微**です。実コストは
  トークン量・モデル・リージョンで変動します。[Cost Calculator](cost-calculator.md) を参照。

---

## English

### Why an inference profile is required

Amazon Nova (e.g. `amazon.nova-lite-v1:0`) and newer Claude models **cannot be invoked on-demand
by the bare model ID in some regions** (on-demand availability varies by region, model, and over
time). Where it is unsupported, the call fails with:

```
ValidationException: Invocation of model ID amazon.nova-lite-v1:0 with on-demand throughput
isn't supported. Retry your request with the ID or ARN of an inference profile that contains
this model.
```

**An inference-profile ID's prefix expresses the request's routing scope (i.e. where data may be
processed).** By choosing the prefix, you control the availability-vs-residency/sovereignty
trade-off yourself. It is **not** a global-vs-Japan binary — it's a continuous spectrum of scopes.

#### Routing scope (= data residency)

| Scope | Prefix (examples) | Routes within | Typical use |
|---|---|---|---|
| Global | `global.` | supported regions worldwide | maximum availability / portability (no residency constraint) |
| Continent / geo | `apac.` / `us.` / `eu.` | multiple regions in one geo | geo-level residency |
| Country / sovereign | `jp.` (Japan) / `au.` (Australia) / `us.` (US) … | multiple regions within one country | strict in-country residency |

> **The prefix name conveys the intent**: `jp.` = within Japan, `au.` = within Australia, `eu.` =
> Europe, `global.` = worldwide. AWS is expanding in-country (sovereign) profiles for countries that
> have multiple in-country regions (Japan, US, Australia, India, …). In this repo's live probe we saw
> Japan `jp.` and Australia `au.`; India-family regions currently expose only `apac.`/`global.`
> (country scope may appear later). **Availability is model-, region-, and time-specific — always
> verify with `aws bedrock list-inference-profiles`.**

#### How to choose

Set `BedrockModelId` to a profile ID whose scope matches your requirement (the parameter is free-form):

- **Portability (default):** this repo defaults to `global.` (Claude) / `apac.` (Nova) so it "just
  works" everywhere.
- **Geo residency:** keep data within a geo → `apac.` / `us.` / `eu.`.
- **In-country / sovereign:** keep data within your country → `jp.` / `au.` / `us.` … (your country's
  profile), or **in-region Provisioned Throughput** (pinned to a single region).

Switch at deploy time by overriding `BedrockModelId` (no code change):

```bash
# e.g. change the default (portability-first global.) to Japan in-country scope (jp.)
sam deploy --parameter-overrides BedrockModelId=jp.anthropic.claude-haiku-4-5-20251001-v1:0
# list the profile IDs available in your region with list-inference-profiles (below)
```

> **Observed behavior (sample, as of 2026-07):** for the same model, the bare ID invoked on-demand
> successfully in one region but returned the `ValidationException` above in another; the profile ID
> succeeded in both. Some models also have no `apac.` (e.g. Claude Haiku 4.5 offers only `jp.`/
> `global.`). Availability changes over time — verify in your deployment region.

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

A cross-region inference profile **routes requests across multiple regions within its scope**
(`global.` = worldwide, `apac.` = across APAC, `jp.` = within Japan, …). For regulated or
data-sovereignty-sensitive workloads, evaluate **where inference data may be processed** against the
"Routing scope" table above.

> AWS classifies cross-Region inference into two types — **Geographic** (stays within a geographic
> boundary) and **Global** (worldwide). What routes is the **transient inference computation**;
> **data at rest (logs, knowledge bases, configuration) stays in the source Region**, and traffic
> stays on the encrypted AWS network (never the public internet). See
> [cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html).
> Choose **Geographic** (`apac.`, or in-country `jp.`/`au.`/…) for data-residency needs; choose
> **Global** (`global.`) for availability/cost (AWS notes ~10% lower price for global).

Ways to narrow residency (strongest first):

- Choose a **country / sovereign-scope profile** (`jp.` / `au.` / `us.` …) — stays within that
  country's regions.
- Purchase **in-region Provisioned Throughput** and set its model ARN as `BedrockModelId` (pinned to a single region).
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
# single model
python3 scripts/bedrock_inference_profile_smoke.py \
  --model-id apac.amazon.nova-lite-v1:0 --region ap-northeast-1

# validate every default the repo ships (catches invalid profile IDs)
python3 scripts/bedrock_inference_profile_smoke.py --all-repo-defaults --region ap-northeast-1
```

`--all-repo-defaults` extracts every geo-prefixed default from the templates and invokes each once.
**A non-existent profile ID (e.g. specifying `apac.` for a model that has no `apac.` profile) cannot
be caught by static checks** — this bulk live check catches it.

### Cost note

- Sample defaults use **`nova-lite` for cost**; switch to `nova-pro` or Claude for higher quality
  (keep the Sample-run vs Production-estimate distinction).
- Cross-region inference data transfer is **generally negligible for text**. Actual cost depends on
  token volume, model, and region. See the [Cost Calculator](cost-calculator.md).

---

## AWS References / 参考資料（一次情報）

- [Increase throughput with cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html) — Geographic vs Global comparison, data-residency guidance
- [Geographic cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html) — using a profile ID as `modelId` (InvokeModel / Converse)
- [Supported cross-Region inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html) — which models/prefixes exist per geography
- CLI: `aws bedrock list-inference-profiles --region <your-region>` — authoritative per-region list

## Related Documents

- [Comparison & Alternatives](comparison-alternatives.md)
- [Cost Calculator](cost-calculator.md)
- [Incident Response Playbook](incident-response-playbook.md)
