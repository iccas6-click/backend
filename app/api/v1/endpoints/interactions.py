from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

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

ANALYZE_DEBUG_LOG_PATH = os.getenv("CLICK_ANALYZE_DEBUG_LOG_PATH", "/tmp/click-analyze-debug.jsonl")
ANALYZE_DEBUG_LATEST_PATH = os.getenv("CLICK_ANALYZE_DEBUG_LATEST_PATH", "/tmp/click-last-analyze.json")

KNOWN_PRODUCT_TEXTS = {
    "리보테인",
    "텔미누보",
    "텔미누보40",
    "바스크롱",
    "이티민",
    "큐자임",
    "오메콜에프",
}


def _normalize_match_key(value: str) -> str:
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", value.strip().lower())


def _product_lookup_keys(value: str) -> list[str]:
    compact = _normalize_match_key(value)
    without_packaging = re.sub(r"(ptp|pvc|alu|al)$", "", compact, flags=re.IGNORECASE)
    without_units = re.sub(r"\d+(\.\d+)?(mg|g|mcg|μg|ug|iu|ml)?", "", without_packaging, flags=re.IGNORECASE)
    without_form = re.sub(r"(연질캡슐|필름코팅정|캡슐|정)$", "", without_units)
    keys = [compact, without_packaging, without_units, without_form]
    result: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _model_dump(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _write_analyze_debug_log(body: AnalyzeRequest, response: AnalyzeResponse, context: dict | None = None) -> None:
    """개발 중 프론트-백엔드 분석 입출력을 서버에서 바로 확인하기 위한 JSON 로그."""
    entry = {
        "loggedAt": datetime.now(timezone.utc).isoformat(),
        "request": {
            "lang": body.lang,
            "items": [_model_dump(item) for item in body.items],
        },
        "context": context or {},
        "response": _model_dump(response),
    }
    try:
        latest_dir = os.path.dirname(ANALYZE_DEBUG_LATEST_PATH)
        log_dir = os.path.dirname(ANALYZE_DEBUG_LOG_PATH)
        if latest_dir:
            os.makedirs(latest_dir, exist_ok=True)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(ANALYZE_DEBUG_LATEST_PATH, "w", encoding="utf-8") as latest_file:
            json.dump(entry, latest_file, ensure_ascii=False, indent=2)
        with open(ANALYZE_DEBUG_LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # 분석 API 자체가 로그 기록 실패 때문에 죽으면 안 된다.
        pass


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


def _is_non_ingredient_text(value: str) -> bool:
    clean = value.strip()
    compact = clean.replace(" ", "")
    if not compact:
        return True
    if compact.upper() in {"PTP", "PVC", "ALU", "AL", "정제", "캡슐"}:
        return True
    if re.fullmatch(r"\d+(\.\d+)?(mg|g|mcg|μg|ug|iu|ml|정|캡슐)?", compact, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"\d+/\d+(\.\d+)?(mg|g|mcg|μg|ug|iu|ml)?", compact, flags=re.IGNORECASE):
        return True
    if re.search(r"(정|캡슐|연질캡슐|필름코팅정)\d*(\.\d+)?\s*(mg|g|mcg|μg|ug|iu|ml)?$", compact, flags=re.IGNORECASE):
        return True
    if compact in KNOWN_PRODUCT_TEXTS:
        return True
    return False


def _looks_like_pill_product_text(value: str) -> bool:
    compact = value.strip().replace(" ", "")
    if compact in KNOWN_PRODUCT_TEXTS:
        return True
    return bool(re.search(r"(서방정|발포정|장용정|필름코팅정|연질캡슐|캡슐|정)", compact))


def _resolve_product_ingredients(cursor, drug_names: list[str]) -> tuple[list[dict], set[str]]:
    """AIHub 1000종 제품명으로 들어온 값을 제품 성분 canonical drug rows로 확장."""
    resolved: list[dict] = []
    matched_inputs: set[str] = set()
    seen_ids: set[str] = set()

    for clean in _clean_unique(drug_names):
        if not _looks_like_pill_product_text(clean):
            continue
        normalized = _normalize_match_key(clean)
        product_keys = _product_lookup_keys(clean)
        like_keys = [key for key in product_keys if key != normalized]
        cursor.execute(
            """
            SELECT ppi.canonical_drug_id, cde.canonical_name_ko, cde.canonical_name_en
            FROM pill_product_ingredients ppi
            JOIN canonical_drug_entities cde ON ppi.canonical_drug_id = cde.canonical_drug_id
            WHERE ppi.product_name = %s
               OR ppi.normalized_product_name = %s
               OR ppi.normalized_product_name LIKE %s
               OR ppi.normalized_product_name LIKE %s
               OR ppi.normalized_product_name LIKE %s
               OR ppi.normalized_product_name LIKE %s
            ORDER BY ppi.id
            """,
            (
                clean,
                normalized,
                f"%{normalized}%" if len(normalized) >= 3 else "__NO_MATCH__",
                f"%{like_keys[0]}%" if len(like_keys) > 0 else "__NO_MATCH__",
                f"%{like_keys[1]}%" if len(like_keys) > 1 else "__NO_MATCH__",
                f"%{like_keys[2]}%" if len(like_keys) > 2 else "__NO_MATCH__",
            ),
        )
        rows = cursor.fetchall()
        if not rows:
            continue
        matched_inputs.add(clean)
        for row in rows:
            drug_id = row["canonical_drug_id"]
            if drug_id in seen_ids:
                continue
            seen_ids.add(drug_id)
            resolved.append(row)

    return resolved, matched_inputs


def _resolve_drugs(cursor, drug_names: list[str]) -> tuple[list[dict], int, set[str]]:
    """입력된 제품명/성분명을 canonical_drug_entities 행으로 최대한 해석."""
    resolved: list[dict] = []
    unresolved_count = 0
    seen: set[str] = set()

    product_rows, product_inputs = _resolve_product_ingredients(cursor, drug_names)
    for row in product_rows:
        drug_id = row["canonical_drug_id"]
        seen.add(drug_id)
        resolved.append(row)

    ingredient_candidates = [
        name
        for name in drug_names
        if name not in product_inputs and not _is_non_ingredient_text(name)
    ]

    for clean in _clean_unique(ingredient_candidates):
        normalized = _normalize_match_key(clean)
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
                WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(canonical_name_ko), ' ', ''), '-', ''), '_', ''), '/', ''), '(', ''), ')', ''), '.', '') = %s
                   OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(canonical_name_en), ' ', ''), '-', ''), '_', ''), '/', ''), '(', ''), ')', ''), '.', '') = %s
                   OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(raw_aliases), ' ', ''), '-', ''), '_', ''), '/', ''), '(', ''), ')', ''), '.', '') LIKE %s
                LIMIT 8
                """,
                (normalized, normalized, f"%{normalized}%"),
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
        if not rows:
            unresolved_count += 1
            continue

        for row in rows:
            drug_id = row["canonical_drug_id"]
            if drug_id in seen:
                continue
            seen.add(drug_id)
            resolved.append(row)

    return resolved, unresolved_count, product_inputs


def _resolve_drug_ids(cursor, drug_names: list[str]) -> list[str]:
    resolved, _, _ = _resolve_drugs(cursor, drug_names)
    return [row["canonical_drug_id"] for row in resolved]


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
        response = AnalyzeResponse(
            overall="safe",
            summary=get_summary("no_supplements", lang),
            pairs=[],
            checkedCount=0,
            detectedCount=0,
            undetectedCount=0,
            unmatchedSupplementCount=0,
            unmatchedDrugCount=0,
            unmatchedCombinationCount=0,
        )
        _write_analyze_debug_log(
            body,
            response,
            {
                "reason": "no_supplements",
                "supplementNames": supplement_names,
                "drugNames": drug_names,
                "ignoredDrugNames": [name for name in drug_names if _is_non_ingredient_text(name)],
            },
        )
        return response

    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        pairs: list[InteractionPair] = []
        pair_id = 0
        detected_keys: set[tuple[str, str]] = set()
        resolved_supplements, unresolved_supplement_count = _resolved_supplements(supplement_names)
        resolved_drugs, unresolved_drug_count, product_drug_names = _resolve_drugs(cursor, drug_names)
        ignored_drug_names = [
            name
            for name in drug_names
            if name not in product_drug_names and _is_non_ingredient_text(name)
        ]
        drug_ids = [row["canonical_drug_id"] for row in resolved_drugs]
        total_supplement_count = len(resolved_supplements) + unresolved_supplement_count
        total_drug_count = len(drug_ids) + unresolved_drug_count
        checked_count = len(resolved_supplements) * len(drug_ids) if drug_ids else 0
        total_combination_count = total_supplement_count * total_drug_count if total_drug_count else 0
        unmatched_combination_count = max(total_combination_count - checked_count, 0)
        debug_context = {
            "supplementNames": supplement_names,
            "drugNames": drug_names,
            "ignoredDrugNames": ignored_drug_names,
            "resolvedSupplements": resolved_supplements,
            "unresolvedSupplementCount": unresolved_supplement_count,
            "resolvedDrugs": resolved_drugs,
            "unresolvedDrugCount": unresolved_drug_count,
            "matchedSupplementCount": len(resolved_supplements),
            "matchedDrugCount": len(drug_ids),
            "totalSupplementCount": total_supplement_count,
            "totalDrugCount": total_drug_count,
            "unmatchedCombinationCount": unmatched_combination_count,
        }

        if drug_ids or not drugs:
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
            response = AnalyzeResponse(
                overall="safe",
                summary=get_summary("no_interactions", lang),
                pairs=[],
                checkedCount=checked_count,
                detectedCount=detected_count,
                undetectedCount=undetected_count,
                unmatchedSupplementCount=unresolved_supplement_count,
                unmatchedDrugCount=unresolved_drug_count,
                unmatchedCombinationCount=unmatched_combination_count,
            )
            _write_analyze_debug_log(body, response, debug_context)
            return response

        pairs.sort(key=lambda p: LEVEL_RANK[p.level], reverse=True)
        overall: RiskLevel = pairs[0].level

        response = AnalyzeResponse(
            overall=overall,
            summary=get_summary(overall, lang),
            pairs=pairs,
            checkedCount=checked_count,
            detectedCount=detected_count,
            undetectedCount=undetected_count,
            unmatchedSupplementCount=unresolved_supplement_count,
            unmatchedDrugCount=unresolved_drug_count,
            unmatchedCombinationCount=unmatched_combination_count,
        )
        _write_analyze_debug_log(body, response, debug_context)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
