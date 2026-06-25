from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class InteractionResult(BaseModel):
    claim_id: str
    supplement_canonical_ko: Optional[str]
    drug_canonical_ko: Optional[str]
    drug_canonical_en: Optional[str]
    interaction_text_raw: Optional[str]
    source_review_status: Optional[str]
    overall_review_status: Optional[str]


class InteractionResponse(BaseModel):
    supplement_name: str
    interactions: list[InteractionResult]
    total: int
