import re
from hashlib import sha256
from typing import Protocol

from sqlalchemy.orm import Session

from app.brand.repository import BrandRepository
from app.brand.service import BrandService
from app.catalog.repository import ProductRepository
from app.support.engine import IndexedKnowledgeChunk, SupportContext
from app.support.models import SupportKnowledge
from app.support.repository import SupportKnowledgeRepository
from app.support.schemas import SupportKnowledgeInput


class KnowledgeEmbeddingProvider(Protocol):
    embedding_model: str

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]: ...


INDEX_VERSION = "support-index-v3"
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!؟])\s+")
SENTENCE_ENDINGS = (".", "!", "?", "؟", ":", "؛")


def split_knowledge(content: str, *, max_chars: int = 900) -> list[str]:
    """Split editable business text into focused facts for accurate retrieval."""
    normalized = content.replace("\r\n", "\n")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _is_heading(line):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    chunks: list[str] = []
    for section in sections:
        if len(section) == 1 or not _is_heading(section[0]):
            units = [
                sentence.strip()
                for line in section
                for sentence in SENTENCE_BOUNDARY.split(line)
                if sentence.strip()
            ]
        else:
            units = _pack_section(section[0], section[1:], max_chars=max_chars)
        for unit in units:
            chunks.extend(
                unit[start : start + max_chars].strip()
                for start in range(0, len(unit), max_chars)
            )
    return [chunk for chunk in chunks if chunk]


def _is_heading(line: str) -> bool:
    return len(line) <= 80 and not line.endswith(SENTENCE_ENDINGS)


def _pack_section(heading: str, lines: list[str], *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = heading
    for line in lines:
        candidate = f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = f"{heading}\n{line}"
    chunks.append(current)
    return chunks


class SupportKnowledgeService:
    def __init__(self, repository: SupportKnowledgeRepository) -> None:
        self.repository = repository

    def get_or_create(self) -> SupportKnowledge:
        existing = self.repository.get()
        if existing is not None:
            return existing

        knowledge = SupportKnowledge(id=1, content="")
        try:
            self.repository.add(knowledge)
            self.repository.commit()
            self.repository.refresh(knowledge)
        except Exception:
            self.repository.rollback()
            raise
        return knowledge

    @staticmethod
    def indexed_chunks(knowledge: SupportKnowledge) -> tuple[IndexedKnowledgeChunk, ...]:
        chunks: list[IndexedKnowledgeChunk] = []
        for item in knowledge.index_chunks:
            if not isinstance(item, dict):
                continue
            source_ref = item.get("source_ref")
            text = item.get("text")
            embedding = item.get("embedding")
            if (
                not isinstance(source_ref, str)
                or not isinstance(text, str)
                or not isinstance(embedding, list)
            ):
                continue
            try:
                vector = tuple(float(value) for value in embedding)
            except (TypeError, ValueError):
                continue
            if vector:
                chunks.append(IndexedKnowledgeChunk(source_ref, text, vector))
        return tuple(chunks)

    def update(self, data: SupportKnowledgeInput) -> SupportKnowledge:
        knowledge = self.get_or_create()
        try:
            knowledge.content = data.content
            knowledge.index_chunks = []
            knowledge.indexed_content_hash = ""
            knowledge.embedding_model = ""
            self.repository.commit()
            self.repository.refresh(knowledge)
        except Exception:
            self.repository.rollback()
            raise
        return knowledge

    def ensure_index(
        self,
        knowledge: SupportKnowledge,
        provider: KnowledgeEmbeddingProvider,
    ) -> SupportKnowledge:
        content = knowledge.content.strip()
        content_hash = (
            sha256(f"{INDEX_VERSION}\0{content}".encode()).hexdigest()
            if content
            else ""
        )
        if (
            knowledge.index_chunks
            and knowledge.indexed_content_hash == content_hash
            and knowledge.embedding_model == provider.embedding_model
        ):
            return knowledge

        texts = split_knowledge(content)
        embeddings = provider.embed(texts) if texts else []
        if len(embeddings) != len(texts):
            raise ValueError("Embedding result count does not match knowledge chunks")

        try:
            knowledge.index_chunks = [
                {
                    "source_ref": f"knowledge:{index}",
                    "text": text,
                    "embedding": list(embedding),
                }
                for index, (text, embedding) in enumerate(
                    zip(texts, embeddings, strict=True), start=1
                )
            ]
            knowledge.indexed_content_hash = content_hash
            knowledge.embedding_model = provider.embedding_model if texts else ""
            self.repository.commit()
            self.repository.refresh(knowledge)
        except Exception:
            self.repository.rollback()
            raise
        return knowledge


def build_support_context(
    db: Session,
    knowledge: SupportKnowledge,
    service: SupportKnowledgeService,
) -> SupportContext:
    brand = BrandService(BrandRepository(db)).get_or_create()
    products = [product for product in ProductRepository(db).list() if product.active]
    return SupportContext(
        business_name=brand.business_name,
        knowledge_text=knowledge.content,
        tone_guidelines=brand.tone_guidelines,
        support_handle=brand.support_handle,
        support_phone=brand.support_phone,
        product_facts=tuple(_product_fact(product) for product in products),
        knowledge_chunks=service.indexed_chunks(knowledge),
    )


def _product_fact(product) -> str:
    attributes = "، ".join(f"{key}: {value}" for key, value in product.attributes.items())
    parts = [
        f"[product:{product.id}] نام: {product.name}",
        f"توضیحات: {product.description}" if product.description else "",
        f"وضعیت: {product.availability}" if product.availability else "",
        f"ارسال: {product.shipping_info}" if product.shipping_info else "",
        f"مشخصات: {attributes}" if attributes else "",
    ]
    return " | ".join(part for part in parts if part)
