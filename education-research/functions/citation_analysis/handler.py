"""教育 / 研究 引用ネットワーク分析 Lambda ハンドラ

参考文献セクションから引用関係を解析し、引用隣接リスト
（nodes, edges, total_papers, total_citations）を構築する。
JSON で S3 出力する。

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def extract_references_section(text: str) -> str:
    """テキストから参考文献セクションを抽出する

    Args:
        text: 論文全文テキスト

    Returns:
        str: 参考文献セクションのテキスト
    """
    # 参考文献セクションのヘッダーパターン
    patterns = [
        r"(?i)\n\s*references?\s*\n",
        r"(?i)\n\s*bibliography\s*\n",
        r"(?i)\n\s*参考文献\s*\n",
        r"(?i)\n\s*引用文献\s*\n",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return text[match.end():]

    return ""


def parse_references(references_text: str) -> list[dict]:
    """参考文献テキストから個別の引用を解析する

    Args:
        references_text: 参考文献セクションのテキスト

    Returns:
        list[dict]: 解析された引用のリスト
    """
    references = []

    # [1], [2], ... パターン
    numbered_pattern = r"\[(\d+)\]\s*(.+?)(?=\[\d+\]|\Z)"
    numbered_matches = re.findall(numbered_pattern, references_text, re.DOTALL)

    if numbered_matches:
        for num, text in numbered_matches:
            ref = _parse_single_reference(text.strip(), int(num))
            if ref:
                references.append(ref)
        return references

    # 番号なしの行ベースパターン
    lines = references_text.strip().split("\n")
    ref_num = 1
    current_ref = ""

    for line in lines:
        line = line.strip()
        if not line:
            if current_ref:
                ref = _parse_single_reference(current_ref, ref_num)
                if ref:
                    references.append(ref)
                    ref_num += 1
                current_ref = ""
        else:
            current_ref += " " + line if current_ref else line

    # 最後の参考文献
    if current_ref:
        ref = _parse_single_reference(current_ref, ref_num)
        if ref:
            references.append(ref)

    return references


def _parse_single_reference(text: str, ref_num: int) -> dict | None:
    """単一の参考文献エントリを解析する

    Args:
        text: 参考文献テキスト
        ref_num: 参考文献番号

    Returns:
        dict | None: 解析された参考文献、または None
    """
    if len(text) < 10:
        return None

    # 著者名の抽出（最初のピリオドまで）
    author_match = re.match(r"^(.+?)\.\s*", text)
    authors = author_match.group(1).strip() if author_match else "Unknown"

    # 年の抽出
    year_match = re.search(r"\((\d{4})\)|(\d{4})", text)
    year = year_match.group(1) or year_match.group(2) if year_match else "Unknown"

    # タイトルの抽出（引用符内、またはピリオド間）
    title_match = re.search(r'"(.+?)"|"(.+?)"', text)
    if title_match:
        title = title_match.group(1) or title_match.group(2)
    else:
        # ピリオド間のテキストをタイトルとして使用
        parts = text.split(".")
        title = parts[1].strip() if len(parts) > 1 else text[:100]

    return {
        "ref_id": f"ref_{ref_num}",
        "authors": authors,
        "year": year,
        "title": title[:200],
        "raw_text": text[:500],
    }


def build_citation_network(
    papers: list[dict],
) -> dict:
    """複数論文の引用関係から引用ネットワークを構築する

    Args:
        papers: 論文データのリスト。各論文は以下の形式:
            {
                "paper_id": str,
                "title": str,
                "references": list[dict]
            }

    Returns:
        dict: 引用ネットワーク
            {
                "nodes": [...],
                "edges": [...],
                "total_papers": int,
                "total_citations": int
            }
    """
    nodes = []
    edges = []
    seen_edges: set[tuple[str, str]] = set()

    # ノード生成
    paper_ids = set()
    for paper in papers:
        paper_id = paper.get("paper_id", "")
        if paper_id and paper_id not in paper_ids:
            paper_ids.add(paper_id)
            nodes.append({
                "id": paper_id,
                "title": paper.get("title", ""),
                "type": "paper",
            })

    # エッジ生成（引用関係）
    for paper in papers:
        source_id = paper.get("paper_id", "")
        if not source_id:
            continue

        for ref in paper.get("references", []):
            target_id = ref.get("ref_id", "")
            if not target_id:
                continue

            # ターゲットノードが存在しない場合は追加
            if target_id not in paper_ids:
                paper_ids.add(target_id)
                nodes.append({
                    "id": target_id,
                    "title": ref.get("title", ""),
                    "type": "reference",
                })

            # 重複エッジ防止
            edge_key = (source_id, target_id)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "source": source_id,
                    "target": target_id,
                    "type": "cites",
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "total_papers": len(nodes),
        "total_citations": len(edges),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """引用ネットワーク分析

    Input:
        {
            "papers": [
                {
                    "file_key": "papers/paper1.pdf",
                    "paper_id": "paper_001",
                    "title": "...",
                    "extracted_text": "..."
                },
                ...
            ]
        }

    Output:
        {
            "status": "SUCCESS",
            "citation_network": {
                "nodes": [...],
                "edges": [...],
                "total_papers": 10,
                "total_citations": 45
            },
            "output_key": "..."
        }
    """
    papers_input = event.get("papers", [])
    output_bucket = os.environ["OUTPUT_BUCKET"]

    logger.info("Citation analysis started: papers=%d", len(papers_input))

    # 各論文の参考文献を解析
    papers_with_refs = []
    for paper in papers_input:
        extracted_text = paper.get("extracted_text", "")
        references_section = extract_references_section(extracted_text)
        references = parse_references(references_section)

        papers_with_refs.append({
            "paper_id": paper.get("paper_id", paper.get("file_key", "")),
            "title": paper.get("title", ""),
            "references": references,
        })

    # 引用ネットワーク構築
    citation_network = build_citation_network(papers_with_refs)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    output_key = f"citations/{now.strftime('%Y/%m/%d')}/citation_network.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "citation_network": citation_network,
        "output_key": output_key,
        "analyzed_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Citation analysis completed: nodes=%d, edges=%d",
        citation_network["total_papers"],
        citation_network["total_citations"],
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="citation_analysis")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "education-research"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
