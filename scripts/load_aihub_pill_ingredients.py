"""
AIHub 기반 알약 1000종 제품명-성분 CSV를 백엔드 매칭 DB에 적재한다.

CSV 형식:
    제품명,성분명,코드
    제품 A,성분1|성분2,K-000001

역할:
1. canonical_drug_entities에 성분 canonical row를 보강한다.
2. pill_product_ingredients에 제품명 -> 성분들 매핑을 저장한다.
3. 분석 API는 이 테이블을 이용해 제품명이 들어와도 성분 조합으로 확장한다.

사용법:
    python scripts/load_aihub_pill_ingredients.py /path/to/aihub_1000_pill_ingredients_slim.csv
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

SOURCE_NAME = "AIHub pill 1000 product ingredient slim CSV"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pill_product_ingredients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_code VARCHAR(50),
    product_name VARCHAR(255) NOT NULL,
    normalized_product_name VARCHAR(255) NOT NULL,
    ingredient_name VARCHAR(255) NOT NULL,
    normalized_ingredient_name VARCHAR(255) NOT NULL,
    canonical_drug_id VARCHAR(50) NOT NULL,
    source_name VARCHAR(255),
    UNIQUE KEY uq_product_ingredient (product_code, normalized_product_name, normalized_ingredient_name),
    KEY idx_pill_product_norm (normalized_product_name),
    KEY idx_pill_ingredient_norm (normalized_ingredient_name),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""


def normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", value.strip().lower())


def canonical_id_for_ingredient(ingredient_name: str) -> str:
    digest = hashlib.sha1(normalize_name(ingredient_name).encode("utf-8")).hexdigest()[:16].upper()
    return f"AIHUB_ING_{digest}"


def ingredient_aliases(name: str) -> list[str]:
    aliases = {name.strip()}
    compact = name.strip()
    salt_suffixes = [
        "염산염수화물",
        "염산염",
        "브롬화수소산염수화물",
        "브롬화수소산염",
        "말레산염",
        "베실산염이수화물",
        "베실산염",
        "수화물",
        "프로판디올수화물",
        "나트륨삼수화물",
        "나트륨",
        "칼륨",
        "칼슘수화물",
        "칼슘",
    ]
    for suffix in salt_suffixes:
        if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
            aliases.add(compact[: -len(suffix)])
    return sorted(aliases)


def find_existing_drug_id(cursor, ingredient_name: str) -> str | None:
    aliases = ingredient_aliases(ingredient_name)
    normalized_aliases = [normalize_name(alias) for alias in aliases]

    for alias in aliases:
        cursor.execute(
            """
            SELECT canonical_drug_id
            FROM canonical_drug_entities
            WHERE canonical_name_ko = %s
               OR LOWER(canonical_name_en) = LOWER(%s)
               OR raw_aliases LIKE %s
            LIMIT 1
            """,
            (alias, alias, f"%{alias}%"),
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    for normalized in normalized_aliases:
        cursor.execute(
            """
            SELECT canonical_drug_id
            FROM canonical_drug_entities
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(canonical_name_ko), ' ', ''), '-', ''), '_', ''), '/', ''), '·', '') = %s
               OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(canonical_name_en), ' ', ''), '-', ''), '_', ''), '/', ''), '·', '') = %s
               OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(raw_aliases), ' ', ''), '-', ''), '_', ''), '/', ''), '·', '') LIKE %s
            LIMIT 1
            """,
            (normalized, normalized, f"%{normalized}%"),
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    return None


def upsert_drug_entity(cursor, ingredient_name: str) -> str:
    existing_id = find_existing_drug_id(cursor, ingredient_name)
    if existing_id:
        return existing_id

    drug_id = canonical_id_for_ingredient(ingredient_name)
    aliases = ingredient_aliases(ingredient_name)
    cursor.execute(
        """
        INSERT INTO canonical_drug_entities (
            canonical_drug_id, entity_level, canonical_name_ko, canonical_name_en,
            alias_count, raw_aliases, rxcui, atc_code, unii, kr_ingredient_code,
            external_id_status, mapping_status, verification_source_name,
            verification_source_url, notes
        )
        VALUES (%s, 'INGREDIENT', %s, NULL, %s, %s, NULL, NULL, NULL, NULL,
                'NOT_VERIFIED', 'AIHUB_PRODUCT_DICTIONARY', %s, NULL,
                'AIHub pill recognition 1000종 제품-성분 CSV에서 보강')
        ON DUPLICATE KEY UPDATE
            canonical_name_ko = VALUES(canonical_name_ko),
            alias_count = VALUES(alias_count),
            raw_aliases = VALUES(raw_aliases),
            mapping_status = VALUES(mapping_status),
            verification_source_name = VALUES(verification_source_name),
            notes = VALUES(notes)
        """,
        (drug_id, ingredient_name, len(aliases), ", ".join(aliases), SOURCE_NAME),
    )
    return drug_id


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"제품명", "성분명", "코드"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV 컬럼이 맞지 않습니다. 필요: {sorted(required)}, 실제: {reader.fieldnames}")
        return [row for row in reader if row.get("제품명") and row.get("성분명")]


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("AIHUB_PILL_INGREDIENT_CSV", ""))
    if not csv_path.exists():
        raise SystemExit(f"CSV 파일 없음: {csv_path}")

    rows = read_rows(csv_path)
    conn = get_conn()
    cursor = conn.cursor()

    product_count = 0
    ingredient_links = 0
    ingredient_ids: set[str] = set()

    try:
        cursor.execute(CREATE_TABLE_SQL)
        cursor.execute("DELETE FROM pill_product_ingredients WHERE source_name = %s", (SOURCE_NAME,))

        for row in rows:
            product_name = row["제품명"].strip()
            product_code = row["코드"].strip()
            ingredients = [
                item.strip()
                for item in re.split(r"[|·ㆍ]", row["성분명"])
                if item.strip()
            ]
            if not product_name or not ingredients:
                continue

            product_count += 1
            normalized_product = normalize_name(product_name)

            for ingredient in ingredients:
                drug_id = upsert_drug_entity(cursor, ingredient)
                ingredient_ids.add(drug_id)
                cursor.execute(
                    """
                    INSERT INTO pill_product_ingredients (
                        product_code, product_name, normalized_product_name,
                        ingredient_name, normalized_ingredient_name,
                        canonical_drug_id, source_name
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        product_name = VALUES(product_name),
                        ingredient_name = VALUES(ingredient_name),
                        canonical_drug_id = VALUES(canonical_drug_id),
                        source_name = VALUES(source_name)
                    """,
                    (
                        product_code,
                        product_name,
                        normalized_product,
                        ingredient,
                        normalize_name(ingredient),
                        drug_id,
                        SOURCE_NAME,
                    ),
                )
                ingredient_links += 1

        conn.commit()
        print(
            "완료: "
            f"제품 {product_count}개, 제품-성분 링크 {ingredient_links}개, "
            f"canonical 성분 {len(ingredient_ids)}개"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
