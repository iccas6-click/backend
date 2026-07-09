"""
CSV 파일을 MySQL DB에 적재하는 스크립트.

소스: click/drug-supplement schema v2/
대상: click/backend DB (init.sql 스키마 기준 8개 테이블)

사용법:
  python scripts/load_interaction_data.py

옵션:
  --processed-dir PATH   CSV 폴더 경로 (기본값: 스크립트 내 상수)
  --skip-supplement-info supplement_info / supplement_product_markers 적재 생략
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import List

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# CSV 폴더 경로 (drug-supplement schema v2)
DEFAULT_PROCESSED_DIR = Path(
    r"C:\Users\mercu\Documents\kangmin\click\drug-supplement schema v2"
)

# supplement_info는 행 수가 많으므로 배치 단위로 적재
BATCH_SIZE = 1000


def get_conn():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        database=os.environ["MYSQL_DATABASE"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        charset="utf8mb4",
    )


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def none_if_empty(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def load_canonical_drug_entities(cursor, rows: List[dict]) -> None:
    print(f"  canonical_drug_entities: {len(rows)}행 적재 중...")
    cursor.execute("DELETE FROM canonical_drug_entities")
    sql = """
        INSERT INTO canonical_drug_entities
            (canonical_drug_id, canonical_drug_name_ko, canonical_drug_name_en)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            canonical_drug_name_ko = VALUES(canonical_drug_name_ko),
            canonical_drug_name_en = VALUES(canonical_drug_name_en)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("canonical_drug_id")),
            none_if_empty(row.get("canonical_drug_name_ko")),
            none_if_empty(row.get("canonical_drug_name_en")),
        ))


def load_pill_products(cursor, rows: List[dict]) -> None:
    print(f"  pill_products: {len(rows)}행 적재 중...")
    cursor.execute("DELETE FROM pill_product_ingredients")
    cursor.execute("DELETE FROM pill_products")
    sql = """
        INSERT INTO pill_products
            (pill_product_id, product_name, product_name_normalized)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            product_name = VALUES(product_name),
            product_name_normalized = VALUES(product_name_normalized)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("pill_product_id")),
            none_if_empty(row.get("product_name")),
            none_if_empty(row.get("product_name_normalized")),
        ))


def load_drug_aliases(cursor, rows: List[dict]) -> None:
    print(f"  drug_aliases: {len(rows)}행 적재 중...")
    cursor.execute("DELETE FROM drug_aliases")
    sql = """
        INSERT INTO drug_aliases
            (drug_alias_id, alias_name, alias_name_normalized, canonical_drug_id)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            alias_name = VALUES(alias_name),
            alias_name_normalized = VALUES(alias_name_normalized),
            canonical_drug_id = VALUES(canonical_drug_id)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("drug_alias_id")),
            none_if_empty(row.get("alias_name")),
            none_if_empty(row.get("alias_name_normalized")),
            none_if_empty(row.get("canonical_drug_id")),
        ))


def load_pill_product_ingredients(cursor, rows: List[dict]) -> None:
    print(f"  pill_product_ingredients: {len(rows)}행 적재 중...")
    # pill_products 삭제 시 CASCADE로 함께 지워지므로 여기선 INSERT만
    sql = """
        INSERT IGNORE INTO pill_product_ingredients
            (pill_product_id, ingredient_name, ingredient_name_normalized, canonical_drug_id)
        VALUES (%s, %s, %s, %s)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("pill_product_id")),
            none_if_empty(row.get("ingredient_name")),
            none_if_empty(row.get("ingredient_name_normalized")),
            none_if_empty(row.get("canonical_drug_id")),
        ))


def load_supplement_entities(cursor, rows: List[dict]) -> None:
    print(f"  supplement_entities: {len(rows)}행 적재 중...")
    cursor.execute("DELETE FROM supplement_entities")
    sql = """
        INSERT INTO supplement_entities
            (supplement_id, supplement_name_ko, supplement_name_en)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            supplement_name_ko = VALUES(supplement_name_ko),
            supplement_name_en = VALUES(supplement_name_en)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("supplement_id")),
            none_if_empty(row.get("supplement_name_ko")),
            none_if_empty(row.get("supplement_name_en")),
        ))


def load_supplement_info(cursor, rows: List[dict]) -> None:
    print(f"  supplement_info: {len(rows)}행 적재 중 (배치={BATCH_SIZE})...")
    cursor.execute("DELETE FROM supplement_product_markers")
    cursor.execute("DELETE FROM supplement_info")
    sql = """
        INSERT INTO supplement_info
            (id, sttemnt_no, product, product_normalized, entrps, regist_dt,
             distb_pd, sungsang, srv_use, prsrv_pd, intake_hint1,
             main_fnctn, base_standard, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            product = VALUES(product),
            product_normalized = VALUES(product_normalized)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cursor.executemany(sql, [
            (
                none_if_empty(row.get("id")),
                none_if_empty(row.get("sttemnt_no")),
                none_if_empty(row.get("product")),
                none_if_empty(row.get("product_normalized")),
                none_if_empty(row.get("entrps")),
                none_if_empty(row.get("regist_dt")),
                none_if_empty(row.get("distb_pd")),
                none_if_empty(row.get("sungsang")),
                none_if_empty(row.get("srv_use")),
                none_if_empty(row.get("prsrv_pd")),
                none_if_empty(row.get("intake_hint1")),
                none_if_empty(row.get("main_fnctn")),
                none_if_empty(row.get("base_standard")),
                none_if_empty(row.get("created_at")),
            )
            for row in batch
        ])
        print(f"    {min(i + BATCH_SIZE, len(rows))}/{len(rows)}행 완료")


def load_supplement_product_markers(cursor, rows: List[dict]) -> None:
    print(f"  supplement_product_markers: {len(rows)}행 적재 중 (배치={BATCH_SIZE})...")
    # supplement_info 삭제 시 CASCADE로 함께 지워지므로 여기선 INSERT만
    sql = """
        INSERT IGNORE INTO supplement_product_markers
            (supplement_info_id, marker_text, marker_text_normalized,
             marker_source_column, marker_type, supplement_id, mapping_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cursor.executemany(sql, [
            (
                none_if_empty(row.get("supplement_info_id")),
                none_if_empty(row.get("marker_text")),
                none_if_empty(row.get("marker_text_normalized")),
                none_if_empty(row.get("marker_source_column")),
                none_if_empty(row.get("marker_type")),
                none_if_empty(row.get("supplement_id")),
                none_if_empty(row.get("mapping_status")),
            )
            for row in batch
        ])
        print(f"    {min(i + BATCH_SIZE, len(rows))}/{len(rows)}행 완료")


def load_source_claims(cursor, rows: List[dict]) -> None:
    print(f"  source_claims: {len(rows)}행 적재 중...")
    cursor.execute("DELETE FROM standardized_interactions")
    cursor.execute("DELETE FROM source_claims")
    sql = """
        INSERT INTO source_claims
            (source_claim_id, source_name, source_url,
             drug_text_original, supplement_text_original, claim_text_original)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            claim_text_original = VALUES(claim_text_original)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("source_claim_id")),
            none_if_empty(row.get("source_name")),
            none_if_empty(row.get("source_url")),
            none_if_empty(row.get("drug_text_original")),
            none_if_empty(row.get("supplement_text_original")),
            none_if_empty(row.get("claim_text_original")),
        ))


def load_standardized_interactions(cursor, rows: List[dict]) -> None:
    print(f"  standardized_interactions: {len(rows)}행 적재 중...")
    sql = """
        INSERT IGNORE INTO standardized_interactions
            (interaction_id, canonical_drug_id, supplement_id, source_claim_id)
        VALUES (%s, %s, %s, %s)
    """
    for row in rows:
        cursor.execute(sql, (
            none_if_empty(row.get("interaction_id")),
            none_if_empty(row.get("canonical_drug_id")),
            none_if_empty(row.get("supplement_id")),
            none_if_empty(row.get("source_claim_id")),
        ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="processed CSV 폴더 경로",
    )
    parser.add_argument(
        "--skip-supplement-info",
        action="store_true",
        help="supplement_info / supplement_product_markers 적재 생략 (빠른 테스트용)",
    )
    args = parser.parse_args()

    d: Path = args.processed_dir
    if not d.exists():
        print(f"[ERROR] processed 폴더를 찾을 수 없습니다: {d}")
        raise SystemExit(1)

    # FK 순서를 지켜서 CSV 로드
    # 1) FK 없는 테이블
    canonical_rows = read_csv(d / "canonical_drug_entities.csv")
    pill_rows = read_csv(d / "pill_products.csv")
    supplement_entity_rows = read_csv(d / "supplement_entities.csv")
    source_claim_rows = read_csv(d / "source_claims.csv")

    # 2) FK 있는 테이블
    alias_rows = read_csv(d / "drug_aliases.csv")
    pill_ingredient_rows = read_csv(d / "pill_product_ingredients.csv")
    interaction_rows = read_csv(d / "standardized_interactions.csv")

    supplement_info_rows = []
    marker_rows = []
    has_supplement_info = (d / "supplement_info.csv").exists() and (d / "supplement_product_markers.csv").exists()
    if not args.skip_supplement_info and has_supplement_info:
        supplement_info_rows = read_csv(d / "supplement_info.csv")
        marker_rows = read_csv(d / "supplement_product_markers.csv")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    try:
        print("\n[1/9] canonical_drug_entities")
        load_canonical_drug_entities(cursor, canonical_rows)
        conn.commit()

        print("[2/9] pill_products")
        load_pill_products(cursor, pill_rows)
        conn.commit()

        print("[3/9] drug_aliases")
        load_drug_aliases(cursor, alias_rows)
        conn.commit()

        print("[4/9] pill_product_ingredients")
        load_pill_product_ingredients(cursor, pill_ingredient_rows)
        conn.commit()

        print("[5/9] supplement_entities")
        load_supplement_entities(cursor, supplement_entity_rows)
        conn.commit()

        if not args.skip_supplement_info and has_supplement_info:
            print("[6/9] supplement_info")
            load_supplement_info(cursor, supplement_info_rows)
            conn.commit()

            print("[7/9] supplement_product_markers")
            load_supplement_product_markers(cursor, marker_rows)
            conn.commit()
        else:
            reason = "파일 없음" if not has_supplement_info else "생략 옵션"
            print(f"[6/9] supplement_info — 건너뜀 ({reason})")
            print(f"[7/9] supplement_product_markers — 건너뜀 ({reason})")

        print("[8/9] source_claims")
        load_source_claims(cursor, source_claim_rows)
        conn.commit()

        print("[9/9] standardized_interactions")
        load_standardized_interactions(cursor, interaction_rows)
        conn.commit()

        print("\n전체 데이터 적재 완료")
        print(f"  canonical_drug_entities : {len(canonical_rows)}행")
        print(f"  pill_products           : {len(pill_rows)}행")
        print(f"  drug_aliases            : {len(alias_rows)}행")
        print(f"  pill_product_ingredients: {len(pill_ingredient_rows)}행")
        print(f"  supplement_entities     : {len(supplement_entity_rows)}행")
        if not args.skip_supplement_info and has_supplement_info:
            print(f"  supplement_info         : {len(supplement_info_rows)}행")
            print(f"  supplement_product_markers: {len(marker_rows)}행")
        print(f"  source_claims           : {len(source_claim_rows)}행")
        print(f"  standardized_interactions: {len(interaction_rows)}행")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 적재 실패: {e}")
        raise SystemExit(1)
    finally:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
