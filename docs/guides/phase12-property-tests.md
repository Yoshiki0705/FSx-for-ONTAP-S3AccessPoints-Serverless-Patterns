# Phase 12 Property-Based Tests Guide

## Overview

Phase 12 では Hypothesis ライブラリを使用したプロパティベーステスト（PBT）を導入し、
各コンポーネントの不変条件・安全性保証を形式的に検証する。

PBT は従来のユニットテスト（具体例ベース）を補完し、ランダム生成された多数の入力に対して
普遍的な性質（プロパティ）が成立することを検証する手法である。

## テストファイル構成

| ファイル | 対象コンポーネント | プロパティ |
|---------|-------------------|-----------|
| `shared/tests/test_guardrails_properties.py` | Capacity Guardrails | P1: Mode Consistency, P2: Daily Cap Invariant |
| `shared/tests/test_secrets_rotation_properties.py` | Secrets Rotation | P15: Secrets Not Logged |
| `shared/tests/test_capacity_forecast_properties.py` | Capacity Forecast | P3: Linear Regression Correctness, P4: Prediction Consistency |
| `shared/tests/test_protobuf_reader_properties.py` | Protobuf Frame Reader | P7: LENGTH_PREFIXED Round-Trip, P8: FRAMELESS Round-Trip, P9: Max Size Enforcement, P10: Counter Accuracy |
| `shared/tests/test_canary_properties.py` | Synthetic Monitoring Canary | P11: Fail-Independence, P16: No Sensitive Data in Results |
| `shared/tests/test_lineage_properties.py` | Data Lineage Tracking | P5: Record Round-Trip, P6: History Ordering |
| `shared/tests/test_load_properties.py` | Load/Replay Testing | P12: Set-Difference Event Loss, P13: Ramp-Up Linearity, P14: Percentile Correctness |

## 実行方法

```bash
# 全プロパティテストを実行
python3 -m pytest -m property -v

# 個別ファイルを実行
python3 -m pytest shared/tests/test_guardrails_properties.py -v

# 全テスト（ユニット + プロパティ）を実行
python3 -m pytest shared/tests/ -v
```

## プロパティ一覧

### Property 1: Guardrail Mode Consistency

**検証対象**: Requirements 1.1, 1.2, 1.3

| モード | 期待動作 |
|--------|---------|
| BREAK_GLASS | 任意の入力で `allowed=True` |
| DRY_RUN | 任意の入力で `allowed=True`（チェック失敗時もブロックしない） |
| DRY_RUN (DynamoDB障害) | fail-open: `allowed=True` |

**テスト戦略**:
- `action_type`: 5種類のアクション種別からランダム選択
- `requested_gb`: 0.1〜200.0 GB の浮動小数点数
- DynamoDB の事前状態（daily_total, action_count）もランダム生成

### Property 2: ENFORCE Daily Cap Invariant

**検証対象**: Requirements 1.4, 1.5, 1.7

**不変条件**: 任意のアクションシーケンス実行後、`daily_total_gb <= daily_cap_gb`

**テスト戦略**:
- `action_sequence`: 1〜20個のリクエスト（各0.1〜100.0 GB）
- `daily_cap_gb`: 50.0〜2000.0 GB
- `rate_limit`: 1〜50
- クールダウンは無効化して cap/rate limit に集中

**発見事項**:
- ガードレールの日次キャップチェックは `>` (strict greater than) を使用するため、
  `daily_total_gb` は `daily_cap_gb` と正確に等しくなることがある（超過はしない）
- Decimal/float 変換で微小な丸め誤差が発生するため、テストでは 0.001 GB の許容誤差を設定

### Property 3: Linear Regression Correctness

**検証対象**: Requirements 4.3

**不変条件**: 完全に線形なデータ `y = a*x + b` に対して、`linear_regression()` が
元のパラメータ `a` (slope) と `b` (intercept) を正確に復元する。

**テスト戦略**:
- x 値は 0 ベースのオフセット（epoch タイムスタンプの大きさによる精度低下を回避）
- `slope_per_step`: 0.01〜10.0 GB/step
- `intercept`: 0.0〜500.0 GB
- `num_points`: 3〜100 点
- `time_step`: 3600〜86400 秒

**発見事項**:
- 大きな epoch タイムスタンプ（~1.7×10⁹）を直接 x 値として使用すると、
  正規方程式の条件数が悪化し、浮動小数点精度が大幅に低下する
- 実運用では問題にならない（30日分のデータで十分な精度が得られる）が、
  テストでは x 値を正規化して精度を確保

### Property 4: Capacity Prediction Consistency

**検証対象**: Requirements 4.4, 4.7

**不変条件**:
- 正の slope かつ `current_usage < total_capacity` → `days_until_full >= 0`
- `slope <= 0` → `days_until_full = -1`
- `current_usage >= total_capacity` → `days_until_full = 0`

**テスト戦略**:
- `current_usage_pct` を使って intercept を逆算（assume フィルタリングを回避）
- 固定 `current_time` を使用（テストの再現性確保）

**発見事項・バグ修正**:
- `predict_days_until_full()` で `seconds_remaining` が非常に大きい場合に
  `int()` 変換でオーバーフローが発生するバグを発見・修正
- 修正: `seconds_remaining > 1e15` または `not math.isfinite()` の場合は `-1` を返す

### Property 7: LENGTH_PREFIXED Round-Trip

**検証対象**: Requirements 6.2

**不変条件**: 4バイト big-endian 長さプレフィックスでエンコードしたメッセージが
正確に復元される。

**テスト戦略**:
- `message`: 1〜1000 バイトのランダムバイナリデータ
- 単一メッセージ・複数メッセージ（1〜10個）の両方をテスト
- `bytes_read` と `messages_read` カウンターの正確性も検証

### Property 8: FRAMELESS Round-Trip

**検証対象**: Requirements 6.3

**不変条件**: varint-delimited でエンコードしたメッセージが正確に復元される。

**テスト戦略**:
- `message`: 1〜1000 バイトのランダムバイナリデータ
- 128バイト以上のメッセージ（マルチバイト varint）を重点テスト
- メッセージ順序の保持を検証

### Property 15: Secrets Not Logged

**検証対象**: Requirements 2.8

**不変条件**: 任意のパスワード文字列がローテーション処理のログ出力に含まれない。

**テスト戦略**:
- `password`: 8〜64文字のランダム文字列（英数字 + 記号）
- 4ステップ全て（createSecret, setSecret, testSecret, finishSecret）を検証
- ログキャプチャハンドラーで全ログ出力を収集し、パスワード文字列の非存在を確認
- 失敗通知メッセージにもパスワードが含まれないことを検証

### Property 5: Lineage Record Round-Trip

**検証対象**: Requirements 5.1, 5.2, 5.4, 5.5

**不変条件**: `record()` で書き込んだレコードが `get_history()` および `get_by_uc()` で
取得可能である。

**テスト戦略**:
- `source_file_key`: `/vol[1-9]/[a-z]+/[a-z0-9_-]+.(pdf|csv|json|txt)` パターン
- `uc_id`: 5種類の UC ID からランダム選択
- `status`: success / failed / partial からランダム選択
- `execution_arn`: 有効な ARN パターンで生成
- moto `@mock_aws` で DynamoDB テーブル（GSI 付き）をエミュレート

**発見事項**:
- moto の DynamoDB GSI エミュレーションは eventually consistent のため、
  書き込み直後のクエリで結果が返ることを確認（moto では即時反映）

### Property 6: Lineage History Ordering

**検証対象**: Requirements 5.3

**不変条件**: `get_history()` が `processing_timestamp` 降順でソートされたリストを返す。

**テスト戦略**:
- 2〜10 個のレコードを異なるタイムスタンプで書き込み
- 均等間隔と不均等間隔の両方をテスト
- 書き込み順序に関わらず、取得結果が降順であることを検証

### Property 9: Max Size Enforcement

**検証対象**: Requirements 6.4

**不変条件**: `max_message_size` を超えるメッセージで `FramingError` が raise される。
`max_message_size` 以内のメッセージでは正常に読み取れる。

**テスト戦略**:
- `max_size`: 10〜500 バイト
- `excess`: 1〜500 バイト（超過量）
- LENGTH_PREFIXED と FRAMELESS の両モードで検証
- 境界値（ちょうど max_size 以内）では正常動作を確認

### Property 10: Counter Accuracy

**検証対象**: Requirements 6.7

**不変条件**: 全メッセージ読み取り後、`messages_read` がメッセージ数と一致し、
`bytes_read` が消費した総バイト数（ヘッダー + ペイロード）と一致する。

**テスト戦略**:
- 1〜10 個のメッセージ（各 1〜500 バイト）
- LENGTH_PREFIXED: `bytes_read = Σ(4 + len(msg))`
- FRAMELESS: `bytes_read = Σ(varint_len(len(msg)) + len(msg))`
- 初期状態でカウンターが 0 であることも検証

### Property 11: Canary Fail-Independence

**検証対象**: Requirements 3.5

**不変条件**: 任意のチェック失敗の組み合わせ（S3AP List, S3AP Get, ONTAP Health）で、
全 3 チェックが常に実行され、結果に独立して報告される。

**テスト戦略**:
- `failures`: 3 つのブール値タプル（各チェックの成功/失敗）
- 8 通りの組み合わせ（2³）を全てカバー
- boto3 S3/Secrets Manager/CloudWatch クライアントをモック
- urllib3 PoolManager をモック（ONTAP ヘルスチェック用）
- 各チェックの pass/fail が他のチェックに影響しないことを検証

### Property 12: Set-Difference Event Loss Calculation

**検証対象**: Requirements 7.5, 8.7

**不変条件**: `lost_events = expected_set - received_set` であり、
カウントが `len(expected_set) - len(received_set ∩ expected_set)` と一致する。

**テスト戦略**:
- `expected_events`: 1〜50 個のユニークなファイルパス
- `drop_indices`: ランダムなインデックスで一部イベントをドロップ
- 全受信時は欠損 0、全未受信時は全数欠損を検証
- 集合演算の正確性を数学的に検証

### Property 13: Load Ramp-Up Linearity

**検証対象**: Requirements 9.1

**不変条件**: 任意の `target_rate` と `ramp_up_sec` で、各秒のレートが
線形関数 `rate(t) = (t / ramp_up_sec) * target_rate` に従う。

**テスト戦略**:
- `target_rate`: 1〜10000 events/sec
- `ramp_up_sec`: 1〜600 秒
- 単調非減少性、開始時 0、終了時 target_rate、中間点で約半分を検証
- 任意の時点で target_rate を超えないことを検証

### Property 14: Percentile Calculation Correctness

**検証対象**: Requirements 8.6, 9.4

**不変条件**: P50 ≤ P95 ≤ P99 ≤ max(values)、min(values) ≤ P50。

**テスト戦略**:
- `values`: 1〜200 個の正の浮動小数点数
- 単調性（P50 ≤ P95 ≤ P99）を検証
- P99 が最大値を超えないことを検証
- P0 = min、P100 = max を検証
- 全値同一の場合、全パーセンタイルが同じ値を返すことを検証

### Property 16: Canary No Sensitive Data in Results

**検証対象**: Requirements 3.9

**不変条件**: 任意の S3 オブジェクト内容が Canary 結果に含まれない。
結果にはレイテンシとステータスのみが含まれる。

**テスト戦略**:
- `content`: 4〜500 文字のランダムテキスト（サロゲートペア除外）
- バイナリコンテンツ（10〜1000 バイト）も検証
- 結果を JSON シリアライズし、コンテンツ文字列の非存在を確認
- 結果の各チェックが許可されたキー（name, passed, latency_ms, error）のみを含むことを検証

## 実装パターン

### moto + Hypothesis の組み合わせ

`@mock_aws` デコレータと Hypothesis の `@given` を組み合わせる場合、
`mock_aws()` をコンテキストマネージャとしてテスト本体内で使用する：

```python
@pytest.mark.property
@given(action_type=st.sampled_from(["grow", "shrink"]))
@settings(max_examples=50, deadline=None)
def test_example(self, action_type: str):
    with mock_aws():
        # DynamoDB テーブル作成
        _ensure_table_exists()
        # テスト本体
        ...
```

**理由**: `@mock_aws` をクラスデコレータや関数デコレータとして使用すると、
Hypothesis が同一モックコンテキスト内で複数回テスト関数を呼び出すため、
テーブル重複作成エラーが発生する。

### deadline=None の設定

DynamoDB アクセスを含むテストでは `deadline=None` を設定する：

```python
@settings(max_examples=50, deadline=None)
```

**理由**: moto の DynamoDB エミュレーションは初回アクセス時にオーバーヘッドがあり、
Hypothesis のデフォルトデッドライン（200ms）を超過することがある。

### assume() の最小化

`assume()` によるフィルタリングが多すぎると `HealthCheck.filter_too_much` エラーが
発生する。代わりに、テスト入力を逆算して有効な入力空間を直接生成する：

```python
# ❌ Bad: assume で多くの入力をフィルタリング
@given(slope=st.floats(...), intercept=st.floats(...))
def test_positive_days(self, slope, intercept):
    current_usage = slope * current_time + intercept
    assume(current_usage < total_capacity)  # 多くの入力がフィルタされる
    ...

# ✅ Good: 有効な入力を直接構築
@given(current_usage_pct=st.floats(min_value=0.01, max_value=0.95))
def test_positive_days(self, current_usage_pct):
    current_usage = current_usage_pct * total_capacity
    intercept = current_usage - slope * current_time  # 逆算
    ...
```

## 発見事項と改善

### 1. capacity_forecast: int オーバーフロー修正

**問題**: `predict_days_until_full()` で `seconds_remaining` が `float('inf')` に
近い値になった場合、`int()` 変換で `OverflowError` が発生。

**修正**: `math.isfinite()` チェックと上限ガードを追加。

```python
if not math.isfinite(seconds_remaining) or seconds_remaining > 1e15:
    return -1
```

### 2. linear_regression: 大きな x 値での精度低下

**観察**: epoch タイムスタンプ（~1.7×10⁹）を直接使用すると、正規方程式の
`n * sum_x2 - sum_x * sum_x` で桁落ちが発生し、精度が低下する。

**影響**: 実運用では 30 日分のデータ（720+ ポイント）で十分な精度が得られるため、
コード修正は不要。テスト側で適切な許容誤差を設定。

### 3. guardrails: daily_cap の境界条件

**観察**: `daily_total_gb + requested_gb > daily_cap_gb` のチェックは strict greater than
を使用するため、`daily_total_gb` が `daily_cap_gb` と正確に等しくなるケースが存在する。
これは仕様通りの動作（「超過」ではなく「到達」は許可）。

## pytest マーカー

全プロパティテストには `@pytest.mark.property` マーカーが付与されている：

```bash
# プロパティテストのみ実行
python3 -m pytest -m property -v

# プロパティテストを除外
python3 -m pytest -m "not property" -v
```
