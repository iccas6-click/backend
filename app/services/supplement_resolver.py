"""
입력된 성분명(또는 개별인정원료명)을 supplement_map의 canonical 성분으로 해석하는 서비스.

우선순위:
1. supplement_map.canonical_name_ko 정확 일치
2. supplement_map.raw_name 정확 일치
3. supplement_aliases.alias 정확 일치
4. 위 세 컬럼에 대한 LIKE 부분 일치 (가장 짧은 이름 우선)
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
    matched_alias: str        # 실제 매칭된 이름
    match_type: str           # exact_canonical / exact_raw / exact_alias / partial


def resolve_supplement(name: str) -> Optional[ResolvedSupplement]:
    """성분명으로 supplement_map 엔트리를 찾아 반환. 없으면 None."""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1) canonical_name_ko / raw_name 정확 일치
        cursor.execute(
            """
            SELECT supplement_id, canonical_name_ko, canonical_name_en, raw_name
            FROM supplement_map
            WHERE canonical_name_ko = %s OR raw_name = %s
            LIMIT 1
            """,
            (name, name),
        )
        row = cursor.fetchone()
        if row:
            match_type = "exact_canonical" if row["canonical_name_ko"] == name else "exact_raw"
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row["canonical_name_en"],
                matched_alias=name,
                match_type=match_type,
            )

        # 2) supplement_aliases 정확 일치
        cursor.execute(
            """
            SELECT sm.supplement_id, sm.canonical_name_ko, sm.canonical_name_en, sa.alias
            FROM supplement_aliases sa
            JOIN supplement_map sm ON sa.supplement_id = sm.supplement_id
            WHERE sa.alias = %s
            LIMIT 1
            """,
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row["canonical_name_en"],
                matched_alias=row["alias"],
                match_type="exact_alias",
            )

        # 3) 부분 일치 (canonical_name_ko, raw_name, alias) — 가장 짧은 이름 우선
        cursor.execute(
            """
            SELECT supplement_id, canonical_name_ko, canonical_name_en,
                   canonical_name_ko AS matched, 'canonical' AS src,
                   LENGTH(canonical_name_ko) AS name_len
            FROM supplement_map
            WHERE canonical_name_ko LIKE %s OR raw_name LIKE %s
            UNION ALL
            SELECT sm.supplement_id, sm.canonical_name_ko, sm.canonical_name_en,
                   sa.alias AS matched, 'alias' AS src,
                   LENGTH(sa.alias) AS name_len
            FROM supplement_aliases sa
            JOIN supplement_map sm ON sa.supplement_id = sm.supplement_id
            WHERE sa.alias LIKE %s
            ORDER BY name_len ASC
            LIMIT 1
            """,
            (f"%{name}%", f"%{name}%", f"%{name}%"),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                canonical_name_ko=row["canonical_name_ko"],
                canonical_name_en=row["canonical_name_en"],
                matched_alias=row["matched"],
                match_type="partial",
            )

        return None
    finally:
        cursor.close()
        conn.close()
