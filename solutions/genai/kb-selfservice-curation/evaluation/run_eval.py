#!/usr/bin/env python3
"""UC29 RAG 評価ハーネス（GENOPS01）

評価データセット（uc29-eval-dataset.json）を Query Lambda に投げ、
citation 整合 / no-answer 挙動を採点してレポートを出力する。

CI ではスコアリングの純粋関数を単体テストで検証する（AWS 不要）。
実 AWS 評価は手動/ローカルで実行する:

  python3 run_eval.py --function-name <QueryFn> --threshold 0.8
  python3 run_eval.py --mock fixtures.json            # ライブ呼び出しなし

> 評価は特定データセットでの相対比較。スコアは品質傾向の参照であり保証値ではない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# no-answer とみなす代表表現（推測抑制の確認用）
_NO_ANSWER_MARKERS = [
    "情報が含まれていません",
    "情報が不足",
    "わかりません",
    "分かりません",
    "特定することはできません",
    "見つかりませんでした",
    "提供されていません",
]


def is_no_answer(answer: str) -> bool:
    """回答が「情報なし/推測しない」系かを判定する。"""
    if not answer or not answer.strip():
        return True
    return any(m in answer for m in _NO_ANSWER_MARKERS)


def _citation_sources(result: dict[str, Any]) -> list[str]:
    return [c.get("source", "") for c in result.get("citations", []) if c.get("source")]


def score_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """1 ケースを採点する。

    - expected_behavior == "no_answer": no-answer を返せば pass
    - それ以外: expected_source が citations のいずれかに含まれれば pass
    """
    answer = result.get("answer", "") or ""
    expected_behavior = case.get("expected_behavior")
    if expected_behavior == "no_answer":
        ok = is_no_answer(answer)
        return {"id": case.get("id"), "type": "no_answer", "passed": ok, "no_answer": ok}

    expected = case.get("expected_source") or ""
    sources = _citation_sources(result)
    matched = any(expected and expected in s for s in sources)
    return {
        "id": case.get("id"),
        "type": "citation",
        "passed": bool(matched),
        "citation_match": bool(matched),
        "expected_source": expected,
        "got_sources": sources,
    }


def summarize(scored: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scored)
    passed = sum(1 for s in scored if s.get("passed"))
    citation_cases = [s for s in scored if s.get("type") == "citation"]
    citation_pass = sum(1 for s in citation_cases if s.get("passed"))
    no_answer_cases = [s for s in scored if s.get("type") == "no_answer"]
    no_answer_pass = sum(1 for s in no_answer_cases if s.get("passed"))
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "citation_pass_rate": round(citation_pass / len(citation_cases), 3) if citation_cases else None,
        "no_answer_pass_rate": round(no_answer_pass / len(no_answer_cases), 3) if no_answer_cases else None,
    }


def load_dataset(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("cases", [])


def _invoke_live(function_name: str, query: str, region: str) -> dict[str, Any]:
    import boto3

    client = boto3.client("lambda", region_name=region)
    resp = client.invoke(
        FunctionName=function_name,
        Payload=json.dumps({"query": query}).encode("utf-8"),
    )
    return json.loads(resp["Payload"].read())


def main() -> int:
    p = argparse.ArgumentParser(description="UC29 RAG evaluation harness")
    p.add_argument("--dataset", default=os.path.join(os.path.dirname(__file__), "uc29-eval-dataset.json"))
    p.add_argument("--function-name", default="")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-northeast-1"))
    p.add_argument("--mock", default="", help="ライブ呼び出しの代わりに使う {id: result} JSON")
    p.add_argument("--threshold", type=float, default=0.8, help="pass_rate のしきい値（下回ると exit 1）")
    p.add_argument("--out", default="")
    args = p.parse_args()

    cases = load_dataset(args.dataset)
    mock = {}
    if args.mock:
        with open(args.mock, encoding="utf-8") as f:
            mock = json.load(f)

    scored = []
    for case in cases:
        if args.mock:
            result = mock.get(case["id"], {})
        elif args.function_name:
            result = _invoke_live(args.function_name, case["query"], args.region)
        else:
            print("ERROR: --function-name か --mock のいずれかが必要")
            return 2
        scored.append(score_case(case, result))

    summary = summarize(scored)
    report = {"summary": summary, "cases": scored}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)

    if summary["pass_rate"] < args.threshold:
        print(f"FAIL: pass_rate {summary['pass_rate']} < threshold {args.threshold}")
        return 1
    print(f"PASS: pass_rate {summary['pass_rate']} >= threshold {args.threshold}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
