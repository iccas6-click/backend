"""
입력된 약물명을 canonical_drug_entities의 canonical drug로 해석하는 서비스.

우선순위:
1. canonical_drug_entities.canonical_drug_name_ko 정확 일치
2. canonical_drug_entities.canonical_drug_name_en 정확 일치
3. drug_aliases.alias_name_normalized 정확 일치
4. 위 세 컬럼에 대한 LIKE 부분 일치 (가장 짧은 이름 우선)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.db.connection import get_conn


@dataclass
class ResolvedDrug:
    canonical_drug_id: str
    canonical_drug_name_ko: str
    canonical_drug_name_en: Optional[str]
    matched_alias: str
    match_type: str  # exact_ko | exact_en | exact_alias | partial


def resolve_drug(name: str) -> Optional[ResolvedDrug]:
    """약물명으로 canonical_drug_entities 엔트리를 찾아 반환. 없으면 None."""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1) canonical_drug_name_ko 정확 일치
        cursor.execute(
            """
            SELECT canonical_drug_id, canonical_drug_name_ko, canonical_drug_name_en
            FROM canonical_drug_entities
            WHERE canonical_drug_name_ko = %s
            LIMIT 1
            """,
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedDrug(
                canonical_drug_id=row["canonical_drug_id"],
                canonical_drug_name_ko=row["canonical_drug_name_ko"],
                canonical_drug_name_en=row["canonical_drug_name_en"],
                matched_alias=name,
                match_type="exact_ko",
            )

        # 2) canonical_drug_name_en 정확 일치
        cursor.execute(
            """
            SELECT canonical_drug_id, canonical_drug_name_ko, canonical_drug_name_en
            FROM canonical_drug_entities
            WHERE canonical_drug_name_en = %s
            LIMIT 1
            """,
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedDrug(
                canonical_drug_id=row["canonical_drug_id"],
                canonical_drug_name_ko=row["canonical_drug_name_ko"],
                canonical_drug_name_en=row["canonical_drug_name_en"],
                matched_alias=name,
                match_type="exact_en",
            )

        # 3) drug_aliases.alias_name 정확 일치
        cursor.execute(
            """
            SELECT cde.canonical_drug_id,
                   cde.canonical_drug_name_ko,
                   cde.canonical_drug_name_en,
                   da.alias_name
            FROM drug_aliases da
            JOIN canonical_drug_entities cde
              ON da.canonical_drug_id = cde.canonical_drug_id
            WHERE da.alias_name = %s
            LIMIT 1
            """,
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedDrug(
                canonical_drug_id=row["canonical_drug_id"],
                canonical_drug_name_ko=row["canonical_drug_name_ko"],
                canonical_drug_name_en=row["canonical_drug_name_en"],
                matched_alias=row["alias_name"],
                match_type="exact_alias",
            )

        # 4) 부분 일치 — canonical name 또는 alias, 가장 짧은 이름 우선
        cursor.execute(
            """
            SELECT cde.canonical_drug_id,
                   cde.canonical_drug_name_ko,
                   cde.canonical_drug_name_en,
                   cde.canonical_drug_name_ko AS matched,
                   LENGTH(cde.canonical_drug_name_ko) AS name_len
            FROM canonical_drug_entities cde
            WHERE cde.canonical_drug_name_ko LIKE %s
               OR cde.canonical_drug_name_en LIKE %s

            UNION

            SELECT cde.canonical_drug_id,
                   cde.canonical_drug_name_ko,
                   cde.canonical_drug_name_en,
                   da.alias_name AS matched,
                   LENGTH(da.alias_name) AS name_len
            FROM drug_aliases da
            JOIN canonical_drug_entities cde
              ON da.canonical_drug_id = cde.canonical_drug_id
            WHERE da.alias_name LIKE %s

            ORDER BY name_len ASC
            LIMIT 1
            """,
            (f"%{name}%", f"%{name}%", f"%{name}%"),
        )
        row = cursor.fetchone()
        if row:
            return ResolvedDrug(
                canonical_drug_id=row["canonical_drug_id"],
                canonical_drug_name_ko=row["canonical_drug_name_ko"],
                canonical_drug_name_en=row["canonical_drug_name_en"],
                matched_alias=row["matched"],
                match_type="partial",
            )

        return None
    finally:
        cursor.close()
        conn.close()
