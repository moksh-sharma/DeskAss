"""Knowledge base (RAG) endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import container
from app.core.container import Container
from app.models.schemas import KnowledgeReference

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/search", response_model=list[KnowledgeReference], summary="Search the knowledge base")
async def search(
    q: str = Query(..., min_length=2),
    top_k: int = Query(4, ge=1, le=20),
    c: Container = Depends(container),
) -> list[KnowledgeReference]:
    return c.rag.retrieve(q, top_k=top_k)


@router.get("/count", summary="Number of indexed documents")
async def count(c: Container = Depends(container)) -> dict[str, int]:
    return {"count": c.rag.count()}


@router.post("/reseed", summary="Re-ingest knowledge base documents from disk")
async def reseed(c: Container = Depends(container)) -> dict[str, int]:
    return {"indexed": c.rag.reseed()}
