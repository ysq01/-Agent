from collections.abc import Generator
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.main import app
from app.services import policy_knowledge
from app.services.policy_knowledge import (
    KnowledgeIngestionResult,
    LocalTextEmbedder,
    ingest_knowledge_base,
    make_qdrant_client,
    search_policy,
)


TEST_QDRANT_URL = "http://localhost:6333"
TEST_COLLECTION = "kefu_policy_chunks_pytest"
PolicyKnowledgeFixture = tuple[QdrantClient, KnowledgeIngestionResult]


@pytest.fixture(scope="module")
def qdrant_test_collection() -> Generator[PolicyKnowledgeFixture, None, None]:
    previous_env = {
        "QDRANT_URL": os.environ.get("QDRANT_URL"),
        "QDRANT_COLLECTION": os.environ.get("QDRANT_COLLECTION"),
        "KEFU_EMBEDDING_BACKEND": os.environ.get("KEFU_EMBEDDING_BACKEND"),
    }
    os.environ["QDRANT_URL"] = TEST_QDRANT_URL
    os.environ["QDRANT_COLLECTION"] = TEST_COLLECTION
    os.environ["KEFU_EMBEDDING_BACKEND"] = "hashing"

    client = QdrantClient(url=TEST_QDRANT_URL, timeout=10)
    if client.collection_exists(TEST_COLLECTION):
        client.delete_collection(TEST_COLLECTION)

    first_result = ingest_knowledge_base(collection_name=TEST_COLLECTION)

    try:
        yield client, first_result
    finally:
        if client.collection_exists(TEST_COLLECTION):
            client.delete_collection(TEST_COLLECTION)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_ingest_knowledge_base_imports_documents_idempotently(
    qdrant_test_collection: PolicyKnowledgeFixture,
) -> None:
    client, first_result = qdrant_test_collection

    assert first_result.collection_name == TEST_COLLECTION
    assert first_result.document_count >= 7
    assert first_result.chunk_count >= 7
    assert first_result.point_count == first_result.chunk_count

    first_collection = client.get_collection(TEST_COLLECTION)
    assert first_collection.points_count == first_result.chunk_count

    second_result = ingest_knowledge_base(collection_name=TEST_COLLECTION)
    second_collection = client.get_collection(TEST_COLLECTION)

    assert second_result.chunk_count == first_result.chunk_count
    assert second_collection.points_count == first_collection.points_count


def test_search_policy_matches_seven_day_return_rule(
    qdrant_test_collection: PolicyKnowledgeFixture,
) -> None:
    _client, _first_result = qdrant_test_collection

    matches = search_policy(
        query="七天内不想要了可以退吗",
        top_k=3,
        collection_name=TEST_COLLECTION,
    )

    assert any(match.policy_title == "七天无理由退货规则" for match in matches)


def test_search_policy_matches_logistics_delay_compensation_rule(
    qdrant_test_collection: PolicyKnowledgeFixture,
) -> None:
    _client, _first_result = qdrant_test_collection

    matches = search_policy(
        query="物流延迟有没有赔偿",
        top_k=3,
        collection_name=TEST_COLLECTION,
    )

    assert any(match.policy_title == "物流延迟赔付规则" for match in matches)


def test_search_policy_uses_title_keyword_fallback_when_vector_results_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def collection_exists(self, collection_name: str) -> bool:
            return collection_name == "fake_collection"

    monkeypatch.setattr(policy_knowledge, "make_qdrant_client", lambda: FakeClient())
    monkeypatch.setattr(
        policy_knowledge.LocalTextEmbedder,
        "embed",
        lambda self, texts: [[1.0, 0.0] for _ in texts],
    )
    monkeypatch.setattr(
        policy_knowledge,
        "_query_points",
        lambda client, collection_name, vector, top_k: [
            SimpleNamespace(
                payload={
                    "policy_title": "七天无理由退货规则",
                    "text": "七天无理由 matched text",
                    "source_file": "seven_day_return.md",
                },
                score=0.42,
            )
        ],
    )

    matches = search_policy(
        query="shipping delivery 物流延迟",
        top_k=3,
        collection_name="fake_collection",
    )

    assert matches[0].policy_title == "物流延迟赔付规则"
    assert matches[0].source_file == "logistics_delay_compensation.md"
    assert any(match.policy_title == "七天无理由退货规则" for match in matches)


def test_keyword_fallback_prioritizes_user_query_terms_when_collection_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def collection_exists(self, collection_name: str) -> bool:
            del collection_name
            return False

    monkeypatch.setattr(policy_knowledge, "make_qdrant_client", lambda: FakeClient())

    matches = search_policy(
        query="售后政策里特殊商品有什么限制 售后政策 七天无理由 特殊商品 会员售后 退款到账",
        top_k=3,
        collection_name="missing_collection",
    )

    assert any(match.policy_title == "特殊商品退货规则" for match in matches)


def test_policy_search_api_returns_required_result_fields(
    qdrant_test_collection: PolicyKnowledgeFixture,
) -> None:
    _client, _first_result = qdrant_test_collection
    client = TestClient(app)

    response = client.post(
        "/api/tools/policies/search",
        json={"query": "物流延迟有没有赔偿", "top_k": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "search_policy"
    assert data["query"] == "物流延迟有没有赔偿"
    assert len(data["results"]) >= 1

    result = data["results"][0]
    assert set(result) == {"policy_title", "matched_text", "score", "source_file"}
    assert isinstance(result["policy_title"], str)
    assert isinstance(result["matched_text"], str)
    assert isinstance(result["score"], float)
    assert isinstance(result["source_file"], str)


def test_local_text_embedder_reuses_fastembed_model_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_calls: list[str] = []

    class FakeTextEmbedding:
        def __init__(self, model_name: str) -> None:
            init_calls.append(model_name)

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        SimpleNamespace(TextEmbedding=FakeTextEmbedding),
    )

    first_embedder = LocalTextEmbedder(model_name="fake-model", backend="fastembed")
    second_embedder = LocalTextEmbedder(model_name="fake-model", backend="fastembed")

    assert first_embedder.embed(["first"]) == [[1.0, 0.0]]
    assert second_embedder.embed(["second"]) == [[1.0, 0.0]]
    assert init_calls == ["fake-model"]


def test_make_qdrant_client_reuses_client_for_same_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDRANT_URL", TEST_QDRANT_URL)

    first_client = make_qdrant_client()
    second_client = make_qdrant_client()

    try:
        assert first_client is second_client
    finally:
        policy_knowledge._get_qdrant_client.cache_clear()
