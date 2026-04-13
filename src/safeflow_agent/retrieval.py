from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .models import RetrievedDoc
from .seeds import seeded_corpus

try:
    import chromadb
except ImportError:  # pragma: no cover
    chromadb = None


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class HashEmbeddingFunction:
    def __init__(self, dims: int = 64) -> None:
        self.dims = dims

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in input:
            vector = [0.0] * self.dims
            for token in tokenize(text):
                slot = hash(token) % self.dims
                vector[slot] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self.__call__(input)

    @staticmethod
    def name() -> str:
        return "hash_embedding"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashEmbeddingFunction":
        dims = int(config.get("dims", 64))
        return HashEmbeddingFunction(dims=dims)

    def get_config(self) -> dict[str, Any]:
        return {"dims": self.dims}

    def default_space(self) -> str:
        return "l2"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def is_legacy(self) -> bool:
        return False


class KnowledgeBase:
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = persist_dir
        self.documents = seeded_corpus()
        self.embedder = HashEmbeddingFunction()
        self._client = None
        self._collection = None
        if chromadb is not None:
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name="safeflow_knowledge",
                embedding_function=self.embedder,
            )
            self._ensure_index()

    def _ensure_index(self) -> None:
        if self._collection is None:
            return
        self._collection.upsert(
            ids=[doc["id"] for doc in self.documents],
            documents=[doc["content"] for doc in self.documents],
            metadatas=[{"title": doc["title"], "doc_type": doc["doc_type"]} for doc in self.documents],
        )

    def query(self, query_text: str, case_type: str | None = None, top_k: int = 4) -> list[RetrievedDoc]:
        if self._collection is not None:
            return self._query_chroma(query_text, case_type, top_k)
        return self._query_memory(query_text, case_type, top_k)

    def _query_chroma(self, query_text: str, case_type: str | None, top_k: int) -> list[RetrievedDoc]:
        assert self._collection is not None
        result = self._collection.query(query_texts=[query_text], n_results=top_k * 2)
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        scored: list[tuple[float, RetrievedDoc]] = []
        for doc_id, content, meta, distance in zip(ids, docs, metas, distances):
            score = 1.0 / (1.0 + float(distance))
            score += self._boost_score(meta or {}, content, case_type)
            scored.append(
                (
                    score,
                    RetrievedDoc(
                        doc_id=doc_id,
                        title=str((meta or {}).get("title", doc_id)),
                        doc_type=str((meta or {}).get("doc_type", "unknown")),
                        score=round(score, 4),
                        snippet=self._snippet(content),
                        retrieval_query=query_text,
                        match_reason=self._match_reason(meta or {}, content, case_type, query_text),
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def _query_memory(self, query_text: str, case_type: str | None, top_k: int) -> list[RetrievedDoc]:
        query_tokens = set(tokenize(query_text))
        scored: list[tuple[float, dict[str, str]]] = []
        for doc in self.documents:
            doc_tokens = set(tokenize(f"{doc['title']} {doc['content']}"))
            overlap = len(query_tokens & doc_tokens)
            score = overlap / max(len(query_tokens) or 1, 1)
            score += self._boost_score(doc, doc["content"], case_type)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedDoc(
                doc_id=doc["id"],
                title=doc["title"],
                doc_type=doc["doc_type"],
                score=round(score, 4),
                snippet=self._snippet(doc["content"]),
                retrieval_query=query_text,
                match_reason=self._match_reason(doc, doc["content"], case_type, query_text),
            )
            for score, doc in scored[:top_k]
        ]

    def _boost_score(self, meta: dict[str, Any], content: str, case_type: str | None) -> float:
        score = 0.0
        doc_type = str(meta.get("doc_type", "")).lower()
        payload = f"{meta.get('title', '')} {content} {doc_type}".lower()
        if case_type and case_type.lower() in payload:
            score += 0.35
        if doc_type == "policy":
            score += 0.1
        if "human review" in payload or "人工" in payload:
            score += 0.05
        return score

    def _match_reason(self, meta: dict[str, Any], content: str, case_type: str | None, query_text: str) -> str:
        reasons: list[str] = []
        doc_type = str(meta.get("doc_type", "unknown")).lower()
        payload = f"{meta.get('title', '')} {content} {doc_type}".lower()
        query_tokens = set(tokenize(query_text))
        overlap = len(query_tokens & set(tokenize(payload)))
        if case_type and case_type.lower() in payload:
            reasons.append("文档主题与案件类型一致")
        if doc_type == "policy":
            reasons.append("优先返回策略文档以增强 grounding")
        if "human review" in payload or "人工" in payload:
            reasons.append("文档包含人工审核相关约束")
        if overlap:
            reasons.append(f"与检索查询存在 {overlap} 个词项重叠")
        return "；".join(reasons) if reasons else "基础语义相似度命中"

    @staticmethod
    def _snippet(content: str, limit: int = 180) -> str:
        return content[:limit] + ("..." if len(content) > limit else "")
