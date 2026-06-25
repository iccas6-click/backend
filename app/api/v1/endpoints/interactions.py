from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.db.connection import get_conn
from app.schemas.interaction import InteractionResponse, InteractionResult

router = APIRouter()


@router.get("/interactions", response_model=InteractionResponse)
def get_interactions(supplement: str):
    """
    건기식 이름으로 약물 상호작용 조회.
    supplement: 건기식 성분명 (예: 비타민C, 오메가3)
    """
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT claim_id, supplement_canonical_ko, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw,
                   source_review_status, overall_review_status
            FROM standardized_interactions
            WHERE supplement_canonical_ko LIKE %s
               OR supplement_canonical_en LIKE %s
            """,
            (f"%{supplement}%", f"%{supplement}%"),
        )
        rows = cursor.fetchall()

        return InteractionResponse(
            supplement_name=supplement,
            interactions=[InteractionResult(**row) for row in rows],
            total=len(rows),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
