"""Embedding-backed RAG utilities for LifePass.

This module upgrades the earlier keyword/TF-IDF style retrieval into an
embedding-first retrieval layer while staying safe for offline competition demos.

Provider strategy
-----------------
1. OpenAI embedding API if ``LIFEPASS_EMBEDDING_PROVIDER=openai`` and
   ``OPENAI_API_KEY`` are configured.
2. sentence-transformers if ``LIFEPASS_EMBEDDING_PROVIDER=sentence_transformers``
   and the package/model are installed in the runtime image.
3. Deterministic local hashing vector as a dependency-free fallback.

The fallback is intentionally kept because judges and teammates may run the
project without API keys. When an embedding provider is configured, the same RAG
pipeline transparently uses the real embedding model. Eligibility decisions do
not depend on LLM or embedding output; retrieval is used only for evidence,
explanation, and counseling support.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "knowledge_base.json"
POLICY_DOCS_PATH = ROOT / "data" / "policy_docs.md"
TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]{2,}")


@dataclass
class RAGChunk:
    chunk_id: str
    title: str
    text: str
    source: str
    source_type: str
    metadata: Dict[str, Any]


@dataclass
class RAGHit:
    chunk_id: str
    title: str
    text: str
    source: str
    source_type: str
    score: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def _normalize(vec: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [float(v) / norm for v in vec]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(float(a[i]) * float(b[i]) for i in range(n))


def _hash_embedding(text: str, dim: int = 384) -> List[float]:
    """Dependency-free semantic-ish vector fallback.

    This is not a deep neural embedding model. It is a stable vectorizer that
    keeps the demo operational without secrets or network calls. When OpenAI or
    sentence-transformers is configured, this fallback is replaced by the actual
    embedding model.
    """
    vec = [0.0] * dim
    tokens = _tokens(text)
    if not tokens:
        return vec
    for token in tokens:
        # Unigram contribution.
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    # Light bigram contribution improves Korean compound matching.
    for left, right in zip(tokens, tokens[1:]):
        token = f"{left}_{right}"
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 0.6 if digest[4] % 2 == 0 else -0.6
        vec[idx] += sign
    return _normalize(vec)


def _openai_embeddings(texts: Sequence[str]) -> List[List[float]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    model = os.getenv("LIFEPASS_EMBEDDING_MODEL", "text-embedding-3-small")
    payload = json.dumps({"model": model, "input": list(texts)}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("LIFEPASS_OPENAI_TIMEOUT", "20"))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - requires external API
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI embedding API error: {exc.code} {detail[:300]}") from exc
    data = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
    return [_normalize(item.get("embedding", [])) for item in data]


def _sentence_transformer_embeddings(texts: Sequence[str]) -> List[List[float]]:
    model_name = os.getenv("LIFEPASS_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("sentence-transformers is not installed") from exc
    model = SentenceTransformer(model_name)
    vectors = model.encode(list(texts), normalize_embeddings=True)
    return [[float(v) for v in row] for row in vectors]


def embed_texts(texts: Sequence[str]) -> tuple[List[List[float]], Dict[str, Any]]:
    """Return embeddings plus provider metadata.

    The function never crashes the dashboard because of a missing API key. If a
    configured provider fails, it records the warning and falls back to the local
    vectorizer.
    """
    provider = os.getenv("LIFEPASS_EMBEDDING_PROVIDER", "local_hash").strip().lower()
    if provider in {"openai", "text-embedding-3-small", "text-embedding"}:
        try:
            vectors = _openai_embeddings(texts)
            return vectors, {"provider": "openai", "model": os.getenv("LIFEPASS_EMBEDDING_MODEL", "text-embedding-3-small"), "fallback": False}
        except Exception as exc:  # noqa: BLE001
            vectors = [_hash_embedding(t) for t in texts]
            return vectors, {"provider": "local_hash", "model": "local-hash-ko-384", "fallback": True, "warning": str(exc)}
    if provider in {"sentence_transformers", "sentence-transformers", "sbert"}:
        try:
            vectors = _sentence_transformer_embeddings(texts)
            return vectors, {"provider": "sentence_transformers", "model": os.getenv("LIFEPASS_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"), "fallback": False}
        except Exception as exc:  # noqa: BLE001
            vectors = [_hash_embedding(t) for t in texts]
            return vectors, {"provider": "local_hash", "model": "local-hash-ko-384", "fallback": True, "warning": str(exc)}
    vectors = [_hash_embedding(t) for t in texts]
    return vectors, {"provider": "local_hash", "model": "local-hash-ko-384", "fallback": False}


def _safe_read_json(path: Path) -> Any:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _split_markdown_docs(text: str) -> List[tuple[str, str]]:
    if not text.strip():
        return []
    sections: List[tuple[str, str]] = []
    current_title = "정책 문서"
    current_lines: List[str] = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
                current_lines = []
            current_title = line.strip("# ") or current_title
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, body) for title, body in sections if body]


def build_policy_chunks(benefits: Iterable[Dict[str, Any]]) -> List[RAGChunk]:
    chunks: List[RAGChunk] = []
    for policy in benefits:
        pid = str(policy.get("id") or policy.get("name") or "policy")
        title = str(policy.get("name") or pid)
        rule = policy.get("rule", {})
        text = "\n".join([
            f"정책명: {title}",
            f"영역: {policy.get('domain', '')}",
            f"대상: {policy.get('target', '')}",
            f"설명: {policy.get('description', '')}",
            f"월 환산효과: {policy.get('estimated_monthly_value', 0)}",
            f"필요서류: {', '.join(policy.get('required_docs', []) or [])}",
            f"신청URL: {policy.get('apply_url', '')}",
            f"판정룰: {json.dumps(rule, ensure_ascii=False)}",
        ])
        chunks.append(RAGChunk(
            chunk_id=f"benefit:{pid}",
            title=title,
            text=text,
            source=str((policy.get("provenance") or {}).get("source_system", "benefit_catalog")),
            source_type="benefit_rule",
            metadata={"benefit_id": pid, "domain": policy.get("domain", ""), "monthly_value": policy.get("estimated_monthly_value", 0)},
        ))

    for idx, item in enumerate(_safe_read_json(KB_PATH)):
        title = str(item.get("title", f"knowledge_{idx}"))
        text = str(item.get("text", ""))
        keywords = item.get("keywords", []) or []
        chunks.append(RAGChunk(
            chunk_id=f"kb:{idx}",
            title=title,
            text=f"{text}\n키워드: {', '.join(keywords)}",
            source=str(item.get("source", "local_knowledge_base")),
            source_type="knowledge_base",
            metadata={"keywords": keywords},
        ))

    if POLICY_DOCS_PATH.exists():
        for idx, (title, body) in enumerate(_split_markdown_docs(POLICY_DOCS_PATH.read_text(encoding="utf-8"))):
            chunks.append(RAGChunk(
                chunk_id=f"policy_docs:{idx}",
                title=title,
                text=body,
                source="data/policy_docs.md",
                source_type="policy_document",
                metadata={},
            ))
    return chunks


def semantic_search(query: str, benefits: Iterable[Dict[str, Any]], top_k: int = 6) -> Dict[str, Any]:
    chunks = build_policy_chunks(benefits)
    if not query.strip() or not chunks:
        return {"query": query, "hits": [], "embedding": embedding_rag_status(), "count": 0}
    texts = [query] + [f"{c.title}\n{c.text}" for c in chunks]
    vectors, meta = embed_texts(texts)
    qv, doc_vectors = vectors[0], vectors[1:]
    scored: List[RAGHit] = []
    for chunk, vec in zip(chunks, doc_vectors):
        score = _cosine(qv, vec)
        if score > 0:
            scored.append(RAGHit(
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                text=chunk.text[:1200],
                source=chunk.source,
                source_type=chunk.source_type,
                score=round(float(score), 5),
                metadata=chunk.metadata,
            ))
    scored.sort(key=lambda h: h.score, reverse=True)
    hits = [h.to_dict() for h in scored[: max(1, int(top_k))]]
    return {"query": query, "hits": hits, "embedding": meta, "count": len(hits)}


def build_rag_context(query: str, benefits: Iterable[Dict[str, Any]], profile: Any | None = None, top_k: int = 5) -> Dict[str, Any]:
    retrieval = semantic_search(query, benefits, top_k=top_k)
    profile_line = ""
    if profile is not None and hasattr(profile, "to_dict"):
        p = profile.to_dict()
        profile_line = f"사용자 조건: 나이 {p.get('age')}세, 지역 {p.get('region')}, 가구원 {p.get('household_size')}명, 월소득 {p.get('monthly_income')}원, 월세 {p.get('rent')}원."
    context_blocks = []
    if profile_line:
        context_blocks.append(profile_line)
    for idx, hit in enumerate(retrieval["hits"], start=1):
        context_blocks.append(
            f"[근거 {idx}] {hit['title']} / source={hit['source']} / score={hit['score']}\n{hit['text']}"
        )
    retrieval["context"] = "\n\n".join(context_blocks) if context_blocks else "해당 데이터 없음"
    return retrieval


def embedding_rag_status() -> Dict[str, Any]:
    provider = os.getenv("LIFEPASS_EMBEDDING_PROVIDER", "local_hash").strip().lower()
    configured = provider == "local_hash" or bool(os.getenv("OPENAI_API_KEY")) or provider in {"sentence_transformers", "sentence-transformers", "sbert"}
    return {
        "provider_requested": provider,
        "model_requested": os.getenv("LIFEPASS_EMBEDDING_MODEL", "local-hash-ko-384" if provider == "local_hash" else "text-embedding-3-small"),
        "configured": configured,
        "decision_boundary": "임베딩 검색은 근거 검색과 설명 보조에만 사용되며 최종 자격 판정은 rule_engine이 수행합니다.",
    }
