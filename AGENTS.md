# AGENTS.md

> Project-specific instructions for AI coding agents working in this repository.

## Project Overview
FSx for ONTAP S3 Access Points Serverless Patterns — a library of **28 industry-specific use
cases (UC1-UC28)** + **1 SAP/ERP pattern** + **10 FlexCache/FlexClone patterns** + **2 GenAI
patterns** + **1 HA monitoring pattern** + **2 event-driven patterns** + **2 edge delivery
patterns** + **6 operations optimization patterns (OPS1-OPS6)**. Each pattern is an independent
CloudFormation/SAM template sharing the Python modules in `shared/`.

**Two pillars**: `solutions/` (S3 AP data processing) + `operations/` (file system operational
optimization).

**Test coverage**: ~4,900 Python tests across 290 files + ~495 vitest tests across 34 files.

> ファイル数は `make drift` がツリーと照合するので、古くなれば fail する。テスト総数は
> `make test` / ポータルハンドラの個別実行 / vitest の 3 系統の合計なので概数。誰も保守
> しない厳密な数値より、丸めた数値のほうがよい。
## 詳細知識の所在

このファイルは**タスクの内容が分かる前に必要な情報**だけを持つ。作業別の詳細は
`docs/agent/` にある。ローカルの Kiro では `.kiro/steering/` と `.kiro/skills/` が
「いつ読むか」だけを持ち、該当する作業をしているときに自動でこれらへ誘導する。
`.kiro/` は公開しないため、**知識の本体は常に `docs/agent/` 側にある**。

| 作業 | 参照先 |
|---|---|
| CloudFormation / SAM を書く・デプロイが失敗した | [pitfalls-cfn-sam](docs/agent/pitfalls-cfn-sam.md) |
| FlexGroup を作る・容量の偏りを直す・型ごとの差を調べる | [pitfalls-flexgroup](docs/agent/pitfalls-flexgroup.md) |
| S3 AP / ONTAP API を扱う・AccessDenied を調べる | [pitfalls-s3ap-ontap](docs/agent/pitfalls-s3ap-ontap.md) |
| FlexCache / SnapMirror / SVM ピアを作る・消す | [pitfalls-flexcache-snapmirror](docs/agent/pitfalls-flexcache-snapmirror.md) |
| ボリューム / FlexCache の作成・削除、SMB ローカルユーザー | [pitfalls-volume-lifecycle](docs/agent/pitfalls-volume-lifecycle.md) |
| AD 連携 / SMB / Windows ドメイン参加 | [pitfalls-ad-smb](docs/agent/pitfalls-ad-smb.md) |
| Bedrock / AgentCore / Quick / KNFSD | [pitfalls-genai-edge](docs/agent/pitfalls-genai-edge.md) |
| SnapLock / WORM / Snapshot ロック | [pitfalls-snaplock](docs/agent/pitfalls-snaplock.md) |
| ARP/AI の状態遷移 / EMS イベント | [pitfalls-arp-ems](docs/agent/pitfalls-arp-ems.md) |
| ポータルの CDK / cdk-nag | [portal-cdk-quality-gates](docs/agent/portal-cdk-quality-gates.md) |
| ポータル sandbox の削除 / 同一 VPC への 2 台目 | [portal-sandbox-lifecycle](docs/agent/portal-sandbox-lifecycle.md) |
| ポータル UI の文字列 / 翻訳 | [portal-i18n](docs/agent/portal-i18n.md) |
| 他端末に渡すデモ環境（URL / アカウント） | [portal-demo-environment](docs/agent/portal-demo-environment.md) |
| 作業を PR に切り分けて main に載せる | [landing-work](docs/agent/landing-work.md) |
| コスト見積り / リソース停止 | [cost-awareness](docs/agent/cost-awareness.md) |
| 依存追加 / Renovate | [dependency-updates](docs/agent/dependency-updates.md) |
| 構成図の作成・再生成・エクスポート | [diagram-regeneration](docs/agent/diagram-regeneration.md) |
| ポータル画面の撮影 / E2E / ブラウザ自動化 | [pitfalls-browser-automation](docs/agent/pitfalls-browser-automation.md) |
| 新パターンの追加と公開判定 | [new-pattern](docs/agent/new-pattern.md) |
| ドキュメント全体を探す | [docs/index.md](docs/index.md) |
| README / ドキュメント構成の設計 | グローバル steering `documentation-design` |
| 成果物のレビュー観点 | グローバル steering `sa-persona-review-board` |

> 不可逆操作・命名・PII・認可のように**知らないと事故る情報は上の表に移していない**。
> ロード条件のマッチ運に賭けられないため、常時ロードかフック強制のままにしてある。

## 着手前に grill を通す条件

次に当てはまる依頼は、実装より先に `grill-me`（グローバル steering に判断規則と質問形式）で
決定を洗い出す。曖昧で解釈が 2 通り以上ある / 複数ファイルまたは複数言語に触る / 不可逆操作を
含む / 公開物を作り変える / 数値・上限・価格・リージョン提供状況を書く / 比較や選定を書く。

**当てはまらないものは grill しない。** typo 修正や指示済みのコマンド実行を訊き返すのは
網羅性ではない。事実は自分で調べ、決定だけを訊く。

### ブラウザ自動化で対話を止めない（常時適用）

理由と再現手順は [pitfalls-browser-automation](docs/agent/pitfalls-browser-automation.md)。
この 3 つだけは**踏むとユーザーの操作を数分ブロックする**ので参照表任せにしない。

- `page.addInitScript()` は蓄積し解除できない → 書き換えは撮影直前の `page.evaluate()` で。
- DOM を書き換える処理を `MutationObserver` から呼ばない → レンダラーが 100% で回り、
  「見た目は正常なのに自動化だけ返らない」形になる。
- 返らなくなったらリトライしない → 暴走レンダラーの pid を特定して kill する。

## Core Commands
`make help` が現役のターゲット一覧を出す。ここには毎回使うものだけを置く。

```bash
make test-quick     # 主要パターンのテスト（コミット前に必須）
make test           # 全テスト
make lint           # ruff（2 段）+ cfn-lint
make format-python  # フォーマット差分の修正
make drift          # 乖離・到達性チェック一式（中身は Verification Checklist を見る）
make security       # bandit
make security-cfn   # cfn-guard（cfn-guard バイナリが必要）
make clean          # ビルド成果物の削除

make test-uc1 / test-ops1 / test-fc1 / test-sap   # 単一パターン（番号を差し替える）
make build-uc1 / deploy-uc1                       # samconfig.toml が必要
```

個別に呼ぶことがあるもの:

```bash
python3 -m pytest solutions/industry/semiconductor-eda/tests/ -v  # 単一ディレクトリ
cfn-lint --non-zero-exit-code error <template.yaml>               # 単一テンプレート
python3 scripts/check_portal_action_params.py --list-opaque        # 読めない呼び出し箇所
python3 scripts/portal_action_types.py --check                     # 生成モジュールと handler の一致
make drift-published                                               # 公開記事の陳腐化（要ネットワーク、PR ゲートではない）
```

ポータル（`solutions/amplify-portal/`）を動かす:

```bash
npm run dev    # vite のみ。frontend 確認（AWS を変更しない）
npm start      # ↑ + sandbox watch。未コミットの amplify/ が AWS に入る
npm run phone  # ↑ + トンネル。使い捨て URL。渡さない
```

**`npx ampx sandbox` を素で実行しない。** identifier を省略すると別 sandbox を新規作成して
失敗し、ロールバックもしない。`scripts/sandbox.sh` 経由で使う。

**URL を渡す前に `make portal-preflight`。** 開けることはサインインできる証拠ではない。

KNFSD（Terraform、`infrastructure/knfsd-file-cache/`）は `scripts/{deploy,validate-cache,cleanup}.sh`。
## Project Layout
ツリー全体はリポジトリから読める（`ls`、`make drift`）。ここには**役割**だけを置く。
構造を焼き込むと更新されずに古くなるため、一覧は列挙しない。

| パス | 役割 |
|------|------|
| `solutions/industry/` | UC1-UC28 の業種別パターン。1 ディレクトリ = 独立してデプロイ可能な 1 パターン |
| `solutions/{sap,flexcache,genai,ha,event-driven,edge}/` | 業種横断のパターン群 |
| `solutions/amplify-portal/` | Amplify Gen2 のファイルポータル（`amplify/` が CDK、`src/` が React） |
| `operations/` | OPS1-OPS6。ファイルシステム運用最適化（S3 AP を使わない側の柱） |
| `infrastructure/` | パターンに属さない共有基盤（AD 検証環境、KNFSD 読み取りキャッシュ） |
| `shared/` | 全パターンが import する Python モジュール。`s3ap_helper.py` が中核抽象 |
| `shared/schemas/` | イベント / レスポンスの TypedDict |
| `scripts/` | 自動化スクリプト。`make` のターゲットから呼ばれるものが現役 |
| `docs/` | ドキュメント。索引は `docs/index.md`、`en/` と `ja/` が対訳 |
| `security/`, `cfn-params/`, `params/` | cfn-guard ルールとパラメータ例 |
| `.kiro/` | このリポジトリ固有の steering / skills / hooks（git 未追跡） |

各パターンのディレクトリは同じ形をしている:

```
{pattern}/
├── template.yaml            # SAM/CloudFormation。単体でデプロイ可能
├── functions/{func}/handler.py
├── statemachine/*.asl.json  # Step Functions（DefinitionUri で参照）
├── tests/                   # pytest + hypothesis
├── docs/                    # アーキテクチャ、デモガイド
├── samconfig.toml.example
└── README.md                # 8 言語（ja/en/ko/zh-CN/zh-TW/fr/de/es）
```
## Architecture Patterns

- **Trigger**: EventBridge Scheduler (polling) OR FPolicy EventBridge Rule (event-driven)
- **Orchestration**: Step Functions state machine per UC
- **Compute**: Lambda functions (Python 3.13, 256-1024MB)。**アーキテクチャは統一されていない**:
  `Architectures: [arm64]` を宣言しているのは一部（operations 全体と一部の solutions）で、
  残りは宣言が無いため Lambda 既定の x86_64 になる。純 Python なので動作は変わらないが
  GB 秒あたりの単価は arm64 が安い。**新規パターンは arm64 を明示する**。内訳は数えれば
  分かるので焼き込まない（`grep -rl "arm64" solutions/*/*/template.yaml operations/*/template.yaml`）
- **Storage access**: FSx for ONTAP S3 Access Points (read/write via S3ApHelper)
- **AI/ML**: Bedrock (Nova/Claude), Textract, Comprehend, Rekognition, SageMaker
- **Analytics**: Athena + Glue Data Catalog
- **Secrets**: Secrets Manager for ONTAP credentials
- **Networking**: VPC-internal (ONTAP API) + VPC-external (S3 AP Internet Origin)
- **TriggerMode**: POLLING / EVENT_DRIVEN / HYBRID (per-UC parameter)
- **DemoMode**: `true` allows running without FSx for ONTAP (regular S3 bucket)

## Coding Conventions

### Python

- Python 3.13 target。Source must stay compatible with 3.12 (`requires-python = ">=3.12"`, ruff `target-version = "py312"`, CI matrix 3.11–3.13)
- Type hints on all function signatures (use `shared/schemas/events.py` TypedDicts)
- Docstrings on all public functions (Google style)
- `from __future__ import annotations` at top of every module
- No wildcard imports
- Use `logging` module, never `print()` in Lambda handlers
- Error handling: raise domain exceptions from `shared/exceptions.py`
- Use `shared/observability.py` EmfMetrics for CloudWatch metrics
- Use `shared/human_review.py` for confidence-based review decisions
- Use `shared/data_classification.py` for output data labeling

### CloudFormation / SAM

- Each UC template is self-contained (deployable independently)
- Use `!Sub` for all resource names (include `${AWS::StackName}`)
- Conditions for optional resources (VPC Endpoints, CloudWatch Alarms, X-Ray)
- TriggerMode Conditions: `IsPollingOrHybrid`, `IsEventDrivenOrHybrid`
- Tags on all resources: `UseCase`, `Phase`
- IAM: least-privilege, per-function roles
- Log retention: `LogRetentionInDays` parameter (default 90, compliance: 2557)
- Step Functions: always include Retry/Catch on Task states
- Step Functions ASL: prefer `DefinitionUri` over inline `DefinitionBody` (cfn-lint compat)
- `RecursiveDeleteOption: true` on Athena WorkGroups (single key, no duplicates)
- `SNSPublishMessagePolicy` requires `TopicName` (not `TopicArn`)

### Naming

- UC directories: kebab-case (`legal-compliance`, `financial-idp`)
- Lambda functions: `{stack-name}-{function-name}`
- Python modules: snake_case
- CloudFormation resources: PascalCase
- Environment variables: UPPER_SNAKE_CASE
- Handler files: `handler.py` (not `index.py`)
- Handler entry: `handler.handler` (not `index.handler`)

## Testing

- Framework: pytest + hypothesis (property-based)
- Mocking: moto (AWS services)
- Coverage threshold: 80%
- Test location: `shared/tests/` (shared) + `{uc}/tests/` (UC-specific)
- Run before every commit: `make test-quick`
- conftest.py in each test dir for sys.path + fixtures

### shared/ Module Resolution

```python
# In conftest.py (each pattern's tests/)
# Root conftest.py adds project root to sys.path automatically.
# Pattern tests only need to add their local functions dir:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "functions" / "discovery"))
```

```bash
# Run from repo root (PYTHONPATH auto-resolved via root conftest.py)
python3 -m pytest solutions/sap/erp-adjacent/tests/ -v
```

### Known test exclusions

- `tests/e2e/` — requires deployed AWS stacks
- `tests/load/` — requires deployed infrastructure
- `shared/tests/test_canary_properties.py` — requires live S3 AP

### テスト固有の罠

| Pitfall | Solution |
|---------|----------|
| Hypothesis + moto DynamoDB slow | Use `deadline=None` in `@given()` settings |
| Test file name collision across patterns | Use unique test file names or run per-directory |
| アプリ側モジュール名の衝突（`handler` / `index`） | conftest で固有名にして `sys.modules` に登録する。`scripts/check_test_module_names.py` が強制 |

## Self-Review (4-Axis Check)

4 軸（実装漏れ / 違和感 / 磨き込み / 退行リスク）の定義はグローバル steering
`yoshiki-ai-development-principles` にある。あちらも常時ロードなので、ここに転記すると
同じ規約が 2 か所に存在し、片方だけが更新される。このリポジトリ固有の読み替えだけを置く:

- **実装漏れ**: handler を変えて `template.yaml` を忘れていないか。JA/EN parity。
- **退行リスク**: `make test-quick` を通したか。`shared/` の export を消していないか
  （全パターンが import する）。DemoMode と本番パスの両方を壊していないか。

## Verification Checklist
変更を出す前に、毎回:

1. `make test-quick`
2. `make lint` — `ruff check` と `ruff format --check` の両方。CI が別ステップなので、
   片方だけではローカルを通って CI で落ちる。差分は `make format-python`
3. `cfn-lint` — 変更したテンプレート
4. `make drift` — ゲート自身の健全性（.PHONY 網羅、ツール不在で落ちるか、ピン留めした
   バージョンが実際に走るか、`make drift` の各チェックが CI からも走るか）、テストディレクトリ
   の網羅、action インベントリと action-parameter 契約、i18n（manifest が要求する翻訳の存在・
   全 8 言語の構造 parity・生成されたスイッチャ）、陳腐化ルール、テーマトークン、画像とリンクの
   解決、samconfig 例、env var 契約、Lambda ランタイム版の一致（`PY_VERSION` と全テンプレート
   / CDK / requires-python / CI マトリクス）
5. `make security-cfn` — テンプレートを触ったとき。cfn-guard は暗号化・公開アクセス・
   最小権限・SageMaker 分離を見る（cfn-lint はテンプレートの妥当性しか見ない）

変更内容に応じて:

| 変更したもの | 追加で必要なこと |
|---|---|
| UC テンプレート | TriggerMode のパラメータと Condition が揃っているか |
| `shared/` にモジュール追加 | `shared/tests/` にテストを追加 |
| README | Governance Note と Performance Considerations があるか |
| 新しい出力 | `data_classification` フィールドを含める |
| ポータルの dispatch 呼び出し | `src/lib/dispatch.ts` を経由する（`client.mutations.*` を直接呼ばない）。handler のパラメータを変えたら `src/lib/dispatchActions.ts` を再生成する（`make drift` が一致するまで fail する）。ブランドは ONTAP から値が到着する場所（レスポンスの interface）で付ける。呼び出し側で付けると、その場にある任意の文字列を受け入れてしまい、防ぎたい間違いそのものになる |
| ユーザー向け UI 文字列 | `ja.ts` に先に追加してから他 7 言語。`t("key")` を使う。JSX テキスト・`aria-label`・`title`・`placeholder` にハードコードしない。製品名・SQL リテラル・技術用語（ONTAP, FlexCache, SnapLock, S3 AP）は翻訳しない。`t("key") \|\| "既定値"` と書かない（`t()` は末尾が `?? key` なので常に truthy で、右辺は到達しない） |
| ポータルの色 | `var(--color-*)` を使う。**値ではなく役割で対応付ける**（`white` は `color` なら `--color-text-inverse`、`background` なら `--color-surface`）。JSX の `style={{ }}` に色リテラルを書かない（インラインは後から上書きできないので、そのテーマに固定される）。新しいトークンは `:root` と `[data-theme="dark"]` の**両方**に定義する |
| 制約の解消（ドキュメントが「自分で作れ」と書いていたものを実装した） | `make drift-published` も走らせる。公開記事の記述はリポジトリ内のチェックでは見えない |
| `solutions/amplify-portal/amplify/**` | IAM Policy Validation ワークフローが `solutions/industry/` と `infrastructure/` の**全**テンプレートを走査する。失敗は既存の負債かもしれないので、`git diff --name-only` で自分の変更範囲を確認してから引き受ける |

> **なぜ action-parameter 契約チェックがあるか**: dispatch は型のない `params` を取るため、
> TypeScript は境界の向こうを見られない。`{snapshotName, retentionDays}` を `snapshotId` と
> `expiryTime` を読む action に送るコードは、コンパイルも lint も通り、ボタンも描画され、
> クリックのたびに失敗する。実際に出荷された。新しいラッパー形状で dispatch を呼んだら
> `--list-opaque` を確認する。チェッカーが読めない呼び出しは、守れない呼び出しである。
> action 名は計算せずリテラルで書く。
## Key Design Decisions

### S3ApHelper is the Core Abstraction

All S3 AP access goes through `shared/s3ap_helper.py`. It accepts both S3 AP aliases and regular S3 bucket names (enabling DemoMode). Never call `boto3.client('s3')` directly in Lambda handlers.

### VPC Split Architecture

- **VPC-internal Lambda**: For ONTAP REST API access (management LIF is private)
- **VPC-external Lambda**: For Internet-origin S3AP access (no VpcConfig)
- **Never mix**: A single Lambda cannot access both ONTAP mgmt LIF and Internet-origin S3AP

### Output Destination Pattern

- `OutputDestination=STANDARD_S3` — write to new S3 bucket (default)
- `OutputDestination=FSXN_S3AP` — write back to FSx for ONTAP via S3 AP (NFS/SMB users see results)

### Human Review Pattern

```python
from shared.human_review import evaluate_confidence
decision = evaluate_confidence(confidence=0.72)
# decision.action: "AUTO_APPROVE" | "HUMAN_REVIEW" | "REJECT"
```

## External Dependencies

- **AWS Region**: ap-northeast-1 (Tokyo) — primary deployment target
- **ONTAP version**: 9.18.1P3D1 (supports FPolicy, Persistent Store, protobuf)
- **Python packages**: boto3, urllib3
- **Dev packages**: pytest, hypothesis, moto, ruff, cfn-lint, bandit

## Documentation Language

- Code, variable names, CloudFormation resources: English
- Documentation, comments, README: Japanese (primary) + English + 6 other languages
- Commit messages: English (conventional commits: `feat:`, `fix:`, `docs:`, `chore:`)
- No persona names in git content (use role-based descriptions)

## Security & Privacy (Public Repository)
公開リポジトリである。コミットした内容は全世界から見える。

### Placeholder Rules

| Real Data | Placeholder |
|-----------|-------------|
| AWS Account ID | `123456789012`。複数アカウントを書き分けるときは下記の 3 形状のいずれかを使う |
| Secret ARN suffix | `-XXXXXX` |
| VPC/Subnet/SG IDs | `vpc-0123456789abcdef0` |
| File System ID | `fs-0123456789abcdef0` |
| Real IP addresses — a network or CIDR | `10.0.0.0/16`, `10.0.1.0/24`, or `<management-ip>` |
| Real IP addresses — **one host standing in for a person's client** | RFC 5737 documentation range: `203.0.113.x` (or `198.51.100.x`) |
| SSH key paths | `<your-ssh-key.pem>` |
| Personal file paths | Relative paths or `${PROJECT_DIR}` |
| S3 AP Alias | Use parameter reference `!Ref S3AccessPointAlias` |

> **アカウント ID は値ではなく形状で許可される**: 許可されるのは同一数字の繰り返し
> （`111111111111`）、4 桁ずつの繰り返し（`111122223333`、AWS 公式ドキュメントの慣行）、
> ±1 の連番（`123456789012`、`987654321098`）。形状判定なのでアカウントを 1 つ増やすときに
> この表を編集する必要はない。実在 ID を書かざるを得ないなら行に `allow:account-id` と理由を
> 付ける。強制と例外は `scripts/check_account_id_placeholders.py` にある

> **IP が 2 行ある理由**: 判断基準は「そのアドレスは 1 人の端末を指しているか」。指すなら
> RFC 5737 に置換し（PII 監査が守る対象そのもの。`scripts/portal-probes/` が
> `203.0.113.99` を使うのも同じ理由）、ネットワークを指すなら `10.0.0.0/16` のまま残す
> ——「プライベートである」ことが説明の一部だから。

### 機械強制されているもの

命名違反（FSxN / FSx ONTAP）、個人のファイルパス、ペルソナ名、サポートケース番号、ベンダー <!-- allow:naming: 禁止語を規則として明示する行 -->
内部チケット ID、実在しそうな AWS アカウント ID、メールアドレスは、ローカルの commit フック
がステージ済み差分を検査して `exit 2` で commit を停止する（フックは `.kiro/` にあり
リポジトリには含まれない）。逐語引用など意図的な場合はその行に `allow:naming` /
`allow:vendor-ref` を付ける。CI 側は `.github/workflows/agent-output-audit.yml` と
`gitleaks.yml` が同等の検査を行うので、フックが無い環境でも取りこぼしはない。

機械では判定できないので人が見るもの:

- マスクしていないスクリーンショット（`scripts/mask_uc_demos.py`）
- `.pem` / SSH 鍵 / `.env`（`gitleaks` も拾うが、そもそもリポジトリに置かない）
- 役職名ラベルの inline note — 実際のレビューがないのに「〜 lens」「〜 の視点」と書かない。
  中立なトピック名（`**セキュリティに関する補足**` 等）を使う
## Irreversible Operations — Confirm Before Executing
一部の AWS / ONTAP 操作は取り消せず、いくつかは**親リソース**を数か月ロックする。
これらに事後検証は成立しない。復旧経路が存在しないからである。

**毎回、実行前にアカウント所有者の承認を得るもの:**

| Operation | Why |
|---|---|
| Create a SnapLock volume (`compliance` / `enterprise`) | `snaplock.type` is creation-time only. Unexpired WORM files block volume → SVM → **file system** deletion |
| Create a SnapLock audit log volume | Minimum 6 months. AWS API has no field for the audit-log retention, so the default applies. **No route to early deletion exists other than closing the account** |
| `PrivilegedDelete=PERMANENTLY_DISABLED` | Terminal state. Makes `enterprise` behave as `compliance` |
| `snapshot_locking_enabled = true` | Cannot be disabled |
| Lock a snapshot (`expiry_time`) | Extendable only. Cannot be shortened or released |
| S3 Object Lock `COMPLIANCE` mode | Retention cannot be shortened or removed |
| Delete a volume, SVM or file system | Data loss |

**ルール:**

- **影響範囲を先に述べる。** どのリソースが、いつまで削除不能になり、その間いくらかかるか。
- **保持期間の既定値を受け入れない。** API に指定手段がないことは、進めてよい理由ではなく
  止まって聞く理由である。
- **最初の呼び出しの前に**サービスドキュメントの「削除できない条件」を読む。最初の失敗の後ではなく。
- **検証環境こそ最悪の置き場所。** 6 か月削除できないファイルシステムは 6 か月の請求で、
  同居する他のボリュームも動かせなくなる。
- 成功を返したのにリソースが変わらないとき、**フラグを足して再試行しない。**
  `Lifecycle` を見て止まる。

> この表のうち機械判定できるものは `~/.kiro/hooks/guard-irreversible-ops.json` が実行前に
> `exit 2` でブロックする（削除系と、payload が外部ファイルで中身が読めない場合は確認を求める）。
> フックは判断を代行しない。上のルールは残る。詳細な罠は `pitfalls-snaplock` が持つ。
## Agent Output Standards
命名（FSx for ONTAP のみ）、ベンダー中立性、公開物の PII 安全、JA/EN parity、技術リファレンスの
必須要素は、いずれもユーザーレベルのグローバル steering が持つ。規約本体を 2 か所に置くと
片方が古くなるので、ここは参照だけにしてある。

| 対象 | 参照先 |
|---|---|
| 命名 / 中立性 / PII / JA・EN parity | グローバル `yoshiki-ai-development-principles`（常時ロード） |
| 記事と技術ドキュメントの品質バー | グローバル `documentation-and-article-quality` |
| ガバナンスと責任ある AI | グローバル `governance-responsible-ai` |
| CI | `.github/workflows/agent-output-audit.yml`（命名/中立性/リーク/parity）、`gitleaks.yml` |
| コミット時の機械強制 | `.kiro/hooks/scripts/commit_gate.py` |

### FSx for ONTAP の管理インターフェース（プロジェクト全体の前提）

**ONTAP System Manager は FSx for ONTAP の到達可能な管理インターフェースではない。** 到達できるのは
AWS マネジメントコンソール / FSx API、ONTAP CLI（SSH）、ONTAP REST API の 3 つで、後ろ 2 つは
VPC 内（または TGW ピア経由）からのみ。System Manager 対応はベンダー SaaS 経由でのみ提供され、
その SaaS は FSx for ONTAP を SaaS 接続前提のモードでしか扱わない。管理経路にサードパーティ
SaaS を置けない体制では選択肢が存在しない。これはレジデンシー制約からの帰結で、製品の優劣
判断ではない。

出典・モード対応表・**書くときの禁止事項**は
[管理インターフェースの整理（JA）](docs/ja/fsx-ontap-management-interfaces.md#書くときの禁止事項) /
[(EN)](docs/en/fsx-ontap-management-interfaces.md#what-not-to-write) にある。到達可能性の主張を
書く前に読むこと。System Manager を **UI デザインの参照元**として挙げるのは可
（「カード型ナビゲーションを踏襲」等）。
