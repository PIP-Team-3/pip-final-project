from __future__ import annotations

from fastapi import APIRouter

from . import internal, papers, plans

api_router = APIRouter()
api_router.include_router(papers.router)
api_router.include_router(plans.router)
api_router.include_router(internal.router)

__all__ = ["api_router"]

