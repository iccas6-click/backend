"""Import the v0.22 interaction workbook into additive v2 tables.

The existing tables are left intact and continue to work as fallback data.
This importer creates a v2 namespace that can become the primary matching
surface for prescription-drug ingredients, supplement label aliases, and
standardized interaction claims.

Usage:
    python scripts/import_v022_interaction_schema.py --replace
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.connection import get_conn

DEFAULT_WORKBOOK = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "source"
    / "drug_supplement_interactions_standardized_v0.22_prototype.xlsx"
)

SHEET_TABLES = {
    "canonical_drug_entities": "v2_canonical_drug_entities",
    "standardized_interactions": "v2_standardized_interactions",
    "supplement_map": "v2_supplement_map",
    "drug_entity_map": "v2_drug_entity_map",
    "claim_drug_expansion": "v2_claim_drug_expansion",
    "claim_target_map": "v2_claim_target_map",
    "official_supplement_ingredients": "v2_official_supplement_ingredients",
    "supplement_label_aliases": "v2_supplement_label_aliases",
    "supplement_official_ing_map": "v2_supplement_official_ing_map",
    "supplement_label_exclusions": "v2_supplement_label_exclusions",
    "interaction_scope_map": "v2_interaction_scope_map",
    "drug_class_membership": "v2_drug_class_membership",
    "drug_combination_components": "v2_drug_combination_components",
}

PRIMARY_KEYS = {
    "v2_canonical_drug_entities": "canonical_drug_id",
    "v2_standardized_interactions": "claim_id",
    "v2_supplement_map": "supplement_id",
    "v2_drug_entity_map": "drug_alias_id",
    "v2_claim_drug_expansion": "expansion_id",
    "v2_claim_target_map": "claim_target_id",
    "v2_official_supplement_ingredients": "official_ingredient_id",
    "v2_supplement_label_aliases": "label_alias_id",
    "v2_supplement_official_ing_map": "mapping_id",
    "v2_supplement_label_exclusions": "exclusion_id",
    "v2_interaction_scope_map": "scope_map_id",
    "v2_drug_class_membership": "membership_id",
}

PRIMARY_KEY_BY_TABLE = {
    **PRIMARY_KEYS,
    "v2_drug_combination_components": "combination_canonical_drug_id, component_canonical_drug_id",
}

TEXT_COLUMNS = {
    "raw_aliases",
    "verification_source_url",
    "notes",
    "interaction_target_group_raw",
    "interaction_text_raw",
    "source_url",
    "mapping_basis",
    "source_material_raw",
    "functional_marker_raw",
    "daily_intake_raw",
    "precaution_raw",
    "required_context_raw",
}


def normalize_key(value: str) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("밀리그램", "mg")
    value = value.replace("마이크로그램", "mcg")
    value = value.replace("그램", "g")
    value = value.replace("밀리리터", "ml")
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", value)


def clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "item"):
        value = value.item()
    return value


def column_type(column: str) -> str:
    if column in TEXT_COLUMNS or column.endswith("_url") or column.endswith("_raw") or column.endswith("_text"):
        return "TEXT"
    if column in {"alias_count"}:
        return "INT"
    if column in {"standalone_match_allowed", "human_followup_required"}:
        return "TINYINT(1)"
    return "VARCHAR(255)"


def create_sheet_table(cursor, table: str, columns: list[str]) -> None:
    definitions = []
    for column in columns:
        definitions.append(f"`{column}` {column_type(column)}")
    pk = PRIMARY_KEY_BY_TABLE.get(table)
    if pk:
        definitions.append(f"PRIMARY KEY ({', '.join(f'`{part.strip()}`' for part in pk.split(','))})")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS `{table}` (
            {", ".join(definitions)}
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )


def add_indexes(cursor) -> None:
    indexes = [
        ("v2_canonical_drug_entities", "idx_v2_drug_ko", "canonical_name_ko"),
        ("v2_canonical_drug_entities", "idx_v2_drug_en", "canonical_name_en"),
        ("v2_standardized_interactions", "idx_v2_std_pair", "supplement_id, canonical_drug_id"),
        ("v2_standardized_interactions", "idx_v2_std_supp", "supplement_id"),
        ("v2_supplement_label_aliases", "idx_v2_supp_alias_norm", "alias_text_normalized"),
        ("v2_supplement_label_aliases", "idx_v2_supp_alias_ing", "official_ingredient_id"),
        ("v2_interaction_scope_map", "idx_v2_scope_ing", "official_ingredient_id"),
        ("v2_interaction_scope_map", "idx_v2_scope_supp", "interaction_supplement_id"),
        ("v2_drug_class_membership", "idx_v2_class_member", "member_canonical_drug_id"),
        ("v2_drug_class_membership", "idx_v2_class_parent", "class_canonical_drug_id"),
        ("v2_drug_ingredient_aliases", "idx_v2_drug_alias_norm", "alias_normalized"),
        ("v2_drug_ingredient_aliases", "idx_v2_drug_alias_drug", "canonical_drug_id"),
    ]
    for table, index_name, columns in indexes:
        try:
            cursor.execute(f"CREATE INDEX `{index_name}` ON `{table}` ({columns})")
        except Exception as exc:
            if getattr(exc, "errno", None) != 1061:
                raise


def upsert_dataframe(cursor, table: str, df: pd.DataFrame) -> int:
    columns = [str(column) for column in df.columns]
    create_sheet_table(cursor, table, columns)
    if df.empty:
        return 0

    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(f"`{column}`" for column in columns)
    pk_columns = [part.strip() for part in PRIMARY_KEY_BY_TABLE.get(table, "").split(",") if part.strip()]
    update_columns = [column for column in columns if column not in pk_columns]
    update_sql = ", ".join(f"`{column}` = VALUES(`{column}`)" for column in update_columns)
    sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})"
    if update_sql:
        sql += f" ON DUPLICATE KEY UPDATE {update_sql}"

    rows = [tuple(clean_value(value) for value in row) for row in df.itertuples(index=False, name=None)]
    cursor.executemany(sql, rows)
    return len(rows)


def create_alias_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS v2_drug_ingredient_aliases (
            alias_id INT AUTO_INCREMENT PRIMARY KEY,
            canonical_drug_id VARCHAR(50) NOT NULL,
            alias_text VARCHAR(255) NOT NULL,
            alias_normalized VARCHAR(255) NOT NULL,
            alias_type VARCHAR(50) NOT NULL,
            source_name VARCHAR(255),
            UNIQUE KEY uq_v2_drug_alias (canonical_drug_id, alias_normalized),
            KEY idx_v2_drug_alias_norm (alias_normalized),
            KEY idx_v2_drug_alias_drug (canonical_drug_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )


def import_drug_aliases(cursor) -> int:
    cursor.execute("DELETE FROM v2_drug_ingredient_aliases")
    cursor.execute(
        """
        SELECT canonical_drug_id, canonical_name_ko, canonical_name_en, raw_aliases
        FROM v2_canonical_drug_entities
        """
    )
    rows = cursor.fetchall()
    inserted = 0
    for row in rows:
        aliases: list[tuple[str, str]] = []
        for alias_type, value in [
            ("canonical_ko", row.get("canonical_name_ko")),
            ("canonical_en", row.get("canonical_name_en")),
        ]:
            if value:
                aliases.append((alias_type, str(value)))
        raw_aliases = str(row.get("raw_aliases") or "")
        for alias in re.split(r"[,;/\n|]+|ㆍ|·", raw_aliases):
            clean = alias.strip()
            if clean:
                aliases.append(("raw_alias", clean))

        seen: set[str] = set()
        for alias_type, alias in aliases:
            normalized = normalize_key(alias)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cursor.execute(
                """
                INSERT INTO v2_drug_ingredient_aliases (
                    canonical_drug_id, alias_text, alias_normalized, alias_type, source_name
                )
                VALUES (%s, %s, %s, %s, 'v0.22 workbook')
                ON DUPLICATE KEY UPDATE
                    alias_text = VALUES(alias_text),
                    alias_type = VALUES(alias_type),
                    source_name = VALUES(source_name)
                """,
                (row["canonical_drug_id"], alias, normalized, alias_type),
            )
            inserted += 1
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--replace", action="store_true", help="Clear only v2 tables before importing.")
    args = parser.parse_args()

    workbook = Path(args.workbook)
    if not workbook.exists():
        raise SystemExit(f"Workbook not found: {workbook}")

    xl = pd.ExcelFile(workbook)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        if args.replace:
            for table in ["v2_drug_ingredient_aliases", *SHEET_TABLES.values()]:
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")

        imported: dict[str, int] = {}
        for sheet, table in SHEET_TABLES.items():
            if sheet not in xl.sheet_names:
                continue
            df = xl.parse(sheet)
            df = df.where(pd.notna(df), None)
            imported[table] = upsert_dataframe(cursor, table, df)

        create_alias_table(cursor)
        imported["v2_drug_ingredient_aliases"] = import_drug_aliases(cursor)
        add_indexes(cursor)
        conn.commit()

        for table, count in imported.items():
            print(f"{table}: {count}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
