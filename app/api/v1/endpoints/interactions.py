from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.db.connection import get_conn
from app.i18n import get_summary, parse_lang
from app.schemas.interaction import (
    AnalyzeRequest,
    AnalyzeResponse,
    InteractionPair,
    InteractionResponse,
    InteractionResult,
    LEVEL_RANK,
    RiskLevel,
)
from app.services.supplement_resolver import resolve_supplement
from app.services.translator import translate

router = APIRouter()

_INTERACTION_SELECT = """
    SELECT
        si.interaction_id,
        se.supplement_name_ko,
        cde.canonical_drug_name_ko  AS drug_canonical_ko,
        cde.canonical_drug_name_en  AS drug_canonical_en,
        sc.claim_text_original
    FROM standardized_interactions si
    JOIN supplement_entities    se  ON si.supplement_id     = se.supplement_id
    JOIN canonical_drug_entities cde ON si.canonical_drug_id = cde.canonical_drug_id
    JOIN source_claims           sc  ON si.source_claim_id  = sc.source_claim_id
"""


@router.get("/interactions", response_model=InteractionResponse)
def get_interactions(supplement: str):
    """
    건기식 성분명으로 약물 상호작용 조회.

    supplement_entities에서 성분을 해석한 뒤 standardized_interactions를 반환.
    """
    resolved = resolve_supplement(supplement)

    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        if resolved:
            cursor.execute(
                _INTERACTION_SELECT + "WHERE si.supplement_id = %s",
                (resolved.supplement_id,),
            )
        else:
            cursor.execute(
                _INTERACTION_SELECT +
                "WHERE se.supplement_name_ko LIKE %s OR se.supplement_name_en LIKE %s",
                (f"%{supplement}%", f"%{supplement}%"),
            )

        rows = cursor.fetchall()

        return InteractionResponse(
            supplement_name=supplement,
            resolved_name=resolved.supplement_name_ko if resolved else None,
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


def _infer_level(text: str | None) -> RiskLevel:
    """claim_text_original 키워드로 위험도 추론."""
    if not text:
        return "safe"
    danger_kw = ["금기", "심각", "위험", "사망", "피해야", "절대"]
    caution_kw = ["주의", "감소", "증가", "영향", "모니터", "확인", "조절", "상호작용", "출혈"]
    for kw in danger_kw:
        if kw in text:
            return "danger"
    for kw in caution_kw:
        if kw in text:
            return "caution"
    return "safe"


def _query_interactions(cursor, supplement_id: str, drug_names: list[str]) -> list[dict]:
    """supplement_id로 상호작용 조회. drug_names가 있으면 해당 약물만 필터."""
    if drug_names:
        placeholders = ", ".join(["%s"] * len(drug_names))
        cursor.execute(
            _INTERACTION_SELECT +
            f"WHERE si.supplement_id = %s AND cde.canonical_drug_name_ko IN ({placeholders})",
            (supplement_id, *drug_names),
        )
    else:
        cursor.execute(
            _INTERACTION_SELECT + "WHERE si.supplement_id = %s",
            (supplement_id,),
        )
    return cursor.fetchall()


@router.post("/interactions/analyze", response_model=AnalyzeResponse)
def analyze_interactions(body: AnalyzeRequest):
    """
    여러 항목(알약 + 건강기능식품)의 상호작용을 한번에 분석해 프론트엔드 표시 형식으로 반환.

    - 건강기능식품 성분 × 알약 약물 조합을 DB에서 조회
    - 알약이 없으면 건강기능식품 성분 전체 상호작용 반환
    - claim_text_original 키워드로 danger / caution / safe 추론
    """
    lang = parse_lang(body.lang)
    supplements = [it for it in body.items if it.category == "건강기능식품 라벨"]
    drugs = [it for it in body.items if it.category == "알약"]
    drug_names = [d.name for d in drugs]

    if not supplements:
        return AnalyzeResponse(
            overall="safe",
            summary=get_summary("no_supplements", lang),
            pairs=[],
        )

    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        pairs: list[InteractionPair] = []
        pair_id = 0

        for supp in supplements:
            resolved = resolve_supplement(supp.name)
            if not resolved:
                continue

            rows = _query_interactions(cursor, resolved.supplement_id, drug_names)
            for row in rows:
                level = _infer_level(row["claim_text_original"])
                drug_label = row["drug_canonical_ko"] or row["drug_canonical_en"] or "알 수 없는 약물"
                pair_id += 1
                description = row["claim_text_original"] or "상호작용 정보가 있습니다."
                pairs.append(InteractionPair(
                    id=str(pair_id),
                    items=[resolved.supplement_name_ko, drug_label],
                    level=level,
                    description=translate(description, lang),
                ))

        if not pairs:
            return AnalyzeResponse(
                overall="safe",
                summary=get_summary("no_interactions", lang),
                pairs=[],
            )

        pairs.sort(key=lambda p: LEVEL_RANK[p.level], reverse=True)
        overall: RiskLevel = pairs[0].level

        return AnalyzeResponse(
            overall=overall,
            summary=get_summary(overall, lang),
            pairs=pairs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
