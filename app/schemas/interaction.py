from __future__ import annotations

from typing import Literal, Optional
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
    resolved_name: Optional[str]
    matched_alias: Optional[str]
    match_type: Optional[str]
    interactions: list[InteractionResult]
    total: int


# --- /analyze 엔드포인트용 ---

RiskLevel = Literal["danger", "caution", "safe"]

LEVEL_RANK: dict[RiskLevel, int] = {"danger": 3, "caution": 2, "safe": 1}


class AnalyzeItem(BaseModel):
    name: str
    category: str  # "알약" | "건강기능식품 라벨"


class InteractionPair(BaseModel):
    id: str
    items: list[str]       # [성분명, 약물명]
    level: RiskLevel
    description: str


class AnalyzeResponse(BaseModel):
    overall: RiskLevel
    summary: str
    pairs: list[InteractionPair]


class AnalyzeRequest(BaseModel):
    items: list[AnalyzeItem]
