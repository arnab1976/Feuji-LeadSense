"""Embeddings with an offline fallback.

In ``echo`` mode a deterministic hashed bag-of-words vector is used. It is not a
semantic model, but it is stable and gives the retrieval code something real to
rank, so the RAG path is exercised end to end without an API key.
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from app.core.config import settings

DIM = 256


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in _tokens(text):
        idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        try:  # pragma: no cover - network path
            with httpx.Client(timeout=45) as client:
                resp = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": settings.embedding_model, "input": text},
                )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception:
            pass
    return _hash_embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
