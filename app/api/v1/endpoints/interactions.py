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
from app.services.drug_resolver import resolve_drug
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
                """
                SELECT si.interaction_id AS claim_id,
                       se.supplement_name_ko AS supplement_canonical_ko,
                       cde.canonical_drug_name_ko AS drug_canonical_ko,
                       cde.canonical_drug_name_en AS drug_canonical_en,
                       sc.claim_text_original AS interaction_text_raw,
                       'caution' AS risk_level,
                       1 AS needs_attention,
                       'confirmed' AS evidence_status,
                       sc.source_name AS source_names,
                       sc.source_url AS source_urls
                FROM standardized_interactions si
                JOIN source_claims sc ON sc.source_claim_id = si.source_claim_id
                JOIN canonical_drug_entities cde ON cde.canonical_drug_id = si.canonical_drug_id
                JOIN supplement_entities se ON se.supplement_id = si.supplement_id
                WHERE si.supplement_id = %s
                ORDER BY si.interaction_id
                """,
                (resolved.supplement_id,),
            )
        else:
            cursor.execute(
                """
                SELECT si.interaction_id AS claim_id,
                       se.supplement_name_ko AS supplement_canonical_ko,
                       cde.canonical_drug_name_ko AS drug_canonical_ko,
                       cde.canonical_drug_name_en AS drug_canonical_en,
                       sc.claim_text_original AS interaction_text_raw,
                       'caution' AS risk_level,
                       1 AS needs_attention,
                       'confirmed' AS evidence_status,
                       sc.source_name AS source_names,
                       sc.source_url AS source_urls
                FROM standardized_interactions si
                JOIN source_claims sc ON sc.source_claim_id = si.source_claim_id
                JOIN canonical_drug_entities cde ON cde.canonical_drug_id = si.canonical_drug_id
                JOIN supplement_entities se ON se.supplement_id = si.supplement_id
                WHERE se.supplement_name_ko LIKE %s
                   OR se.supplement_name_en LIKE %s
                ORDER BY si.interaction_id
                """,
                (f"%{supplement}%", f"%{supplement}%"),
            )

        rows = cursor.fetchall()

        interactions = [
            InteractionResult(
                interaction_id=str(row.get("claim_id") or ""),
                supplement_name_ko=row.get("supplement_canonical_ko"),
                drug_canonical_ko=row.get("drug_canonical_ko"),
                drug_canonical_en=row.get("drug_canonical_en"),
                claim_text_original=row.get("interaction_text_raw"),
            )
            for row in rows
        ]
        return InteractionResponse(
            supplement_name=supplement,
            resolved_name=resolved.supplement_name_ko if resolved else None,
            matched_alias=resolved.matched_alias if resolved else None,
            match_type=resolved.match_type if resolved else "not_found",
            interactions=interactions,
            total=len(interactions),
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
    for kw in danger_kw:
        if kw in text:
            return "danger"
    return "caution"


def _level_from_row(row: dict) -> RiskLevel:
    """DB row의 risk_level을 우선 사용하고, 없으면 기존 텍스트 키워드 추론으로 fallback."""
    raw_level = str(row.get("risk_level") or "").strip().lower()
    if raw_level in {"danger", "high", "major", "contraindicated", "avoid"}:
        return "danger"
    if raw_level in {"caution", "warning", "moderate", "minor"}:
        return "caution"
    if raw_level in {"safe", "no_known_warning", "none", "unknown"}:
        return "safe"
    if bool(row.get("needs_attention")):
        return _infer_level(row.get("interaction_text_raw") or row.get("reason"))
    return _infer_level(row.get("interaction_text_raw") or row.get("reason"))


def _interaction_description(row: dict) -> str:
    """현재 DB의 긴 근거 문장을 앱에서 읽기 좋은 1차 설명으로 축약."""
    text = str(row.get("interaction_text_raw") or row.get("reason") or "").strip()
    if not text:
        return "상호작용 정보가 있습니다."
    first_claim = text.split(" | ", 1)[0].strip()
    if len(first_claim) > 700:
        return first_claim[:697].rstrip() + "..."
    return first_claim


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


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone()
    return bool(row and row["count"] > 0)


def _resolve_official_product_ingredients(cursor, drug_names: list[str]) -> tuple[list[dict], set[str]]:
    """공식 제품 카탈로그 기준으로 제품명을 성분 canonical drug rows로 확장."""
    resolved: list[dict] = []
    matched_inputs: set[str] = set()
    seen_ids: set[str] = set()

    if not _table_exists(cursor, "official_drug_products") or not _table_exists(
        cursor,
        "official_drug_product_ingredients",
    ):
        return resolved, matched_inputs

    for clean in _clean_unique(drug_names):
        normalized = _normalize_match_key(clean)
        if len(normalized) < 3:
            continue
        product_keys = _product_lookup_keys(clean)
        like_keys = [key for key in product_keys if key != normalized]
        cursor.execute(
            """
            SELECT odpi.canonical_drug_id, cde.canonical_name_ko, cde.canonical_name_en
            FROM official_drug_products odp
            JOIN official_drug_product_ingredients odpi ON odpi.item_seq = odp.item_seq
            JOIN canonical_drug_entities cde ON odpi.canonical_drug_id = cde.canonical_drug_id
            WHERE odp.product_name = %s
               OR odp.normalized_product_name = %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
            ORDER BY odp.updated_at DESC, odpi.id
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


def _resolve_product_ingredients(cursor, drug_names: list[str]) -> tuple[list[dict], set[str]]:
    """레거시 제품명 테이블을 성분 canonical drug rows로 확장."""
    resolved: list[dict] = []
    matched_inputs: set[str] = set()
    seen_ids: set[str] = set()

    if not _table_exists(cursor, "pill_product_ingredients"):
        return resolved, matched_inputs

    for clean in _clean_unique(drug_names):
        normalized = _normalize_match_key(clean)
        if len(normalized) < 3:
            continue
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


def _resolve_v2_drug_ingredients(cursor, ingredient_names: list[str]) -> list[dict]:
    """v0.22 canonical drug alias table 기준으로 성분명을 표준 약 성분 ID로 해석."""
    if not _table_exists(cursor, "v2_drug_ingredient_aliases") or not _table_exists(
        cursor,
        "v2_canonical_drug_entities",
    ):
        return []

    resolved: list[dict] = []
    seen_ids: set[str] = set()
    for clean in _clean_unique(ingredient_names):
        if _is_non_ingredient_text(clean):
            continue
        normalized = _normalize_match_key(clean)
        if len(normalized) < 2:
            continue
        cursor.execute(
            """
            SELECT cde.canonical_drug_id, cde.canonical_name_ko, cde.canonical_name_en
            FROM v2_drug_ingredient_aliases alias
            JOIN v2_canonical_drug_entities cde ON cde.canonical_drug_id = alias.canonical_drug_id
            WHERE alias.alias_text = %s
               OR alias.alias_normalized = %s
               OR cde.canonical_name_ko = %s
               OR LOWER(cde.canonical_name_en) = LOWER(%s)
            ORDER BY CASE alias.alias_type
                WHEN 'canonical_ko' THEN 1
                WHEN 'canonical_en' THEN 2
                ELSE 3
            END
            LIMIT 8
            """,
            (clean, normalized, clean, clean),
        )
        rows = cursor.fetchall()
        if not rows and len(normalized) >= 3:
            cursor.execute(
                """
                SELECT cde.canonical_drug_id, cde.canonical_name_ko, cde.canonical_name_en
                FROM v2_drug_ingredient_aliases alias
                JOIN v2_canonical_drug_entities cde ON cde.canonical_drug_id = alias.canonical_drug_id
                WHERE alias.alias_normalized LIKE %s
                   OR %s LIKE CONCAT('%', alias.alias_normalized, '%')
                ORDER BY LENGTH(alias.alias_text) ASC
                LIMIT 8
                """,
                (f"%{normalized}%", normalized),
            )
            rows = cursor.fetchall()
        for row in rows:
            drug_id = row["canonical_drug_id"]
            if drug_id in seen_ids:
                continue
            seen_ids.add(drug_id)
            resolved.append(row)
    return resolved


def _resolve_v2_official_product_ingredients(cursor, drug_names: list[str]) -> tuple[list[dict], set[str]]:
    """공식 제품 캐시의 성분명을 v0.22 canonical drug rows로 확장."""
    resolved: list[dict] = []
    matched_inputs: set[str] = set()
    seen_ids: set[str] = set()

    if not _table_exists(cursor, "official_drug_products") or not _table_exists(
        cursor,
        "official_drug_product_ingredients",
    ):
        return resolved, matched_inputs

    for clean in _clean_unique(drug_names):
        normalized = _normalize_match_key(clean)
        if len(normalized) < 3:
            continue
        product_keys = _product_lookup_keys(clean)
        like_keys = [key for key in product_keys if key != normalized]
        cursor.execute(
            """
            SELECT odpi.ingredient_name,
                   odpi.canonical_drug_id AS legacy_canonical_drug_id,
                   v2.canonical_drug_id AS v2_canonical_drug_id,
                   v2.canonical_name_ko AS v2_canonical_name_ko,
                   v2.canonical_name_en AS v2_canonical_name_en
            FROM official_drug_products odp
            JOIN official_drug_product_ingredients odpi ON odpi.item_seq = odp.item_seq
            LEFT JOIN v2_canonical_drug_entities v2 ON v2.canonical_drug_id = odpi.canonical_drug_id
            WHERE odp.product_name = %s
               OR odp.normalized_product_name = %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
               OR odp.normalized_product_name LIKE %s
            ORDER BY odp.updated_at DESC, odpi.id
            LIMIT 16
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
            if row.get("v2_canonical_drug_id"):
                drug_id = row["v2_canonical_drug_id"]
                if drug_id in seen_ids:
                    continue
                seen_ids.add(drug_id)
                resolved.append({
                    "canonical_drug_id": drug_id,
                    "canonical_name_ko": row.get("v2_canonical_name_ko"),
                    "canonical_name_en": row.get("v2_canonical_name_en"),
                })
                continue

            for ingredient_row in _resolve_v2_drug_ingredients(cursor, [row.get("ingredient_name") or ""]):
                drug_id = ingredient_row["canonical_drug_id"]
                if drug_id in seen_ids:
                    continue
                seen_ids.add(drug_id)
                resolved.append(ingredient_row)

    return resolved, matched_inputs


def _resolve_v2_drugs(cursor, drug_names: list[str]) -> tuple[list[dict], int, set[str]]:
    """v0.22 약 성분 기준으로 제품명/성분명을 우선 해석."""
    resolved: list[dict] = []
    seen_ids: set[str] = set()

    product_rows, product_inputs = _resolve_v2_official_product_ingredients(cursor, drug_names)
    for row in product_rows:
        drug_id = row["canonical_drug_id"]
        if drug_id in seen_ids:
            continue
        seen_ids.add(drug_id)
        resolved.append(row)

    ingredient_candidates = [
        name
        for name in drug_names
        if name not in product_inputs and not _is_non_ingredient_text(name)
    ]
    ingredient_rows = _resolve_v2_drug_ingredients(cursor, ingredient_candidates)
    matched_ingredient_inputs: set[str] = set()
    for row in ingredient_rows:
        drug_id = row["canonical_drug_id"]
        if drug_id in seen_ids:
            continue
        seen_ids.add(drug_id)
        resolved.append(row)
    resolved_names = {
        _normalize_match_key(name)
        for row in resolved
        for name in [row.get("canonical_name_ko"), row.get("canonical_name_en")]
        if name
    }
    for name in ingredient_candidates:
        if _normalize_match_key(name) in resolved_names:
            matched_ingredient_inputs.add(name)

    unresolved_count = len([
        name
        for name in ingredient_candidates
        if name not in matched_ingredient_inputs
    ])
    return resolved, unresolved_count, product_inputs


def _resolve_drugs_v3(cursor, drug_names: list[str]) -> tuple[list[dict], int, set[str]]:
    """v3 스키마: drug_aliases + canonical_drug_entities로 성분명 해석."""
    if not _table_exists(cursor, "drug_aliases") or not _table_exists(cursor, "canonical_drug_entities"):
        return [], 0, set()

    resolved: list[dict] = []
    seen_ids: set[str] = set()
    matched_inputs: set[str] = set()

    for name in _clean_unique(drug_names):
        if _is_non_ingredient_text(name):
            continue
        normalized = _normalize_match_key(name)
        if len(normalized) < 2:
            continue
        cursor.execute(
            """
            SELECT cde.canonical_drug_id,
                   cde.canonical_drug_name_ko AS canonical_name_ko,
                   cde.canonical_drug_name_en AS canonical_name_en
            FROM canonical_drug_entities cde
            LEFT JOIN drug_aliases da ON da.canonical_drug_id = cde.canonical_drug_id
            WHERE cde.canonical_drug_name_ko = %s
               OR LOWER(cde.canonical_drug_name_en) = LOWER(%s)
               OR REPLACE(REPLACE(LOWER(cde.canonical_drug_name_ko), ' ', ''), '-', '') = %s
               OR da.alias_name = %s
               OR da.alias_name_normalized = %s
               OR da.alias_name_normalized LIKE %s
            GROUP BY cde.canonical_drug_id
            LIMIT 8
            """,
            (name, name, normalized, name, normalized, f"%{normalized}%"),
        )
        rows = cursor.fetchall()
        if not rows:
            continue
        matched_inputs.add(name)
        for row in rows:
            drug_id = row["canonical_drug_id"]
            if drug_id in seen_ids:
                continue
            seen_ids.add(drug_id)
            resolved.append(row)

    unresolved_count = sum(
        1 for name in drug_names
        if name not in matched_inputs and not _is_non_ingredient_text(name)
    )
    return resolved, unresolved_count, matched_inputs


def _resolve_drugs(cursor, drug_names: list[str]) -> tuple[list[dict], int, set[str]]:
    """입력된 제품명/성분명을 canonical_drug_entities 행으로 최대한 해석."""
    # v3 스키마 우선
    v3_rows, v3_unresolved_count, v3_inputs = _resolve_drugs_v3(cursor, drug_names)
    if v3_rows:
        return v3_rows, v3_unresolved_count, v3_inputs

    # 레거시 경로 (구 스키마 테이블이 있을 때만 동작)
    v2_rows, v2_unresolved_count, v2_product_inputs = _resolve_v2_drugs(cursor, drug_names)
    if v2_rows:
        return v2_rows, v2_unresolved_count, v2_product_inputs

    resolved: list[dict] = []
    unresolved_count = 0
    seen: set[str] = set()

    product_rows, product_inputs = _resolve_official_product_ingredients(cursor, drug_names)
    legacy_product_rows, legacy_product_inputs = _resolve_product_ingredients(
        cursor,
        [name for name in drug_names if name not in product_inputs],
    )
    product_inputs.update(legacy_product_inputs)
    product_rows.extend(legacy_product_rows)

    for row in product_rows:
        drug_id = row["canonical_drug_id"]
        if drug_id not in seen:
            seen.add(drug_id)
            resolved.append(row)

    for clean in _clean_unique([n for n in drug_names if n not in product_inputs and not _is_non_ingredient_text(n)]):
        unresolved_count += 1

    return resolved, unresolved_count, product_inputs


def _resolve_drug_ids(cursor, drug_names: list[str]) -> list[str]:
    resolved, _, _ = _resolve_drugs(cursor, drug_names)
    return [row["canonical_drug_id"] for row in resolved]


def _expanded_v2_drug_scope_ids(cursor, drug_ids: list[str]) -> list[str]:
    """사용자 약 성분 ID를 v0.22의 class/composite claim 조회 범위로 확장."""
    expanded: list[str] = []
    seen: set[str] = set()
    for drug_id in drug_ids:
        if drug_id and drug_id not in seen:
            seen.add(drug_id)
            expanded.append(drug_id)

    if not drug_ids:
        return expanded

    placeholders = ", ".join(["%s"] * len(drug_ids))
    if _table_exists(cursor, "v2_drug_class_membership"):
        cursor.execute(
            f"""
            SELECT class_canonical_drug_id AS canonical_drug_id
            FROM v2_drug_class_membership
            WHERE member_canonical_drug_id IN ({placeholders})
              AND COALESCE(default_applicability, 'YES') = 'YES'
            """,
            tuple(drug_ids),
        )
        for row in cursor.fetchall():
            drug_id = row["canonical_drug_id"]
            if drug_id and drug_id not in seen:
                seen.add(drug_id)
                expanded.append(drug_id)

    if _table_exists(cursor, "v2_claim_target_map"):
        cursor.execute(
            f"""
            SELECT source_composite_canonical_drug_id AS canonical_drug_id
            FROM v2_claim_target_map
            WHERE target_canonical_drug_id IN ({placeholders})
              AND COALESCE(review_status, 'CHECKED') IN ('CHECKED', 'VERIFIED')
            """,
            tuple(drug_ids),
        )
        for row in cursor.fetchall():
            drug_id = row["canonical_drug_id"]
            if drug_id and drug_id not in seen:
                seen.add(drug_id)
                expanded.append(drug_id)

    if _table_exists(cursor, "v2_drug_combination_components"):
        cursor.execute(
            f"""
            SELECT combination_canonical_drug_id AS canonical_drug_id
            FROM v2_drug_combination_components
            WHERE component_canonical_drug_id IN ({placeholders})
              AND COALESCE(review_status, 'CHECKED') IN ('CHECKED', 'VERIFIED', 'PARTIAL')
            """,
            tuple(drug_ids),
        )
        for row in cursor.fetchall():
            drug_id = row["canonical_drug_id"]
            if drug_id and drug_id not in seen:
                seen.add(drug_id)
                expanded.append(drug_id)

    return expanded


def _query_v2_interactions(cursor, supplement_id: str, drug_ids: list[str], drug_names: list[str]) -> list[dict]:
    """v0.22 standardized_interactions를 우선 조회."""
    if not _table_exists(cursor, "v2_standardized_interactions"):
        return []

    if drug_ids:
        scope_ids = _expanded_v2_drug_scope_ids(cursor, drug_ids)
        placeholders = ", ".join(["%s"] * len(scope_ids))
        cursor.execute(
            f"""
            SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw,
                   'caution' AS risk_level,
                   1 AS needs_attention,
                   overall_review_status AS evidence_status,
                   source_name AS source_names,
                   source_url AS source_urls
            FROM v2_standardized_interactions
            WHERE supplement_id = %s
              AND canonical_drug_id IN ({placeholders})
            ORDER BY claim_id
            """,
            (supplement_id, *scope_ids),
        )
        return cursor.fetchall()

    if drug_names:
        clean_names = _clean_unique(drug_names)
        placeholders = ", ".join(["%s"] * len(clean_names))
        cursor.execute(
            f"""
            SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
                   drug_canonical_en, interaction_text_raw,
                   'caution' AS risk_level,
                   1 AS needs_attention,
                   overall_review_status AS evidence_status,
                   source_name AS source_names,
                   source_url AS source_urls
            FROM v2_standardized_interactions
            WHERE supplement_id = %s
              AND (drug_canonical_ko IN ({placeholders})
                   OR drug_canonical_en IN ({placeholders}))
            ORDER BY claim_id
            """,
            (supplement_id, *clean_names, *clean_names),
        )
        return cursor.fetchall()

    cursor.execute(
        """
        SELECT claim_id, supplement_canonical_ko, canonical_drug_id, drug_canonical_ko,
               drug_canonical_en, interaction_text_raw,
               'caution' AS risk_level,
               1 AS needs_attention,
               overall_review_status AS evidence_status,
               source_name AS source_names,
               source_url AS source_urls
        FROM v2_standardized_interactions
        WHERE supplement_id = %s
        ORDER BY claim_id
        """,
        (supplement_id,),
    )
    return cursor.fetchall()


def _query_interactions_v3(cursor, supplement_id: str, drug_ids: list[str]) -> list[dict]:
    """v3 스키마: standardized_interactions + source_claims JOIN."""
    if not _table_exists(cursor, "standardized_interactions"):
        return []

    if drug_ids:
        placeholders = ", ".join(["%s"] * len(drug_ids))
        cursor.execute(
            f"""
            SELECT si.interaction_id AS claim_id,
                   se.supplement_name_ko AS supplement_canonical_ko,
                   cde.canonical_drug_id,
                   cde.canonical_drug_name_ko AS drug_canonical_ko,
                   cde.canonical_drug_name_en AS drug_canonical_en,
                   sc.claim_text_original AS interaction_text_raw,
                   'caution' AS risk_level,
                   1 AS needs_attention,
                   'confirmed' AS evidence_status,
                   sc.source_name AS source_names,
                   sc.source_url AS source_urls
            FROM standardized_interactions si
            JOIN source_claims sc ON sc.source_claim_id = si.source_claim_id
            JOIN canonical_drug_entities cde ON cde.canonical_drug_id = si.canonical_drug_id
            JOIN supplement_entities se ON se.supplement_id = si.supplement_id
            WHERE si.supplement_id = %s
              AND si.canonical_drug_id IN ({placeholders})
            ORDER BY si.interaction_id
            """,
            (supplement_id, *drug_ids),
        )
    else:
        cursor.execute(
            """
            SELECT si.interaction_id AS claim_id,
                   se.supplement_name_ko AS supplement_canonical_ko,
                   cde.canonical_drug_id,
                   cde.canonical_drug_name_ko AS drug_canonical_ko,
                   cde.canonical_drug_name_en AS drug_canonical_en,
                   sc.claim_text_original AS interaction_text_raw,
                   'caution' AS risk_level,
                   1 AS needs_attention,
                   'confirmed' AS evidence_status,
                   sc.source_name AS source_names,
                   sc.source_url AS source_urls
            FROM standardized_interactions si
            JOIN source_claims sc ON sc.source_claim_id = si.source_claim_id
            JOIN canonical_drug_entities cde ON cde.canonical_drug_id = si.canonical_drug_id
            JOIN supplement_entities se ON se.supplement_id = si.supplement_id
            WHERE si.supplement_id = %s
            ORDER BY si.interaction_id
            """,
            (supplement_id,),
        )
    return cursor.fetchall()


def _query_interactions(cursor, supplement_id: str, drug_ids: list[str], drug_names: list[str]) -> list[dict]:
    """v3 스키마 우선, 없으면 레거시 경로."""
    v3_rows = _query_interactions_v3(cursor, supplement_id, drug_ids)
    if v3_rows:
        return v3_rows
    return _query_v2_interactions(cursor, supplement_id, drug_ids, drug_names)


def _resolve_v2_supplements(cursor, supplement_names: list[str]) -> tuple[list[dict], set[str]]:
    """건기식 라벨명을 v0.22 공식 원료/alias/scope 기준으로 해석."""
    if not _table_exists(cursor, "v2_supplement_label_aliases") or not _table_exists(
        cursor,
        "v2_interaction_scope_map",
    ):
        return [], set()

    resolved_items: list[dict] = []
    matched_inputs: set[str] = set()
    seen: set[str] = set()
    for name in _clean_unique(supplement_names):
        normalized = _normalize_match_key(name)
        if not normalized:
            continue
        if _table_exists(cursor, "v2_supplement_label_exclusions"):
            cursor.execute(
                """
                SELECT exclusion_id
                FROM v2_supplement_label_exclusions
                WHERE excluded_text_raw = %s
                   OR excluded_text_normalized = %s
                LIMIT 1
                """,
                (name, normalized),
            )
            if cursor.fetchone():
                continue

        cursor.execute(
            """
            SELECT ism.interaction_supplement_id AS supplement_id,
                   COALESCE(vsm.canonical_name_ko, osi.official_ingredient_name_ko) AS canonical_name_ko,
                   COALESCE(vsm.canonical_name_en, osi.official_ingredient_name_en) AS canonical_name_en,
                   sla.alias_text_raw AS matched_alias,
                   sla.match_level,
                   ism.relation_type
            FROM v2_supplement_label_aliases sla
            JOIN v2_official_supplement_ingredients osi
              ON osi.official_ingredient_id = sla.official_ingredient_id
            JOIN v2_interaction_scope_map ism
              ON ism.official_ingredient_id = sla.official_ingredient_id
            LEFT JOIN v2_supplement_map vsm
              ON vsm.supplement_id = ism.interaction_supplement_id
            WHERE (sla.alias_text_raw = %s OR sla.alias_text_normalized = %s)
              AND COALESCE(sla.standalone_match_allowed, 1) = 1
              AND COALESCE(ism.interaction_applicability, 'YES') = 'YES'
            ORDER BY CASE COALESCE(sla.ambiguity_status, 'UNIQUE')
                WHEN 'UNIQUE' THEN 1
                ELSE 2
            END,
            LENGTH(sla.alias_text_raw)
            LIMIT 4
            """,
            (name, normalized),
        )
        rows = cursor.fetchall()
        if not rows and len(normalized) >= 3:
            cursor.execute(
                """
                SELECT ism.interaction_supplement_id AS supplement_id,
                       COALESCE(vsm.canonical_name_ko, osi.official_ingredient_name_ko) AS canonical_name_ko,
                       COALESCE(vsm.canonical_name_en, osi.official_ingredient_name_en) AS canonical_name_en,
                       sla.alias_text_raw AS matched_alias,
                       sla.match_level,
                       ism.relation_type
                FROM v2_supplement_label_aliases sla
                JOIN v2_official_supplement_ingredients osi
                  ON osi.official_ingredient_id = sla.official_ingredient_id
                JOIN v2_interaction_scope_map ism
                  ON ism.official_ingredient_id = sla.official_ingredient_id
                LEFT JOIN v2_supplement_map vsm
                  ON vsm.supplement_id = ism.interaction_supplement_id
                WHERE (sla.alias_text_normalized LIKE %s
                       OR %s LIKE CONCAT('%', sla.alias_text_normalized, '%'))
                  AND COALESCE(sla.standalone_match_allowed, 1) = 1
                  AND COALESCE(ism.interaction_applicability, 'YES') = 'YES'
                ORDER BY LENGTH(sla.alias_text_raw) ASC
                LIMIT 4
                """,
                (f"%{normalized}%", normalized),
            )
            rows = cursor.fetchall()

        if not rows:
            continue
        matched_inputs.add(name)
        for row in rows:
            supplement_id = row["supplement_id"]
            if supplement_id in seen:
                continue
            seen.add(supplement_id)
            resolved_items.append({
                "id": supplement_id,
                "label": row.get("canonical_name_ko") or row.get("canonical_name_en") or name,
                "matchedAlias": row.get("matched_alias"),
                "source": "v0.22",
            })
    return resolved_items, matched_inputs


def _resolve_supplements_v3(cursor, supplement_names: list[str]) -> tuple[list[dict], set[str]]:
    """v3 스키마: supplement_entities로 건기식 성분명 해석."""
    if not _table_exists(cursor, "supplement_entities"):
        return [], set()

    resolved: list[dict] = []
    matched_inputs: set[str] = set()
    seen: set[str] = set()

    for name in _clean_unique(supplement_names):
        normalized = _normalize_match_key(name)
        if not normalized:
            continue
        cursor.execute(
            """
            SELECT supplement_id,
                   supplement_name_ko AS canonical_name_ko,
                   supplement_name_en AS canonical_name_en
            FROM supplement_entities
            WHERE supplement_name_ko = %s
               OR LOWER(supplement_name_en) = LOWER(%s)
               OR REPLACE(LOWER(supplement_name_ko), ' ', '') LIKE %s
            LIMIT 4
            """,
            (name, name, f"%{normalized}%"),
        )
        rows = cursor.fetchall()
        if not rows:
            continue
        matched_inputs.add(name)
        for row in rows:
            sid = row["supplement_id"]
            if sid in seen:
                continue
            seen.add(sid)
            resolved.append({
                "id": sid,
                "label": row["canonical_name_ko"] or row["canonical_name_en"] or name,
                "matchedAlias": name,
                "source": "v3",
            })
    return resolved, matched_inputs


def _resolved_supplements(cursor, supplement_names: list[str]) -> tuple[list[dict], int]:
    """분석 후보 건강기능식품을 canonical supplement 기준으로 중복 제거."""
    resolved_items: list[dict] = []
    unresolved_count = 0
    seen: set[str] = set()

    # v3 스키마 우선
    v3_items, v3_matched_inputs = _resolve_supplements_v3(cursor, supplement_names)
    for item in v3_items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        resolved_items.append(item)

    remaining = [name for name in supplement_names if name not in v3_matched_inputs]

    # 레거시 경로 (구 스키마 테이블이 있을 때만 동작)
    v2_items, v2_matched_inputs = _resolve_v2_supplements(cursor, remaining)
    for item in v2_items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        resolved_items.append(item)

    for supp_name in [name for name in remaining if name not in v2_matched_inputs]:
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
            "matchedAlias": resolved.matched_alias,
            "source": "legacy",
        })
    return resolved_items, unresolved_count


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
    supplement_names = _clean_unique([s.name for s in supplements])
    drug_names = _clean_unique([d.name for d in drugs])

    if not supplements:
        response = AnalyzeResponse(
            overall="safe",
            summary=get_summary("no_supplements", lang),
            pairs=[],
            matchedDrugNames=[],
            matchedSupplementNames=[],
            ignoredDrugNames=[name for name in drug_names if _is_non_ingredient_text(name)],
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
        resolved_supplements, unresolved_supplement_count = _resolved_supplements(cursor, supplement_names)
        resolved_drugs, unresolved_drug_count, product_drug_names = _resolve_drugs(cursor, drug_names)
        ignored_drug_names = [
            name
            for name in drug_names
            if name not in product_drug_names and _is_non_ingredient_text(name)
        ]
        drug_ids = [row["canonical_drug_id"] for row in resolved_drugs]
        matched_drug_names = _clean_unique([
            name
            for row in resolved_drugs
            for name in [row["canonical_name_ko"] or row["canonical_name_en"]]
            if name
        ])
        matched_supplement_names = _clean_unique([row["label"] for row in resolved_supplements])
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
                    level = _level_from_row(row)
                    if level == "safe":
                        continue

                    drug_label = row["drug_canonical_ko"] or row["drug_canonical_en"] or "알 수 없는 약물"
                    drug_key = row.get("canonical_drug_id") or drug_label
                    detected_keys.add((supp["id"], drug_key))
                    pair_id += 1
                    description = _interaction_description(row)
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
                matchedDrugNames=matched_drug_names,
                matchedSupplementNames=matched_supplement_names,
                ignoredDrugNames=ignored_drug_names,
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
            matchedDrugNames=matched_drug_names,
            matchedSupplementNames=matched_supplement_names,
            ignoredDrugNames=ignored_drug_names,
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
