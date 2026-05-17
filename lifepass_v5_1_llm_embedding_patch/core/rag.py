"""Grounded retrieval module for LifePass.

The original MVP used keyword matching only. This file now delegates to
``core.embedding_rag`` so policy explanations can use embedding retrieval when a
real embedding provider is configured, while still falling back safely in local
competition demos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from .embedding_rag import build_rag_context, semantic_search
from .benefit_catalog import load_benefits

DEFAULT_KB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"


def load_kb(path: str | Path = DEFAULT_KB_PATH) -> List[Dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text.lower()))


def _keyword_retrieve(query: str, top_k: int = 3, kb: List[Dict] | None = None) -> List[Dict]:
    kb = kb or load_kb()
    q = _tokens(query)
    scored = []
    for item in kb:
        hay = _tokens(" ".join([item.get("title", ""), item.get("text", ""), " ".join(item.get("keywords", []))]))
        score = len(q & hay)
        for kw in item.get("keywords", []):
            if kw.lower() in query.lower():
                score += 3
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def retrieve(query: str, top_k: int = 3, kb: List[Dict] | None = None) -> List[Dict]:
    """Retrieve evidence documents.

    Returns dictionaries compatible with the old UI shape: ``title``, ``text``,
    ``source`` and optional ``score``. If embedding retrieval fails for any
    reason, the legacy keyword fallback is used.
    """
    try:
        results = semantic_search(query, load_benefits(), top_k=top_k)
        hits = results.get("hits", [])
        if hits:
            return [
                {
                    "title": h.get("title", "근거"),
                    "text": h.get("text", ""),
                    "source": h.get("source", "embedding_rag"),
                    "score": h.get("score", 0),
                    "source_type": h.get("source_type", "unknown"),
                }
                for h in hits[:top_k]
            ]
    except Exception:
        pass
    return _keyword_retrieve(query, top_k=top_k, kb=kb)


def explain_with_evidence(query: str) -> str:
    try:
        bundle = build_rag_context(query, load_benefits(), top_k=3)
        hits = bundle.get("hits", [])
        if not hits:
            return "관련 근거 문서를 찾지 못했습니다. 실제 서비스에서는 복지로/정부24/고용24 최신 공고 RAG를 연결해야 합니다."
        lines = [
            f"- {hit['title']} (score={hit.get('score', 0)}): {hit['text'][:420]}"
            for hit in hits[:3]
        ]
        meta = bundle.get("embedding", {})
        lines.append(f"\n검색 방식: {meta.get('provider', meta.get('provider_requested', 'embedding_rag'))} / model={meta.get('model', meta.get('model_requested', 'unknown'))}")
        return "\n".join(lines)
    except Exception:
        docs = _keyword_retrieve(query, top_k=2)
        if not docs:
            return "관련 근거 문서를 찾지 못했습니다. 실제 서비스에서는 복지로/정부24/고용24 최신 공고 RAG를 연결해야 합니다."
        return "\n".join([f"- {doc['title']}: {doc['text']}" for doc in docs])
