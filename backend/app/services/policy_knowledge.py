from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client import models


DEFAULT_COLLECTION_NAME = "kefu_policy_chunks"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_QDRANT_URL = "http://localhost:6333"
HASHING_VECTOR_SIZE = 384
SUPPORTED_EXTENSIONS = {".md", ".txt"}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"

POLICY_FALLBACK_ALIASES: dict[str, tuple[str, ...]] = {
    "complaint_escalation.md": (
        "投诉",
        "投诉升级",
        "转人工",
        "人工客服",
        "complaint",
        "escalate",
    ),
    "invoice_rules.md": (
        "发票",
        "开票",
        "发票开具",
        "电子发票",
        "企业抬头",
        "invoice",
    ),
    "logistics_delay_compensation.md": (
        "物流",
        "物流延迟",
        "物流赔付",
        "快递",
        "运单",
        "没收到",
        "shipping",
        "delivery",
        "delayed",
        "logistics",
        "not received",
    ),
    "member_after_sales_rights.md": (
        "会员",
        "会员售后",
        "会员售后权益",
        "售后权益",
        "账号",
        "账户",
        "登录",
        "密码",
        "account",
        "login",
        "password",
    ),
    "refund_arrival_time.md": (
        "退款到账",
        "到账时间",
        "退款时间",
        "款项到账",
        "refund arrival",
    ),
    "seven_day_return.md": (
        "七天无理由",
        "七天",
        "退货",
        "不想要",
        "return",
    ),
    "special_goods_return.md": (
        "特殊商品",
        "生鲜",
        "贴身衣物",
        "定制商品",
        "虚拟商品",
        "特殊商品退货",
    ),
}


@dataclass(frozen=True)
class KnowledgeDocument:
    policy_title: str
    text: str
    source_file: str
    status: str = "published"
    source: str = "file_seed"
    policy_id: int | None = None
    version: int = 1
    content_hash: str | None = None


@dataclass(frozen=True)
class PolicyChunk:
    policy_title: str
    text: str
    source_file: str
    chunk_index: int
    status: str = "published"
    source: str = "file_seed"
    policy_id: int | None = None
    version: int = 1
    content_hash: str | None = None


@dataclass(frozen=True)
class PolicySearchMatch:
    policy_title: str
    matched_text: str
    score: float
    source_file: str


@dataclass(frozen=True)
class KnowledgeIngestionResult:
    collection_name: str
    document_count: int
    chunk_count: int
    point_count: int


class LocalTextEmbedder:
    def __init__(
        self,
        model_name: str | None = None,
        backend: str | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "KEFU_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self.backend = (backend or os.getenv("KEFU_EMBEDDING_BACKEND", "fastembed")).lower()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.backend != "hashing":
            try:
                return self._embed_with_fastembed(texts)
            except Exception:
                # Local development and CI should still work if the fastembed
                # model has not been downloaded yet.
                return self._embed_with_hashing(texts)

        return self._embed_with_hashing(texts)

    def _embed_with_fastembed(self, texts: list[str]) -> list[list[float]]:
        model = _get_fastembed_model(self.model_name)
        return [
            [float(value) for value in vector]
            for vector in model.embed(texts)
        ]

    def _embed_with_hashing(self, texts: list[str]) -> list[list[float]]:
        return [_hashing_embedding(text) for text in texts]


def get_qdrant_url() -> str:
    return os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL)


def get_collection_name(collection_name: str | None = None) -> str:
    return collection_name or os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION_NAME)


def make_qdrant_client() -> QdrantClient:
    return _get_qdrant_client(get_qdrant_url())


@lru_cache(maxsize=4)
def _get_qdrant_client(qdrant_url: str) -> QdrantClient:
    return QdrantClient(url=qdrant_url, timeout=30)


@lru_cache(maxsize=4)
def _get_fastembed_model(model_name: str) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name)


def load_knowledge_documents(
    knowledge_dir: Path | None = None,
    session: Session | None = None,
) -> list[KnowledgeDocument]:
    documents = _load_file_knowledge_documents(knowledge_dir)
    if session is not None:
        documents.extend(_load_published_admin_documents(session))
    return documents


def _load_file_knowledge_documents(
    knowledge_dir: Path | None = None,
) -> list[KnowledgeDocument]:
    root = knowledge_dir or DEFAULT_KNOWLEDGE_DIR
    if not root.exists():
        return []

    documents: list[KnowledgeDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue

        source_file = path.relative_to(root).as_posix()
        documents.append(
            KnowledgeDocument(
                policy_title=extract_policy_title(text, path.stem),
                text=_normalize_text(text),
                source_file=source_file,
                status="published",
                source="file_seed",
                policy_id=None,
                version=1,
                content_hash=_content_hash(text),
            )
        )

    return documents


def _load_published_admin_documents(session: Session) -> list[KnowledgeDocument]:
    from app.models import PolicyDocument

    bind = session.get_bind()
    if bind is not None and not sqlalchemy_inspect(bind).has_table(
        PolicyDocument.__tablename__
    ):
        return []

    try:
        policies = list(
            session.scalars(
                select(PolicyDocument)
                .where(PolicyDocument.status == "published")
                .order_by(PolicyDocument.id)
            )
        )
    except ProgrammingError:
        session.rollback()
        return []
    documents: list[KnowledgeDocument] = []
    for policy in policies:
        normalized_content = _normalize_text(policy.content)
        if not normalized_content:
            continue
        documents.append(
            KnowledgeDocument(
                policy_title=policy.title,
                text=normalized_content,
                source_file=_admin_policy_source_file(policy.id, policy.version),
                status="published",
                source=policy.source,
                policy_id=policy.id,
                version=policy.version,
                content_hash=policy.content_hash or _content_hash(policy.content),
            )
        )
    return documents


def extract_policy_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        return stripped
    return fallback


def split_document_text(
    text: str,
    max_chars: int = 700,
    overlap_chars: int = 120,
) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    step = max(1, max_chars - overlap_chars)
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(normalized):
            break
        start += step

    return chunks


def ingest_knowledge_base(
    knowledge_dir: Path | None = None,
    collection_name: str | None = None,
    session: Session | None = None,
) -> KnowledgeIngestionResult:
    collection = get_collection_name(collection_name)
    documents = load_knowledge_documents(knowledge_dir, session=session)
    chunks = _build_chunks(documents)
    embedder = LocalTextEmbedder()
    vectors = embedder.embed([chunk.text for chunk in chunks])
    vector_size = len(vectors[0]) if vectors else HASHING_VECTOR_SIZE

    client = make_qdrant_client()
    _ensure_collection(client, collection, vector_size)

    for source_file in {document.source_file for document in documents}:
        _delete_source_file_points(client, collection, source_file)

    if chunks:
        points = [
            models.PointStruct(
                id=_point_id(chunk),
                vector=vector,
                payload={
                    "policy_title": chunk.policy_title,
                    "text": chunk.text,
                    "source_file": chunk.source_file,
                    "chunk_index": chunk.chunk_index,
                    "status": chunk.status,
                    "source": chunk.source,
                    "policy_id": chunk.policy_id,
                    "version": chunk.version,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        client.upsert(collection_name=collection, points=points, wait=True)

    return KnowledgeIngestionResult(
        collection_name=collection,
        document_count=len(documents),
        chunk_count=len(chunks),
        point_count=_count_points(client, collection),
    )


def rebuild_knowledge_base(
    session: Any | None = None,
    collection_name: str | None = None,
) -> KnowledgeIngestionResult:
    collection = get_collection_name(collection_name)
    client = make_qdrant_client()
    if client.collection_exists(collection):
        client.delete_collection(collection)
    return ingest_knowledge_base(collection_name=collection, session=session)


def search_policy(
    query: str,
    top_k: int = 3,
    collection_name: str | None = None,
    session: Session | None = None,
) -> list[PolicySearchMatch]:
    collection = get_collection_name(collection_name)
    query = query.strip()
    if not query or top_k <= 0:
        return []

    client = make_qdrant_client()
    if not client.collection_exists(collection):
        return _keyword_fallback_matches(query, [], top_k, session=session)

    vector = LocalTextEmbedder().embed([query])[0]
    points = _query_points(client, collection, vector, top_k)
    matches: list[PolicySearchMatch] = []

    for point in points:
        payload = point.payload or {}
        status = payload.get("status")
        if status is not None and status != "published":
            continue
        matches.append(
            PolicySearchMatch(
                policy_title=str(payload.get("policy_title", "")),
                matched_text=str(payload.get("text", "")),
                score=float(point.score),
                source_file=str(payload.get("source_file", "")),
            )
        )

    return _merge_keyword_fallback_matches(query, matches, top_k, session=session)


def _build_chunks(documents: list[KnowledgeDocument]) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for document in documents:
        for index, text in enumerate(split_document_text(document.text)):
            chunks.append(
                PolicyChunk(
                    policy_title=document.policy_title,
                    text=text,
                    source_file=document.source_file,
                    chunk_index=index,
                    status=document.status,
                    source=document.source,
                    policy_id=document.policy_id,
                    version=document.version,
                    content_hash=document.content_hash,
                )
            )
    return chunks


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _merge_keyword_fallback_matches(
    query: str,
    vector_matches: list[PolicySearchMatch],
    top_k: int,
    session: Session | None = None,
) -> list[PolicySearchMatch]:
    fallback_matches = _keyword_fallback_matches(
        query,
        vector_matches,
        top_k,
        session=session,
    )
    if not fallback_matches:
        return vector_matches[:top_k]
    return (fallback_matches + vector_matches)[:top_k]


def _keyword_fallback_matches(
    query: str,
    existing_matches: Sequence[PolicySearchMatch],
    top_k: int,
    session: Session | None = None,
) -> list[PolicySearchMatch]:
    normalized_query = query.lower()
    existing_sources = {match.source_file for match in existing_matches}
    candidates: list[tuple[int, int, int, KnowledgeDocument]] = []

    for order, document in enumerate(load_knowledge_documents(session=session)):
        if document.source_file in existing_sources:
            continue
        score = _policy_alias_match_score(document, normalized_query)
        if score is None:
            continue
        earliest_index, matched_length = score
        candidates.append((earliest_index, -matched_length, order, document))

    matches: list[PolicySearchMatch] = []
    for _index, _length, _order, document in sorted(candidates)[:top_k]:
        matches.append(
            PolicySearchMatch(
                policy_title=document.policy_title,
                matched_text=_fallback_preview(document.text),
                score=0.99,
                source_file=document.source_file,
            )
        )

    return matches


def _policy_aliases(document: KnowledgeDocument) -> tuple[str, ...]:
    source_stem = Path(document.source_file).stem.replace("_", " ")
    return (
        document.policy_title,
        document.source_file,
        source_stem,
        *POLICY_FALLBACK_ALIASES.get(document.source_file, ()),
    )


def _policy_alias_match_score(
    document: KnowledgeDocument,
    normalized_query: str,
) -> tuple[int, int] | None:
    best_index: int | None = None
    best_length = 0
    for alias in _policy_aliases(document):
        normalized_alias = alias.lower()
        if not normalized_alias:
            continue
        index = normalized_query.find(normalized_alias)
        if index < 0:
            continue
        if best_index is None or index < best_index:
            best_index = index
            best_length = len(normalized_alias)
        elif index == best_index and len(normalized_alias) > best_length:
            best_length = len(normalized_alias)

    if best_index is None:
        return None
    return best_index, best_length


def _fallback_preview(text: str, max_chars: int = 220) -> str:
    normalized = _normalize_text(text)
    return normalized[:max_chars]


def _content_hash(content: str) -> str:
    return hashlib.sha256(_normalize_text(content).encode("utf-8")).hexdigest()


def _admin_policy_source_file(policy_id: int, version: int) -> str:
    return f"admin-policy-{policy_id}-v{version}"


def _hashing_embedding(text: str) -> list[float]:
    vector = [0.0] * HASHING_VECTOR_SIZE
    tokens = _tokenize_for_hashing(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % HASHING_VECTOR_SIZE
        vector[index] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


def _tokenize_for_hashing(text: str) -> list[str]:
    lowered = text.lower()
    base_tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", lowered)
    compact_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    bigrams = [
        compact_cjk[index : index + 2]
        for index in range(max(0, len(compact_cjk) - 1))
    ]
    return base_tokens + bigrams


def _ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
) -> None:
    if client.collection_exists(collection_name):
        current_size = _collection_vector_size(client.get_collection(collection_name))
        if current_size == vector_size:
            return
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )


def _collection_vector_size(collection_info: Any) -> int | None:
    vectors = collection_info.config.params.vectors
    if isinstance(vectors, dict):
        first_vector = next(iter(vectors.values()), None)
        return getattr(first_vector, "size", None)
    return getattr(vectors, "size", None)


def _delete_source_file_points(
    client: QdrantClient,
    collection_name: str,
    source_file: str,
) -> None:
    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_file",
                        match=models.MatchValue(value=source_file),
                    )
                ]
            )
        ),
        wait=True,
    )


def _point_id(chunk: PolicyChunk) -> str:
    value = f"{chunk.source_file}:{chunk.chunk_index}:{chunk.text}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def _count_points(client: QdrantClient, collection_name: str) -> int:
    return int(client.count(collection_name=collection_name, exact=True).count)


def _query_points(
    client: QdrantClient,
    collection_name: str,
    vector: list[float],
    top_k: int,
) -> list[Any]:
    published_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="status",
                match=models.MatchValue(value="published"),
            )
        ]
    )
    if hasattr(client, "query_points"):
        try:
            result = client.query_points(
                collection_name=collection_name,
                query=vector,
                query_filter=published_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except TypeError:
            result = client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        return list(result.points)

    try:
        return list(
            client.search(
                collection_name=collection_name,
                query_vector=vector,
                query_filter=published_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        )
    except TypeError:
        return list(
            client.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        )
