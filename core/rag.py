"""Tiny local retrieval module used for grounded explanations in the MVP."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

DEFAULT_KB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"


def load_kb(path: str | Path = DEFAULT_KB_PATH) -> List[Dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text.lower()))


def retrieve(query: str, top_k: int = 3, kb: List[Dict] | None = None) -> List[Dict]:
    kb = kb or load_kb()
    q = _tokens(query)
    scored = []
    for item in kb:
        hay = _tokens(" ".join([item.get("title", ""), item.get("text", ""), " ".join(item.get("keywords", []))]))
        score = len(q & hay)
        # Keyword exact bonus for Korean compound terms.
        for kw in item.get("keywords", []):
            if kw.lower() in query.lower():
                score += 3
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def explain_with_evidence(query: str) -> str:
    docs = retrieve(query, top_k=2)
    if not docs:
        return "관련 근거 문서를 찾지 못했습니다. 실제 서비스에서는 복지로/정부24/고용24 최신 공고 RAG를 연결해야 합니다."
    lines = []
    for doc in docs:
        lines.append(f"- {doc['title']}: {doc['text']}")
    return "\n".join(lines)
