from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import mysql.connector


DEFAULT_CODEIT_DIR = Path("/home/gyu/pill/external/codeit10_pj1")


def main() -> None:
    load_dotenv(Path(".env"))
    codeit_dir = Path(os.getenv("CODEIT_PILL_PROJECT_DIR", str(DEFAULT_CODEIT_DIR))).expanduser()
    info_path = codeit_dir / "web" / "rtmdet_cnn_server" / "data" / "pill_info_master.json"
    if not info_path.exists():
        raise FileNotFoundError(f"codeit pill info not found: {info_path}")

    rows = load_codeit_rows(info_path)
    conn = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
    )
    conn.autocommit = False
    inserted_entities = 0
    inserted_mappings = 0
    reused_entities = 0
    try:
        cursor = conn.cursor(dictionary=True)
        for row in rows:
            product_name = clean_text(row.get("dl_name"))
            product_code = clean_text(row.get("item_seq"))
            if not product_name:
                continue
            for ingredient in extract_ingredients(row.get("material")):
                canonical_id, created = ensure_canonical_entity(cursor, ingredient)
                inserted_entities += int(created)
                reused_entities += int(not created)
                if ensure_product_mapping(
                    cursor,
                    product_code=product_code,
                    product_name=product_name,
                    ingredient_name=ingredient,
                    canonical_drug_id=canonical_id,
                ):
                    inserted_mappings += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"codeit products={len(rows)} inserted_entities={inserted_entities} "
        f"reused_entities={reused_entities} inserted_mappings={inserted_mappings}"
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_codeit_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    values = raw.values() if isinstance(raw, dict) else raw
    rows = [item for item in values if isinstance(item, dict)]
    rows.sort(key=lambda item: str(item.get("dl_name") or ""))
    return rows


def ensure_canonical_entity(cursor, ingredient_name: str) -> tuple[str, bool]:
    normalized = normalize_key(ingredient_name)
    cursor.execute(
        """
        SELECT canonical_drug_id
        FROM canonical_drug_entities
        WHERE canonical_name_ko = %s
           OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(canonical_name_ko), ' ', ''), '-', ''), '_', ''), '/', ''), '(', ''), ')', ''), '.', '') = %s
           OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(raw_aliases), ' ', ''), '-', ''), '_', ''), '/', ''), '(', ''), ')', ''), '.', '') LIKE %s
        LIMIT 1
        """,
        (ingredient_name, normalized, f"%{normalized}%"),
    )
    existing = cursor.fetchone()
    if existing:
        return existing["canonical_drug_id"], False

    canonical_id = f"CODEIT_ING_{stable_hash(ingredient_name)}"
    cursor.execute(
        """
        INSERT IGNORE INTO canonical_drug_entities (
            canonical_drug_id, entity_level, canonical_name_ko, canonical_name_en,
            alias_count, raw_aliases, external_id_status, mapping_status,
            verification_source_name, verification_source_url, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            canonical_id,
            "ingredient",
            ingredient_name,
            None,
            1,
            ingredient_name,
            "unmapped",
            "codeit_imported",
            "ZerofZero/codeit10_pj1 pill_info_master",
            "https://github.com/ZerofZero/codeit10_pj1",
            "Imported from codeit10_pj1 e약은요/MFDS cache for pill product ingredient resolution.",
        ),
    )
    return canonical_id, cursor.rowcount > 0


def ensure_product_mapping(
    cursor,
    product_code: str | None,
    product_name: str,
    ingredient_name: str,
    canonical_drug_id: str,
) -> bool:
    normalized_product = normalize_key(product_name)
    normalized_ingredient = normalize_key(ingredient_name)
    cursor.execute(
        """
        SELECT id
        FROM pill_product_ingredients
        WHERE normalized_product_name = %s
          AND normalized_ingredient_name = %s
          AND canonical_drug_id = %s
        LIMIT 1
        """,
        (normalized_product, normalized_ingredient, canonical_drug_id),
    )
    if cursor.fetchone():
        return False
    cursor.execute(
        """
        INSERT INTO pill_product_ingredients (
            product_code, product_name, normalized_product_name,
            ingredient_name, normalized_ingredient_name, canonical_drug_id, source_name
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            product_code,
            product_name,
            normalized_product,
            ingredient_name,
            normalized_ingredient,
            canonical_drug_id,
            "codeit10_pj1",
        ),
    )
    return True


def extract_ingredients(material: Any) -> list[str]:
    text = clean_text(material)
    if not text:
        return []
    names: list[str] = []
    for match in re.finditer(r"성분명\s*:\s*([^|;\n]+)", text):
        value = clean_text(match.group(1))
        if value and value not in names:
            names.append(value)
    return names


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_key(value: str) -> str:
    return re.sub(r"[\s\-_/().]+", "", value.strip().lower())


def stable_hash(value: str) -> str:
    return hashlib.sha1(normalize_key(value).encode("utf-8")).hexdigest()[:16].upper()


if __name__ == "__main__":
    main()
