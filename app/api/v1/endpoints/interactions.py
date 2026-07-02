from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.db.connection import get_conn
from app.i18n import get_summary, parse_lang
from app.schemas.interaction import (
    AnalyzeItem,
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


def _infer_level(text: str | None) -> RiskLevel:
    """interaction_text_raw 키워드로 위험도 추론."""
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


def _clean_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.replace(" ", "").lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        cleaned.append(clean)
    return cleaned


def _resolve_drugs(cursor, drug_names: list[str]) -> list[dict]:
    """입력된 제품명/성분명을 canonical_drug_entities 행으로 최대한 해석."""
    resolved: list[dict] = []
    seen: set[str] = set()

    for clean in _clean_unique(drug_names):
        cursor.execute(
            """
            SELECT canonical_drug_id, canonical_name_ko, canonical_name_en
            FROM canonical_drug_entities
            WHERE canonical_name_ko = %s
               OR LOWER(canonical_name_en) = LOWER(%s)
            LIMIT 8
            """,
            (clean, clean),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                """
                SELECT canonical_drug_id, canonical_name_ko, canonical_name_en
                FROM canonical_drug_entities
                WHERE raw_aliases LIKE %s
               OR raw_aliases LIKE %s
               OR %s LIKE CONCAT('%', canonical_name_ko, '%')
               OR %s LIKE CONCAT('%', canonical_name_en, '%')
            LIMIT 8
            """,
                (f"%{clean}%", f"%{clean.lower()}%", clean, clean),
            )
            rows = cursor.fetchall()

        for row in rows:
            drug_id = row["canonical_drug_id"]
            if drug_id in seen:
                continue
            seen.add(drug_id)
            resolved.append(row)

    return resolved


def _resolve_drug_ids(cursor, drug_names: list[str]) -> list[str]:
    return [row["canonical_drug_id"] for row in _resolve_drugs(cursor, drug_names)]


def _query_interactions(cursor, supplement_id: str, drug_ids: list[str], drug_names: list[str]) -> list[dict]:
    """supplement_id로 상호작용 조회. drug_ids가 있으면 해당 약물만 필터."""
    if drug_ids:
        placeholders = ", ".join(["%s"] * len(drug_ids))
        cursor.execute(
            f"""
            SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw
            FROM standardized_interactions
            WHERE supplement_id = %s
              AND canonical_drug_id IN ({placeholders})
            """,
            (supplement_id, *drug_ids),
        )
    elif drug_names:
        placeholders = ", ".join(["%s"] * len(drug_names))
        cursor.execute(
            f"""
            SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw
            FROM standardized_interactions
            WHERE supplement_id = %s
              AND (drug_canonical_ko IN ({placeholders})
                   OR drug_canonical_en IN ({placeholders}))
            """,
            (supplement_id, *drug_names, *drug_names),
        )
    else:
        cursor.execute(
            """
            SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw
            FROM standardized_interactions
            WHERE supplement_id = %s
            """,
            (supplement_id,),
        )
    return cursor.fetchall()


def _resolved_supplements(supplement_names: list[str]) -> tuple[list[dict], int]:
    """분석 후보 건강기능식품을 canonical supplement 기준으로 중복 제거."""
    resolved_items: list[dict] = []
    unresolved_count = 0
    seen: set[str] = set()
    for supp_name in supplement_names:
        resolved = resolve_supplement(supp_name)
        if not resolved:
            unresolved_count += 1
            continue
        if resolved.supplement_id in seen:
            continue
        seen.add(resolved.supplement_id)
        resolved_items.append({
            "id": resolved.supplement_id,
            "label": resolved.canonical_name_ko,
        })
    return resolved_items, unresolved_count


@router.post("/interactions/analyze", response_model=AnalyzeResponse)
def analyze_interactions(body: AnalyzeRequest):
    """
    여러 항목(알약 + 건강기능식품)의 상호작용을 한번에 분석해 프론트엔드 표시 형식으로 반환.

    - 건강기능식품 성분 × 알약 약물 조합을 DB에서 조회
    - 알약이 없으면 건강기능식품 성분 전체 상호작용 반환
    - interaction_text_raw 키워드로 danger / caution / safe 추론
    """
    lang = parse_lang(body.lang)
    supplements = [it for it in body.items if it.category == "건강기능식품 라벨"]
    drugs = [it for it in body.items if it.category == "알약"]
    supplement_names = _clean_unique([s.name for s in supplements])
    drug_names = _clean_unique([d.name for d in drugs])

    if not supplements:
        return AnalyzeResponse(
            overall="safe",
            summary=get_summary("no_supplements", lang),
            pairs=[],
            checkedCount=0,
            detectedCount=0,
            undetectedCount=0,
        )

    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        pairs: list[InteractionPair] = []
        pair_id = 0
        detected_keys: set[tuple[str, str]] = set()
        resolved_supplements, unresolved_supplement_count = _resolved_supplements(supplement_names)
        resolved_drugs = _resolve_drugs(cursor, drug_names)
        drug_ids = [row["canonical_drug_id"] for row in resolved_drugs]
        checkable_supplement_count = len(resolved_supplements) + unresolved_supplement_count
        checked_count = checkable_supplement_count * len(drug_ids) if drug_ids else 0

        for supp in resolved_supplements:
            rows = _query_interactions(cursor, supp["id"], drug_ids, drug_names)
            for row in rows:
                level = _infer_level(row["interaction_text_raw"])
                if level == "safe":
                    continue

                drug_label = row["drug_canonical_ko"] or row["drug_canonical_en"] or "알 수 없는 약물"
                drug_key = row.get("canonical_drug_id") or drug_label
                detected_keys.add((supp["id"], drug_key))
                pair_id += 1
                description = row["interaction_text_raw"] or "상호작용 정보가 있습니다."
                pairs.append(InteractionPair(
                    id=str(pair_id),
                    items=[supp["label"], drug_label],
                    level=level,
                    description=translate(description, lang),
                ))

        detected_count = len(detected_keys)
        checked_count = max(checked_count, detected_count)
        undetected_count = max(checked_count - detected_count, 0)

        if not pairs:
            return AnalyzeResponse(
                overall="safe",
                summary=get_summary("no_interactions", lang),
                pairs=[],
                checkedCount=checked_count,
                detectedCount=detected_count,
                undetectedCount=undetected_count,
            )

        pairs.sort(key=lambda p: LEVEL_RANK[p.level], reverse=True)
        overall: RiskLevel = pairs[0].level

        return AnalyzeResponse(
            overall=overall,
            summary=get_summary(overall, lang),
            pairs=pairs,
            checkedCount=checked_count,
            detectedCount=detected_count,
            undetectedCount=undetected_count,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
