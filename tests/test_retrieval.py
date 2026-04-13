from __future__ import annotations

from safeflow_agent.retrieval import HashEmbeddingFunction, KnowledgeBase


def test_hash_embedding_function_exposes_chroma_config() -> None:
    embedder = HashEmbeddingFunction(dims=32)

    assert embedder.name() == "hash_embedding"
    assert embedder.get_config() == {"dims": 32}

    rebuilt = HashEmbeddingFunction.build_from_config(embedder.get_config())
    vectors = rebuilt(["driver threatened me"])

    assert rebuilt.dims == 32
    assert len(vectors) == 1
    assert len(vectors[0]) == 32


def test_knowledge_base_initializes_chroma_collection(tmp_path) -> None:
    kb = KnowledgeBase(tmp_path / "chroma")

    results = kb.query("司机多收费，我要退款", case_type="fare_dispute")

    assert results
