"""
drug-supplement schema v3 CSV → Backend DB import

대상 테이블 (import 순서 준수):
  1. canonical_drug_entities
  2. supplement_entities
  3. source_claims
  4. drug_aliases
  5. standardized_interactions

실행:
  python scripts/import_v3_data.py --csv-dir "../drug-supplement schema v3"

환경변수 (.env):
  MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


def connect(env_path: Path) -> mysql.connector.MySQLConnection:
    load_dotenv(env_path)
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3307")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
    )


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def upsert(cursor, table: str, pk: str, cols: list[str], rows: list[dict]) -> int:
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    updates = ", ".join(f"{c} = VALUES({c})" for c in cols if c != pk)
    sql = f"""
        INSERT INTO {table} ({col_names})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}
    """
    data = [tuple(r[c] for c in cols) for r in rows]
    batch = 2000
    for i in range(0, len(data), batch):
        cursor.executemany(sql, data[i : i + batch])
    return len(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default="../drug-supplement schema v3")
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    env_path = Path(args.env)

    conn = connect(env_path)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        print("canonical_drug_entities import 중...")
        rows = load_csv(csv_dir / "canonical_drug_entities.csv")
        n = upsert(cursor, "canonical_drug_entities", "canonical_drug_id",
                   ["canonical_drug_id", "canonical_drug_name_ko", "canonical_drug_name_en"], rows)
        print(f"  {n}행 처리")

        print("supplement_entities import 중...")
        rows = load_csv(csv_dir / "supplement_entities.csv")
        n = upsert(cursor, "supplement_entities", "supplement_id",
                   ["supplement_id", "supplement_name_ko", "supplement_name_en"], rows)
        print(f"  {n}행 처리")

        print("source_claims import 중...")
        rows = load_csv(csv_dir / "source_claims.csv")
        n = upsert(cursor, "source_claims", "source_claim_id",
                   ["source_claim_id", "source_name", "source_url",
                    "drug_text_original", "supplement_text_original", "claim_text_original"], rows)
        print(f"  {n}행 처리")

        print("drug_aliases import 중...")
        rows = load_csv(csv_dir / "drug_aliases.csv")
        n = upsert(cursor, "drug_aliases", "drug_alias_id",
                   ["drug_alias_id", "alias_name", "alias_name_normalized", "canonical_drug_id"], rows)
        print(f"  {n}행 처리")

        print("standardized_interactions import 중...")
        rows = load_csv(csv_dir / "standardized_interactions.csv")
        n = upsert(cursor, "standardized_interactions", "interaction_id",
                   ["interaction_id", "canonical_drug_id", "supplement_id", "source_claim_id"], rows)
        print(f"  {n}행 처리")

        conn.commit()
        print("완료")
    except Exception as e:
        conn.rollback()
        print(f"오류 발생, 롤백: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
