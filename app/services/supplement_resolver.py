"""
Resolve supplement labels against the main DB schema.

Priority:
1. supplement_entities exact Korean / English names
2. supplement_product_markers exact or normalized marker text
3. supplement_entities partial match
4. legacy supplement_map / supplement_aliases fallback for old running DBs
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.db.connection import get_conn


@dataclass
class ResolvedSupplement:
    supplement_id: str
    canonical_name_ko: str
    canonical_name_en: Optional[str]
    matched_alias: str
    match_type: str


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


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


def _resolved_from_main(cursor, name: str) -> Optional[ResolvedSupplement]:
    if not _table_exists(cursor, "supplement_entities"):
        return None

    clean = name.strip()
    normalized = _normalize(clean)

    cursor.execute(
        """
        SELECT supplement_id, supplement_name_ko, supplement_name_en
        FROM supplement_entities
        WHERE supplement_name_ko = %s OR LOWER(supplement_name_en) = LOWER(%s)
        LIMIT 1
        """,
        (clean, clean),
    )
    row = cursor.fetchone()
    if row:
        return ResolvedSupplement(
            supplement_id=row["supplement_id"],
            canonical_name_ko=row["supplement_name_ko"],
            canonical_name_en=row.get("supplement_name_en"),
            matched_alias=clean,
            match_type="exact_main",
        )

    if _table_exists(cursor, "supplement_product_markers"):
        cursor.execute(
            """
            SELECT se.supplement_id, se.supplement_name_ko, se.supplement_name_en,
                   spm.marker_text
            FROM supplement_product_markers spm
            JOIN supplement_entities se ON se.supplement_id = spm.supplement_id
            WHERE spm.marker_text = %s OR spm.marker_text_normalized = %s
            ORDER BY LENGTH(spm.marker_text) ASC
            LIMIT 1
            """,
            (clean, normalized),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["supplement_name_ko"],
                canonical_name_en=row.get("supplement_name_en"),
                matched_alias=row.get("marker_text") or clean,
                match_type="marker_main",
            )

    cursor.execute(
        """
        SELECT supplement_id, supplement_name_ko, supplement_name_en,
               supplement_name_ko AS matched,
               LENGTH(supplement_name_ko) AS name_len
        FROM supplement_entities
        WHERE CHAR_LENGTH(supplement_name_ko) >= 3
          AND (supplement_name_ko LIKE %s
               OR supplement_name_en LIKE %s
               OR %s LIKE CONCAT(CHAR(37), supplement_name_ko, CHAR(37)))
        ORDER BY name_len ASC
        LIMIT 1
        """,
        (f"%{clean}%", f"%{clean}%", clean),
    )
    row = cursor.fetchone()
    if row:
        return ResolvedSupplement(
            supplement_id=row["supplement_id"],
            canonical_name_ko=row["supplement_name_ko"],
            canonical_name_en=row.get("supplement_name_en"),
            matched_alias=row.get("matched") or clean,
            match_type="partial_main",
        )

    return None


def _resolved_from_legacy(cursor, name: str) -> Optional[ResolvedSupplement]:
    if not _table_exists(cursor, "supplement_map"):
        return None

    clean = name.strip()
    normalized = _normalize(clean)
    cursor.execute(
        """
        SELECT supplement_id, canonical_name_ko, canonical_name_en, raw_name
        FROM supplement_map
        WHERE canonical_name_ko = %s OR raw_name = %s
        LIMIT 1
        """,
        (clean, clean),
    )
    row = cursor.fetchone()
    if row:
        return ResolvedSupplement(
            supplement_id=row["supplement_id"],
            canonical_name_ko=row["canonical_name_ko"],
            canonical_name_en=row.get("canonical_name_en"),
            matched_alias=clean,
            match_type="exact_legacy",
        )

    if _table_exists(cursor, "supplement_aliases"):
        cursor.execute(
            """
            SELECT sm.supplement_id, sm.canonical_name_ko, sm.canonical_name_en, sa.alias
            FROM supplement_aliases sa
            JOIN supplement_map sm ON sa.supplement_id = sm.supplement_id
            WHERE sa.alias = %s
               OR REPLACE(REPLACE(REPLACE(LOWER(sa.alias), CHAR(32), ''), CHAR(45), ''), CHAR(95), '') = %s
            LIMIT 1
            """,
            (clean, normalized),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row.get("canonical_name_en"),
                matched_alias=row.get("alias") or clean,
                match_type="alias_legacy",
            )

    cursor.execute(
        """
        SELECT supplement_id, canonical_name_ko, canonical_name_en,
               canonical_name_ko AS matched,
               LENGTH(canonical_name_ko) AS name_len
        FROM supplement_map
        WHERE CHAR_LENGTH(canonical_name_ko) >= 3
          AND (canonical_name_ko LIKE %s OR raw_name LIKE %s OR %s LIKE CONCAT(CHAR(37), canonical_name_ko, CHAR(37)))
        ORDER BY name_len ASC
        LIMIT 1
        """,
        (f"%{clean}%", f"%{clean}%", clean),
    )
    row = cursor.fetchone()
    if row:
        return ResolvedSupplement(
            supplement_id=row["supplement_id"],
            canonical_name_ko=row["canonical_name_ko"],
            canonical_name_en=row.get("canonical_name_en"),
            matched_alias=row.get("matched") or clean,
            match_type="partial_legacy",
        )

    return None


def resolve_supplement(name: str) -> Optional[ResolvedSupplement]:
    """Return a canonical supplement match for display and interaction lookup."""
    if not name or not name.strip():
        return None

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        return _resolved_from_main(cursor, name) or _resolved_from_legacy(cursor, name)
    finally:
        cursor.close()
        conn.close()
