"""Local RAG knowledge base backed by ChromaDB + Sentence Transformers.

Embeddings and the Chroma client are loaded lazily (they are heavy) so the API
starts quickly. The knowledge base is auto-seeded from ``app/knowledge_base``
on first use if the collection is empty.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Optional

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.schemas import KnowledgeReference

logger = get_logger(__name__)

KB_DIR = Path(__file__).resolve().parents[1] / "knowledge_base"


class RagService:
    """Retrieval-augmented generation knowledge base."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._client = None
        self._collection = None
        self._embedder = None
        self._initialised = False

    # ------------------------------------------------------------------ #
    #  Lazy initialisation
    # ------------------------------------------------------------------ #
    def _ensure_ready(self) -> bool:
        if self._initialised:
            return self._collection is not None
        with self._lock:
            if self._initialised:
                return self._collection is not None
            try:
                self._init_backend()
                self._initialised = True
            except Exception as exc:  # pragma: no cover - heavy deps
                logger.error("RAG backend initialisation failed: %s", exc)
                self._initialised = True
                self._collection = None
        return self._collection is not None

    def _init_backend(self) -> None:
        # Must be set before chromadb imports its telemetry module.
        import os
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

        import chromadb
        from chromadb.config import Settings as ChromaSettings
        from sentence_transformers import SentenceTransformer

        chroma_path = self._settings.chroma_path
        chroma_path.mkdir(parents=True, exist_ok=True)

        logger.info("Loading embedding model '%s'…", self._settings.embedding_model)
        self._embedder = SentenceTransformer(self._settings.embedding_model)

        self._client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._settings.kb_collection,
            metadata={"hnsw:space": "cosine"},
        )
        if self._collection.count() == 0:
            logger.info("Knowledge base empty - seeding from %s", KB_DIR)
            self._seed_from_disk()

    # ------------------------------------------------------------------ #
    #  Embedding helper
    # ------------------------------------------------------------------ #
    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._embedder.encode(texts, normalize_embeddings=True)  # type: ignore[union-attr]
        return [v.tolist() for v in vectors]

    # ------------------------------------------------------------------ #
    #  Ingestion
    # ------------------------------------------------------------------ #
    def _seed_from_disk(self) -> int:
        if not KB_DIR.exists():
            logger.warning("Knowledge base directory not found: %s", KB_DIR)
            return 0
        docs: list[tuple[str, str, str, str]] = []  # (id, title, category, content)
        for md_file in sorted(KB_DIR.rglob("*.md")):
            category = md_file.parent.name if md_file.parent != KB_DIR else "general"
            content = md_file.read_text(encoding="utf-8")
            title = self._title_from_markdown(content, md_file.stem)
            doc_id = hashlib.sha1(str(md_file.relative_to(KB_DIR)).encode()).hexdigest()[:16]
            docs.append((doc_id, title, category, content))
        if docs:
            self._upsert(docs)
        logger.info("Seeded %d knowledge base documents", len(docs))
        return len(docs)

    def _upsert(self, docs: list[tuple[str, str, str, str]]) -> None:
        ids = [d[0] for d in docs]
        contents = [d[3] for d in docs]
        metadatas = [{"title": d[1], "category": d[2]} for d in docs]
        embeddings = self._embed(contents)
        self._collection.upsert(  # type: ignore[union-attr]
            ids=ids, documents=contents, metadatas=metadatas, embeddings=embeddings
        )

    def reseed(self) -> int:
        """Force re-ingestion of the on-disk knowledge base."""
        if not self._ensure_ready() or self._collection is None:
            return 0
        with self._lock:
            try:
                self._client.delete_collection(self._settings.kb_collection)  # type: ignore[union-attr]
            except Exception:
                pass
            self._collection = self._client.get_or_create_collection(  # type: ignore[union-attr]
                name=self._settings.kb_collection,
                metadata={"hnsw:space": "cosine"},
            )
            return self._seed_from_disk()

    # ------------------------------------------------------------------ #
    #  Retrieval
    # ------------------------------------------------------------------ #
    def retrieve(self, query: str, top_k: Optional[int] = None) -> list[KnowledgeReference]:
        if not self._ensure_ready() or self._collection is None:
            logger.warning("RAG retrieve called but knowledge base is unavailable.")
            return []
        k = top_k or self._settings.rag_top_k
        try:
            embedding = self._embed([query])[0]
            result = self._collection.query(
                query_embeddings=[embedding],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # pragma: no cover
            logger.error("RAG query failed: %s", exc)
            return []

        refs: list[KnowledgeReference] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
            score = max(0.0, 1.0 - float(dist))  # cosine distance -> similarity
            refs.append(
                KnowledgeReference(
                    doc_id=doc_id,
                    title=(meta or {}).get("title", "Untitled"),
                    category=(meta or {}).get("category", "general"),
                    snippet=self._snippet(doc),
                    score=round(score, 3),
                )
            )
        return refs

    def count(self) -> int:
        if not self._ensure_ready() or self._collection is None:
            return 0
        return self._collection.count()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _snippet(text: str, max_len: int = 400) -> str:
        cleaned = " ".join(text.replace("#", "").split())
        return cleaned[:max_len] + ("…" if len(cleaned) > max_len else "")

    @staticmethod
    def _title_from_markdown(content: str, fallback: str) -> str:
        for line in content.splitlines():
            if line.startswith("#"):
                return line.lstrip("# ").strip()
        return fallback.replace("_", " ").title()
