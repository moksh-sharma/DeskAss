"""CLI utility to (re)ingest the knowledge base into ChromaDB.

Usage:
    python -m app.scripts.seed_kb
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.rag_service import RagService

logger = get_logger(__name__)


def main() -> None:
    rag = RagService(get_settings())
    count = rag.reseed()
    logger.info("Knowledge base ingestion complete: %d documents indexed.", count)
    print(f"Indexed {count} knowledge base documents.")


if __name__ == "__main__":
    main()
