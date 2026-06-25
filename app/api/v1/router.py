from __future__ import annotations

from fastapi import APIRouter
from app.api.v1.endpoints import interactions

router = APIRouter(prefix="/api/v1")
router.include_router(interactions.router, tags=["interactions"])
