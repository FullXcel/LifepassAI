"""Embedding policy retrieval wrapper.

``search_policies`` is kept as the public function used by the existing UI/API,
but it now delegates to the embedding RAG module. If no external embedding model
is configured, the same function uses a deterministic local vector fallback.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .embedding_rag import semantic_search


def search_policies(query: str, policies: Iterable[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
    result = semantic_search(query, policies, top_k=top_k)
    rows: List[Dict[str, Any]] = []
    for hit in result.get("hits", []):
        rows.append({
            "id": (hit.get("metadata") or {}).get("benefit_id", hit.get("chunk_id")),
            "name": hit.get("title"),
            "domain": (hit.get("metadata") or {}).get("domain", hit.get("source_type")),
            "score": hit.get("score", 0),
            "description": str(hit.get("text", ""))[:260],
            "source": hit.get("source", "embedding_rag"),
            "source_type": hit.get("source_type", "unknown"),
            "embedding_provider": result.get("embedding", {}).get("provider", result.get("embedding", {}).get("provider_requested", "local_hash")),
        })
    return rows
