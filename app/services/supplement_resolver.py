"""
입력된 성분명을 supplement_entities의 canonical 성분으로 해석하는 서비스.

우선순위:
1. supplement_entities.supplement_name_ko 정확 일치
2. supplement_entities.supplement_name_en 정확 일치
3. 위 두 컬럼에 대한 LIKE 부분 일치 (가장 짧은 이름 우선)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.db.connection import get_conn


@dataclass
class ResolvedSupplement:
    supplement_id: str
    supplement_name_ko: str
    supplement_name_en: Optional[str]
    matched_alias: str   # 실제 매칭된 이름
    match_type: str      # exact_ko / exact_en / partial


def resolve_supplement(name: str) -> Optional[ResolvedSupplement]:
    """성분명으로 supplement_map 엔트리를 찾아 반환. 없으면 None."""
    clean = name.strip()
    normalized = clean.lower().replace(" ", "").replace("-", "").replace("_", "")
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1) supplement_name_ko 정확 일치
        cursor.execute(
            """
            SELECT supplement_id, supplement_name_ko, supplement_name_en
            FROM supplement_entities
            WHERE supplement_name_ko = %s
            LIMIT 1
            """,
            (clean, clean),
        )
        row = cursor.fetchone()
        if row:
            match_type = "exact_canonical" if row["canonical_name_ko"] == clean else "exact_raw"
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row["canonical_name_en"],
                matched_alias=clean,
                match_type=match_type,
            )

        # 2) supplement_name_en 정확 일치
        cursor.execute(
            """
            SELECT supplement_id, supplement_name_ko, supplement_name_en
            FROM supplement_entities
            WHERE supplement_name_en = %s
            LIMIT 1
            """,
            (clean,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                supplement_name_ko=row["supplement_name_ko"],
                supplement_name_en=row["supplement_name_en"],
                matched_alias=name,
                match_type="exact_en",
            )

        # 3) 띄어쓰기/하이픈/대소문자 차이를 무시한 정확 일치
        cursor.execute(
            """
            SELECT supplement_id, canonical_name_ko, canonical_name_en,
                   canonical_name_ko AS matched, 'canonical_normalized' AS src
            FROM supplement_map
            WHERE REPLACE(REPLACE(REPLACE(LOWER(canonical_name_ko), ' ', ''), '-', ''), '_', '') = %s
               OR REPLACE(REPLACE(REPLACE(LOWER(raw_name), ' ', ''), '-', ''), '_', '') = %s
            UNION ALL
            SELECT sm.supplement_id, sm.canonical_name_ko, sm.canonical_name_en,
                   sa.alias AS matched, 'alias_normalized' AS src
            FROM supplement_aliases sa
            JOIN supplement_map sm ON sa.supplement_id = sm.supplement_id
            WHERE REPLACE(REPLACE(REPLACE(LOWER(sa.alias), ' ', ''), '-', ''), '_', '') = %s
            LIMIT 1
            """,
            (normalized, normalized, normalized),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row["canonical_name_en"],
                matched_alias=row["matched"],
                match_type="normalized",
            )

        # 4) 부분 일치 (canonical_name_ko, raw_name, alias) — 가장 짧은 이름 우선
        cursor.execute(
            """
            SELECT supplement_id, canonical_name_ko, canonical_name_en,
                   canonical_name_ko AS matched, 'canonical' AS src,
                   LENGTH(canonical_name_ko) AS name_len
            FROM supplement_map
            WHERE CHAR_LENGTH(canonical_name_ko) >= 3
              AND (canonical_name_ko LIKE %s OR raw_name LIKE %s OR %s LIKE CONCAT('%', canonical_name_ko, '%'))
            UNION ALL
            SELECT sm.supplement_id, sm.canonical_name_ko, sm.canonical_name_en,
                   sa.alias AS matched, 'alias' AS src,
                   LENGTH(sa.alias) AS name_len
            FROM supplement_aliases sa
            JOIN supplement_map sm ON sa.supplement_id = sm.supplement_id
            WHERE CHAR_LENGTH(sa.alias) >= 3
              AND (sa.alias LIKE %s OR %s LIKE CONCAT('%', sa.alias, '%'))
            ORDER BY name_len ASC
            LIMIT 1
            """,
            (f"%{clean}%", f"%{clean}%", clean, f"%{clean}%", clean),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                supplement_name_ko=row["supplement_name_ko"],
                supplement_name_en=row["supplement_name_en"],
                matched_alias=row["matched"],
                match_type="partial",
            )

        return None
    finally:
        cursor.close()
        conn.close()
