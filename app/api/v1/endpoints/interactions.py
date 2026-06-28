from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.db.connection import get_conn
from app.schemas.interaction import InteractionResponse, InteractionResult
from app.services.supplement_resolver import resolve_supplement

router = APIRouter()


@router.get("/interactions", response_model=InteractionResponse)
def get_interactions(supplement: str):
    """
    건기식 성분명(또는 개별인정원료명/브랜드명)으로 약물 상호작용 조회.

    supplement: 성분명. 개별인정원료 브랜드명(예: TWK10, 오미자추출물)도 입력 가능.
    alias 테이블을 통해 canonical 성분으로 해석한 뒤 상호작용 정보를 반환.
    """
    resolved = resolve_supplement(supplement)

    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        if resolved:
            cursor.execute(
                """
                SELECT claim_id, supplement_canonical_ko, drug_canonical_ko,
                       drug_canonical_en, interaction_text_raw,
                       source_review_status, overall_review_status
                FROM standardized_interactions
                WHERE supplement_id = %s
                """,
                (resolved.supplement_id,),
            )
        else:
            # resolve 실패 시 기존 LIKE 방식으로 fallback
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
            resolved_name=resolved.canonical_name_ko if resolved else None,
            matched_alias=resolved.matched_alias if resolved else None,
            match_type=resolved.match_type if resolved else "not_found",
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
