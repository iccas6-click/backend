"""
AIHub 약 1000종 제품-성분 DB 검색 스크립트.

검색 대상:
    pill_product_ingredients

실행:
    python scripts/search_pill_ingredients.py
    python scripts/search_pill_ingredients.py 메트포르민
    python scripts/search_pill_ingredients.py --code K-029534
    python scripts/search_pill_ingredients.py --ingredient 아스피린
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn


def normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", value.strip().lower())


def table_exists(cursor) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = 'pill_product_ingredients'
        """
    )
    return bool(cursor.fetchone()["count"])


def summary(cursor) -> dict:
    cursor.execute(
        """
        SELECT COUNT(*) AS links,
               COUNT(DISTINCT product_code) AS products,
               COUNT(DISTINCT normalized_ingredient_name) AS ingredients,
               COUNT(DISTINCT canonical_drug_id) AS canonical_ingredients
        FROM pill_product_ingredients
        """
    )
    return cursor.fetchone()


def search(cursor, query: str, mode: str, limit: int) -> list[dict]:
    clean = query.strip()
    normalized = normalize_name(clean)

    if mode == "code":
        cursor.execute(
            """
            SELECT product_code, product_name, ingredient_name, canonical_drug_id
            FROM pill_product_ingredients
            WHERE product_code = %s
            ORDER BY product_name, ingredient_name
            LIMIT %s
            """,
            (clean, limit),
        )
        return cursor.fetchall()

    if mode == "ingredient":
        cursor.execute(
            """
            SELECT product_code, product_name, ingredient_name, canonical_drug_id
            FROM pill_product_ingredients
            WHERE ingredient_name LIKE %s
               OR normalized_ingredient_name LIKE %s
               OR canonical_drug_id = %s
            ORDER BY ingredient_name, product_name
            LIMIT %s
            """,
            (f"%{clean}%", f"%{normalized}%", clean, limit),
        )
        return cursor.fetchall()

    cursor.execute(
        """
        SELECT product_code, product_name, ingredient_name, canonical_drug_id
        FROM pill_product_ingredients
        WHERE product_name LIKE %s
           OR normalized_product_name LIKE %s
           OR ingredient_name LIKE %s
           OR normalized_ingredient_name LIKE %s
           OR product_code = %s
           OR canonical_drug_id = %s
        ORDER BY
            CASE
                WHEN product_code = %s THEN 1
                WHEN normalized_product_name = %s THEN 2
                WHEN normalized_ingredient_name = %s THEN 3
                ELSE 4
            END,
            product_name,
            ingredient_name
        LIMIT %s
        """,
        (
            f"%{clean}%",
            f"%{normalized}%",
            f"%{clean}%",
            f"%{normalized}%",
            clean,
            clean,
            clean,
            normalized,
            normalized,
            limit,
        ),
    )
    return cursor.fetchall()


def print_rows(rows: list[dict]) -> None:
    if not rows:
        print("검색 결과 없음")
        return

    current_product: tuple[str | None, str | None] | None = None
    for row in rows:
        product_key = (row["product_code"], row["product_name"])
        if product_key != current_product:
            current_product = product_key
            print()
            print(f"[{row['product_code'] or '-'}] {row['product_name']}")
        print(f"  - {row['ingredient_name']} ({row['canonical_drug_id']})")
    print()


def interactive(cursor, limit: int) -> None:
    print("AIHub 약 1000종 제품-성분 DB 검색")
    print("검색어: 제품명/성분명/제품코드 입력, 종료: q")
    print("예: 메트포르민, 콤비글라이즈, K-029534")

    while True:
        try:
            raw = input("\n검색어> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in {"q", "quit", "exit"}:
            break
        print_rows(search(cursor, raw, "all", limit))


def main() -> None:
    parser = argparse.ArgumentParser(description="AIHub 약 1000종 제품-성분 DB 검색")
    parser.add_argument("query", nargs="?", help="제품명, 성분명, 제품코드, canonical_drug_id")
    parser.add_argument("--code", help="제품코드로 검색, 예: K-029534")
    parser.add_argument("--ingredient", help="성분명으로 검색, 예: 메트포르민")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        if not table_exists(cursor):
            raise SystemExit("pill_product_ingredients 테이블이 없습니다. 먼저 load_aihub_pill_ingredients.py를 실행하세요.")

        stats = summary(cursor)
        print(
            "현재 DB: "
            f"제품 {stats['products']}개, "
            f"제품-성분 링크 {stats['links']}개, "
            f"고유 성분명 {stats['ingredients']}개, "
            f"canonical 성분 {stats['canonical_ingredients']}개"
        )

        if args.code:
            print_rows(search(cursor, args.code, "code", args.limit))
        elif args.ingredient:
            print_rows(search(cursor, args.ingredient, "ingredient", args.limit))
        elif args.query:
            print_rows(search(cursor, args.query, "all", args.limit))
        else:
            interactive(cursor, args.limit)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
