"""
Excel 상호작용 데이터를 MySQL DB에 적재하는 스크립트.
사용법: python scripts/load_interaction_data.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

EXCEL_PATH = Path("data/source/drug_supplement_interactions_standardized_v0.21_release_candidate.xlsx")


def get_conn():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        database=os.environ["MYSQL_DATABASE"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        charset="utf8mb4",
    )


def normalize(value) -> str | None:
    if pd.isna(value):
        return None
    return str(value).strip() or None


def load_supplement_map(cursor, df: pd.DataFrame):
    print(f"supplement_map 적재 중... ({len(df)}행)")
    cursor.execute("DELETE FROM supplement_map")
    for _, row in df.iterrows():
        cursor.execute(
            """
            INSERT INTO supplement_map
            (supplement_id, raw_name, canonical_name_ko, canonical_name_en,
             scientific_name, entity_type, mapping_status, mapping_basis,
             source_name, source_url, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                normalize(row.get("supplement_id")),
                normalize(row.get("raw_name")),
                normalize(row.get("canonical_name_ko")),
                normalize(row.get("canonical_name_en")),
                normalize(row.get("scientific_name")),
                normalize(row.get("entity_type")),
                normalize(row.get("mapping_status")),
                normalize(row.get("mapping_basis")),
                normalize(row.get("source_name")),
                normalize(row.get("source_url")),
                normalize(row.get("notes")),
            ),
        )
    print("supplement_map 완료")


def load_canonical_drug_entities(cursor, df: pd.DataFrame):
    print(f"canonical_drug_entities 적재 중... ({len(df)}행)")
    cursor.execute("DELETE FROM canonical_drug_entities")
    for _, row in df.iterrows():
        cursor.execute(
            """
            INSERT INTO canonical_drug_entities
            (canonical_drug_id, entity_level, canonical_name_ko, canonical_name_en,
             alias_count, raw_aliases, rxcui, atc_code, unii, kr_ingredient_code,
             external_id_status, mapping_status, verification_source_name,
             verification_source_url, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                normalize(row.get("canonical_drug_id")),
                normalize(row.get("entity_level")),
                normalize(row.get("canonical_name_ko")),
                normalize(row.get("canonical_name_en")),
                int(row["alias_count"]) if pd.notna(row.get("alias_count")) else None,
                normalize(row.get("raw_aliases")),
                normalize(row.get("rxcui")),
                normalize(row.get("atc_code")),
                normalize(row.get("unii")),
                normalize(row.get("kr_ingredient_code")),
                normalize(row.get("external_id_status")),
                normalize(row.get("mapping_status")),
                normalize(row.get("verification_source_name")),
                normalize(row.get("verification_source_url")),
                normalize(row.get("notes")),
            ),
        )
    print("canonical_drug_entities 완료")


def load_standardized_interactions(cursor, df: pd.DataFrame):
    print(f"standardized_interactions 적재 중... ({len(df)}행)")
    cursor.execute("DELETE FROM standardized_interactions")
    for _, row in df.iterrows():
        cursor.execute(
            """
            INSERT INTO standardized_interactions
            (claim_id, raw_id, supplement_name_raw, supplement_id,
             supplement_canonical_ko, supplement_canonical_en,
             drug_name_raw, drug_alias_id, canonical_drug_id,
             drug_canonical_ko, drug_canonical_en, entity_level,
             interaction_target_group_raw, drug_category_raw,
             interaction_text_raw, source_name, source_record_id, source_url,
             source_review_status, supplement_mapping_status,
             drug_mapping_status, external_id_status, overall_review_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                normalize(row.get("claim_id")),
                normalize(row.get("raw_id")),
                normalize(row.get("supplement_name_raw")),
                normalize(row.get("supplement_id")),
                normalize(row.get("supplement_canonical_ko")),
                normalize(row.get("supplement_canonical_en")),
                normalize(row.get("drug_name_raw")),
                normalize(row.get("drug_alias_id")),
                normalize(row.get("canonical_drug_id")),
                normalize(row.get("drug_canonical_ko")),
                normalize(row.get("drug_canonical_en")),
                normalize(row.get("entity_level")),
                normalize(row.get("interaction_target_group_raw")),
                normalize(row.get("drug_category_raw")),
                normalize(row.get("interaction_text_raw")),
                normalize(row.get("source_name")),
                normalize(row.get("source_record_id")),
                normalize(row.get("source_url")),
                normalize(row.get("source_review_status")),
                normalize(row.get("supplement_mapping_status")),
                normalize(row.get("drug_mapping_status")),
                normalize(row.get("external_id_status")),
                normalize(row.get("overall_review_status")),
            ),
        )
    print("standardized_interactions 완료")


def load_raw_interactions(cursor, df: pd.DataFrame):
    print(f"raw_interactions 적재 중... ({len(df)}행)")
    cursor.execute("DELETE FROM raw_interactions")
    for _, row in df.iterrows():
        cursor.execute(
            """
            INSERT INTO raw_interactions
            (raw_id, supplement_name_raw, drug_name_raw,
             interaction_target_group_raw, drug_category_raw,
             interaction_text_raw, severity_raw, recommendation_raw,
             evidence_text_raw, source_name, source_url, source_record_id,
             retrieved_date, review_status, collector, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                normalize(row.get("raw_id")),
                normalize(row.get("supplement_name_raw")),
                normalize(row.get("drug_name_raw")),
                normalize(row.get("interaction_target_group_raw")),
                normalize(row.get("drug_category_raw")),
                normalize(row.get("interaction_text_raw")),
                normalize(row.get("severity_raw")),
                normalize(row.get("recommendation_raw")),
                normalize(row.get("evidence_text_raw")),
                normalize(row.get("source_name")),
                normalize(row.get("source_url")),
                normalize(row.get("source_record_id")),
                normalize(row.get("retrieved_date")),
                normalize(row.get("review_status")),
                normalize(row.get("collector")),
                normalize(row.get("notes")),
            ),
        )
    print("raw_interactions 완료")


def main():
    if not EXCEL_PATH.exists():
        print(f"파일 없음: {EXCEL_PATH}")
        raise SystemExit(1)

    print("엑셀 로드 중...")
    sheets = pd.read_excel(EXCEL_PATH, sheet_name=None, dtype=object, engine="openpyxl")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SET FOREIGN_KEY_CHECKS=0")

    try:
        load_supplement_map(cursor, sheets["supplement_map"])
        load_canonical_drug_entities(cursor, sheets["canonical_drug_entities"])
        load_raw_interactions(cursor, sheets["raw_interactions"])
        load_standardized_interactions(cursor, sheets["standardized_interactions"])
        conn.commit()
        print("\n전체 데이터 적재 완료")
    except Exception as e:
        conn.rollback()
        print(f"오류: {e}")
        raise SystemExit(1)
    finally:
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
