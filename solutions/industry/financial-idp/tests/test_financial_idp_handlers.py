"""UC2 金融・保険 IDP Lambda ハンドラー ユニットテスト

## このファイルの方針

以前は「ハンドラのソースに特定の文字列が現れるか」を検査していた。たとえば
`assert "seen_keys" in content` や `assert "analyze_document" in content` である。
この形の検査は次の 2 方向に弱い。

- 通るのに壊れている: `seen_keys` という名前の変数があっても、重複排除に使われて
  いなければ検査は通る。実装がコメントアウトされていても、その文字列が残っていれば
  やはり通る。
- 壊れていないのに落ちる: 変数名を変えたり、処理を共通ヘルパーへ移したりすると、
  振る舞いは同じでも検査が落ちる。実際 `SUFFIX_FILTER` の読み取りを
  `shared/suffix_filter.py` に移した際にこれが起きた。

そこでハンドラを実行し、S3 AP / Textract への呼び出しと返り値を見る形に置き換えて
いる。テンプレートについても、YAML を解析して `Parameters` と
`Environment.Variables` を見る（部分文字列検査では、コメント中の文字列や別の
リソースの設定でも通ってしまう）。

## 書くときの注意: SUFFIX_FILTER を明示する

ハーネスの既定は `SUFFIX_FILTER=".txt"` で、サフィックスは 1 つしか照会されない。
Discovery は「サフィックスごとに list_objects を呼び、あとで重複排除する」構造なので、
1 サフィックスだと重複が発生せず、重複排除を丸ごと外しても、件数を重複排除前から
取っても、どちらもテストが通ってしまう。実際に変異を入れて確認した（3 件が生き残った）。

重複排除・件数・走査範囲を見るテストでは
`env={"SUFFIX_FILTER": ".pdf,.tiff,.jpg"}` のように複数指定するか、既定へ倒すために
空文字を渡すこと。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(REPO_ROOT / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.testing import load_pattern_handler, load_sam_template  # noqa: E402

PATTERN_DIR = Path(__file__).resolve().parents[1]
DISCOVERY_HANDLER = "solutions/industry/financial-idp/functions/discovery/handler.py"
OCR_HANDLER = "solutions/industry/financial-idp/functions/ocr/handler.py"
TEMPLATE = PATTERN_DIR / "template.yaml"


# =========================================================================
# Discovery Handler
# =========================================================================


class TestDiscoveryHandler:
    """Discovery ハンドラの振る舞い"""

    def test_returns_objects_and_manifest_key(self, monkeypatch):
        """返り値に objects と manifests/ 配下の manifest_key が含まれる

        後続の Map ステートが `objects` を読むため、キー名は実質的な API である。
        manifest の置き場所も同様に、他のパターンや運用者が前提にしている。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=[{"Key": "docs/a.pdf", "Size": 10, "ETag": "e"}],
        )

        result = harness.handler({}, harness.context)

        assert "objects" in result, f"expected an 'objects' key, got {sorted(result)}"
        assert result["manifest_key"].startswith("manifests/"), (
            f"manifest written outside manifests/: {result['manifest_key']}"
        )

    def test_scans_every_document_suffix(self, monkeypatch):
        """PDF / TIFF / JPEG の各表記を実際に照会している

        金融文書はスキャナ由来で `.tif` と `.tiff`、`.jpg` と `.jpeg` が混在する。
        片方だけを見ていると、取り込み漏れがエラーではなく「0 件で成功」として出る。

        `SUFFIX_FILTER` を空にして既定へ倒す。ハーネスの既定値は `.txt` なので、
        そのままだと 1 サフィックスしか照会せず「全部見ている」ことを確かめられない。
        照会した内容を記録するため、ここでは S3 AP 代替を自前で差し替える。
        """
        queried: list[str] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                pass

            def list_objects(self, prefix="", suffix="", max_keys=1000):
                queried.append(suffix)
                return []

            def put_object(self, **kw):
                return {}

        harness = load_pattern_handler(DISCOVERY_HANDLER, monkeypatch, env={"SUFFIX_FILTER": ""})
        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({}, harness.context)

        assert set(queried) >= {".pdf", ".tiff", ".tif", ".jpeg", ".jpg"}, (
            f"the handler only queried {sorted(set(queried))}. A scanner-produced "
            "extension is not being scanned, which shows up as '0 objects, success'."
        )

    def test_deduplicates_objects_returned_by_more_than_one_query(self, monkeypatch):
        """複数のサフィックス照会で同じキーが返っても 1 件になる

        走査はサフィックスごとに list_objects を呼ぶため、同じオブジェクトが複数回
        返り得る。重複したまま Map に渡すと同じ文書を 2 回 OCR することになり、
        Textract の課金とレポートの件数がどちらもずれる。

        `SUFFIX_FILTER` に複数指定するのが要点。1 つだけだとループが 1 回で終わり、
        重複が発生しないので重複排除を外しても落ちない（実際に外して確認した）。
        """
        duplicated = {"Key": "docs/same.pdf", "Size": 10, "ETag": "e"}
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".pdf,.tiff,.jpg"},
            # ハーネスは照会ごとに同じ一覧を返すので、サフィックス数だけ重複する
            objects=[duplicated],
        )

        result = harness.handler({}, harness.context)

        keys = [obj["Key"] for obj in result["objects"]]
        assert len([c for c in harness.calls if c == "list_objects"]) >= 2, (
            "this test needs at least two suffix queries for a duplicate to arise"
        )
        assert keys.count("docs/same.pdf") == 1, (
            f"the same key survived more than once: {keys}. Deduplication is not happening between suffix queries."
        )

    def test_total_objects_counts_after_deduplication(self, monkeypatch):
        """total_objects が重複排除後の件数と一致する

        重複排除の前を数えると、同じ文書を複数のサフィックス照会で拾った分だけ
        件数が膨らむ。オブジェクト一覧は正しいのに件数だけが多い状態になり、
        レポートと実際の処理数が食い違う。

        ここも複数サフィックスが必須。1 つだと重複前後が同じ値になり、
        どちらを数えていても通る。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".pdf,.tiff,.jpg"},
            objects=[{"Key": "docs/a.pdf", "Size": 1, "ETag": "e"}],
        )

        result = harness.handler({}, harness.context)

        assert len(result["objects"]) == 1, "the fixture should collapse to a single object"
        assert result["total_objects"] == len(result["objects"]), (
            f"total_objects={result['total_objects']} but objects has {len(result['objects'])} "
            "entries — the count is being taken before deduplication"
        )

    def test_list_failure_propagates(self, monkeypatch):
        """S3 AP の一覧取得が失敗したら例外が伝播する

        検出が失敗したのに成功として返すと、後続は空の入力を正常処理として扱い、
        「処理対象 0 件」で終わる。障害が見えなくなる。
        """
        harness = load_pattern_handler(DISCOVERY_HANDLER, monkeypatch, fail_on="list_objects")

        with pytest.raises(Exception) as excinfo:
            harness.handler({}, harness.context)

        assert "injected failure" in str(excinfo.value)


# =========================================================================
# OCR Handler
# =========================================================================


class TestSelectTextractApi:
    """select_textract_api の分岐

    Textract は同期 API に 1 リクエスト 1 ページの制限があるため、この分岐を
    間違えると複数ページ文書が黙って 1 ページ分しか読まれない。
    """

    @pytest.fixture()
    def ocr(self, monkeypatch):
        return load_pattern_handler(OCR_HANDLER, monkeypatch).module

    @pytest.mark.parametrize(
        ("page_count", "threshold", "expected"),
        [
            (1, 1, "sync"),  # 閾値と同じなら同期
            (2, 1, "async"),  # 閾値を 1 超えたら非同期
            (5, 5, "sync"),
            (6, 5, "async"),
            (0, 1, "sync"),  # ページ数不明で 0 のときも同期側に寄せる
        ],
    )
    def test_boundary(self, ocr, page_count, threshold, expected):
        assert ocr.select_textract_api(page_count, threshold=threshold) == expected

    def test_threshold_is_inclusive(self, ocr):
        """閾値そのものは同期側に含まれる

        `<` と `<=` の取り違えは、ちょうど閾値のページ数の文書だけを非同期に送る。
        件数が少ないので気づきにくい。
        """
        assert ocr.select_textract_api(3, threshold=3) == "sync"
        assert ocr.select_textract_api(4, threshold=3) == "async"


class TestOcrHandler:
    """OCR ハンドラの振る舞い"""

    def _textract(self, monkeypatch, harness, sync_text="synced", async_text="asynced"):
        """Textract クライアントを差し替え、呼ばれた API を記録する"""
        seen: list[str] = []

        def fake_sync(client, document_bytes):
            seen.append("analyze_document")
            return sync_text

        def fake_async(client, bucket, key):
            seen.append("start_document_analysis")
            return async_text

        monkeypatch.setattr(harness.module, "_extract_text_sync", fake_sync)
        monkeypatch.setattr(harness.module, "_extract_text_async", fake_async)
        monkeypatch.setattr(harness.module.boto3, "client", lambda *a, **kw: MagicMock())
        return seen

    def test_single_page_uses_the_sync_api_and_reads_the_object(self, monkeypatch):
        """1 ページなら同期 API を使い、S3 AP から本体を読む

        同期 API はバイト列を受け取るので、get_object が必要になる。
        """
        harness = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "1"})
        seen = self._textract(monkeypatch, harness)

        result = harness.handler({"Key": "docs/one.pdf", "Size": 1000, "page_count": 1}, harness.context)

        assert result["api_mode"] == "sync"
        assert seen == ["analyze_document"], f"expected the sync API, got {seen}"
        assert "get_object" in harness.calls, "the sync path must fetch the document bytes; get_object was never called"
        assert result["extracted_text"] == "synced"

    def test_multi_page_uses_the_async_api_without_downloading(self, monkeypatch):
        """複数ページなら非同期 API を使い、本体はダウンロードしない

        非同期 API は S3 の場所を渡す。ここで get_object を呼ぶと、Lambda が
        大きな文書を丸ごとメモリに載せることになり、非同期にした意味がなくなる。
        """
        harness = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "1"})
        seen = self._textract(monkeypatch, harness)

        result = harness.handler({"Key": "docs/many.pdf", "Size": 5_000_000, "page_count": 50}, harness.context)

        assert result["api_mode"] == "async"
        assert seen == ["start_document_analysis"], f"expected the async API, got {seen}"
        assert "get_object" not in harness.calls, (
            "the async path passes an S3 location and must not download the document"
        )

    def test_threshold_comes_from_the_environment(self, monkeypatch):
        """TEXTRACT_PAGE_THRESHOLD が実際に分岐を動かす

        テンプレートがこのノブを渡しているので、編集しても効かなければ
        運用者を誤解させる。
        """
        event = {"Key": "docs/five.pdf", "Size": 1000, "page_count": 5}

        low = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "1"})
        self._textract(monkeypatch, low)
        assert low.handler(event, low.context)["api_mode"] == "async"

        high = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "10"})
        self._textract(monkeypatch, high)
        assert high.handler(event, high.context)["api_mode"] == "sync"

    def test_page_count_is_estimated_from_size_when_absent(self, monkeypatch):
        """page_count が無いときはファイルサイズから推定する（最低 1）

        推定が 0 を返すと、閾値比較で常に同期側になる。100KB/ページの前提を
        変えるときはこのテストが落ちるので、意図しない変更に気づける。
        """
        harness = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "1"})
        self._textract(monkeypatch, harness)

        tiny = harness.handler({"Key": "docs/tiny.pdf", "Size": 10}, harness.context)
        assert tiny["page_count"] == 1, "an almost-empty document must still count as one page"

        big = harness.handler({"Key": "docs/big.pdf", "Size": 350_000}, harness.context)
        assert big["page_count"] == 3, f"350KB should estimate 3 pages, got {big['page_count']}"

    def test_textract_failure_returns_empty_text_instead_of_raising(self, monkeypatch):
        """Textract が失敗しても例外にせず、空テキストと error を返す

        Map ステートの 1 件が失敗しても全体を止めない、という設計。空文字で返す
        ことと `error` を載せることの両方が必要で、`error` が無いと下流は
        「本当に文字が無い文書」と区別できない。
        """
        harness = load_pattern_handler(OCR_HANDLER, monkeypatch, env={"TEXTRACT_PAGE_THRESHOLD": "1"})

        def boom(*a, **kw):
            raise RuntimeError("Textract unavailable")

        # 両方の抽出関数を差し替える。片方だけにすると、sync/async の選択が
        # 変わった瞬間に本物の `_extract_text_async` が動く。あれは
        # `while True: ... time.sleep(5)` で Textract ジョブの完了を待つので、
        # MagicMock 相手では JobStatus が "SUCCEEDED" にならず終わらない。
        # このテストは「どちらの経路でも失敗を飲み込む」ことを見たいので、
        # 経路の選択に依存させない。
        monkeypatch.setattr(harness.module, "_extract_text_sync", boom)
        monkeypatch.setattr(harness.module, "_extract_text_async", boom)
        monkeypatch.setattr(harness.module.boto3, "client", lambda *a, **kw: MagicMock())

        result = harness.handler({"Key": "docs/bad.pdf", "Size": 100, "page_count": 1}, harness.context)

        assert result["extracted_text"] == ""
        assert "Textract unavailable" in result["error"], (
            "the failure reason must survive into the result, or a failed page is "
            "indistinguishable from a genuinely blank one"
        )
        assert result["document_key"] == "docs/bad.pdf", "the key must be preserved for the report"

    def test_result_carries_the_keys_the_next_state_reads(self, monkeypatch):
        """後続ステートが読むキーが揃っている"""
        harness = load_pattern_handler(OCR_HANDLER, monkeypatch)
        self._textract(monkeypatch, harness)

        result = harness.handler({"Key": "docs/a.pdf", "Size": 100, "page_count": 1}, harness.context)

        for key in ("document_key", "extracted_text", "page_count", "api_mode"):
            assert key in result, f"missing {key!r} in {sorted(result)}"


# =========================================================================
# CloudFormation テンプレート
# =========================================================================


class TestTemplateConsistency:
    """テンプレートの整合性

    部分文字列検査ではなく YAML を解析する。`"EnableVpcEndpoints" in content` は
    コメントや別リソースの記述でも通ってしまい、パラメータが実在するかを
    確かめられない。
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def template():
        return load_sam_template(TEMPLATE)

    def test_both_templates_exist(self):
        assert TEMPLATE.exists()
        assert (PATTERN_DIR / "template-deploy.yaml").exists()

    @pytest.mark.parametrize(
        "name",
        ["EnableVpcEndpoints", "EnableS3GatewayEndpoint", "PrivateRouteTableIds"],
    )
    def test_declares_networking_parameter(self, template, name):
        assert name in template.parameters, (
            f"{name} is not a template parameter (declared: {sorted(template.parameters)})"
        )

    def test_discovery_receives_a_suffix_filter_covering_pdf(self, template):
        """SUFFIX_FILTER が DiscoveryFunction に渡り、.pdf を含む

        値まで見る。キーだけ確認しても、`.pdf` が抜けていれば主要な入力形式を
        取りこぼしたまま通ってしまう。
        """
        env = template.function_env("DiscoveryFunction")
        assert "SUFFIX_FILTER" in env, f"DiscoveryFunction does not receive SUFFIX_FILTER (has: {sorted(env)})"
        assert ".pdf" in str(env["SUFFIX_FILTER"]), f"SUFFIX_FILTER does not cover .pdf: {env['SUFFIX_FILTER']!r}"

    def test_no_condition_references_a_missing_parameter(self, template):
        """Conditions が存在しないパラメータを参照していない

        パラメータを消したのに Conditions の !Ref が残っている、という壊れ方は
        デプロイ時にしか出ない。部分文字列検査では検出できない。
        """
        dangling = template.undefined_condition_refs()
        assert not dangling, f"Conditions reference undefined names: {sorted(dangling)}"
