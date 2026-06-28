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
    resolved_name: Optional[str]       # supplement_map에서 찾은 canonical 이름
    matched_alias: Optional[str]       # 실제로 매칭된 alias
    match_type: Optional[str]          # exact_canonical / exact_raw / exact_alias / partial / not_found
    interactions: list[InteractionResult]
    total: int
