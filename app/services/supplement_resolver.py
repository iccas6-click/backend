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
    """성분명으로 supplement_entities 엔트리를 찾아 반환. 없으면 None."""
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
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedSupplement(
                supplement_id=row["supplement_id"],
                supplement_name_ko=row["supplement_name_ko"],
                supplement_name_en=row["supplement_name_en"],
                matched_alias=name,
                match_type="exact_ko",
            )

        # 2) supplement_name_en 정확 일치
        cursor.execute(
            """
            SELECT supplement_id, supplement_name_ko, supplement_name_en
            FROM supplement_entities
            WHERE supplement_name_en = %s
            LIMIT 1
            """,
            (name,),
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

        # 3) 부분 일치 — 가장 짧은 이름 우선
        cursor.execute(
            """
            SELECT supplement_id, supplement_name_ko, supplement_name_en,
                   supplement_name_ko AS matched,
                   LENGTH(supplement_name_ko) AS name_len
            FROM supplement_entities
            WHERE supplement_name_ko LIKE %s OR supplement_name_en LIKE %s
            ORDER BY name_len ASC
            LIMIT 1
            """,
            (f"%{name}%", f"%{name}%"),
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
