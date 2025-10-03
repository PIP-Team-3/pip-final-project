from __future__ import annotations

from fastapi import APIRouter

from . import internal, papers, plans, runs

api_router = APIRouter()
api_router.include_router(papers.router)
api_router.include_router(plans.router)
api_router.include_router(plans.plan_assets_router)
api_router.include_router(runs.router)
api_router.include_router(runs.stream_router)
api_router.include_router(internal.router)

__all__ = ["api_router"]

