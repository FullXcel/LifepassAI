"""Small dependency-free semantic-ish retrieval for policy catalog search.

This is not a replacement for a production vector database.  It is a lightweight
TF-IDF retriever that makes policy search and RAG behavior visible in a fully
offline competition demo.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List

TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]{2,}")


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def policy_text(policy: Dict[str, Any]) -> str:
    chunks = [
        policy.get("name", ""), policy.get("domain", ""), policy.get("description", ""),
        policy.get("target", ""), " ".join(policy.get("required_docs", []) or []),
    ]
    rule = policy.get("rule", {})
    chunks.append(str(rule))
    return " ".join(map(str, chunks))


def search_policies(query: str, policies: Iterable[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
    items = list(policies)
    query_tokens = tokenize(query)
    if not query_tokens or not items:
        return []
    docs = [tokenize(policy_text(p)) for p in items]
    df = Counter()
    for tokens in docs:
        for token in set(tokens):
            df[token] += 1
    n = len(docs)
    q_tf = Counter(query_tokens)

    def weight(token: str, tf: int) -> float:
        return (1 + math.log(tf)) * math.log((n + 1) / (df.get(token, 0) + 1) + 1)

    q_vec = {t: weight(t, c) for t, c in q_tf.items()}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
    scored: List[Dict[str, Any]] = []
    for policy, tokens in zip(items, docs):
        tf = Counter(tokens)
        p_vec = {t: weight(t, c) for t, c in tf.items() if t in q_vec}
        dot = sum(q_vec[t] * p_vec.get(t, 0.0) for t in q_vec)
        p_norm = math.sqrt(sum(v * v for v in p_vec.values())) or 1.0
        score = dot / (q_norm * p_norm) if dot else 0.0
        if score > 0:
            scored.append({
                "id": policy.get("id"),
                "name": policy.get("name"),
                "domain": policy.get("domain"),
                "score": round(score, 4),
                "description": str(policy.get("description", ""))[:260],
                "source": (policy.get("provenance") or {}).get("source_system", "catalog"),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
