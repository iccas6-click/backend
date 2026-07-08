"""Import official domestic drug product records into the product catalog.

This importer intentionally does not read AIHub pill IDs or K-codes. Product
identity is anchored to MFDS/official identifiers such as item_seq, and optional
pharmacy-identification metadata can be attached when a licensed source provides it.

Usage:
    python scripts/import_official_drug_products.py --query 타이레놀이알서방정
    python scripts/import_official_drug_products.py --from-legacy-limit 200
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import dotenv_values, load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

PERMIT_API_URL = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
IDENT_API_URL = "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03/getMdcinGrnIdntfcInfoList03"
EASY_DRUG_API_URL = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
PERMIT_SOURCE_URL = "https://www.data.go.kr/data/15095677/openapi.do"
IDENT_SOURCE_URL = "https://www.data.go.kr/data/15057639/openapi.do"
EASY_DRUG_SOURCE_URL = "https://www.data.go.kr/data/15075057/openapi.do"

CREATE_PRODUCTS_SQL = """
CREATE TABLE IF NOT EXISTS official_drug_products (
    item_seq VARCHAR(50) PRIMARY KEY,
    pharm_product_code VARCHAR(80),
    drug_identification_code VARCHAR(80),
    product_name VARCHAR(255) NOT NULL,
    normalized_product_name VARCHAR(255) NOT NULL,
    manufacturer_name VARCHAR(255),
    dosage_form VARCHAR(100),
    main_ingredient_raw TEXT,
    product_image_url TEXT,
    image_source_name VARCHAR(255),
    image_source_url TEXT,
    efficacy_text TEXT,
    use_method_text TEXT,
    warning_text TEXT,
    interaction_text TEXT,
    side_effect_text TEXT,
    storage_text TEXT,
    source_name VARCHAR(255),
    source_url TEXT,
    source_record_id VARCHAR(100),
    fetched_at TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_official_product_norm (normalized_product_name),
    KEY idx_official_product_pharm_code (pharm_product_code),
    KEY idx_official_product_ident_code (drug_identification_code)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

CREATE_INGREDIENTS_SQL = """
CREATE TABLE IF NOT EXISTS official_drug_product_ingredients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_seq VARCHAR(50) NOT NULL,
    ingredient_name VARCHAR(255) NOT NULL,
    normalized_ingredient_name VARCHAR(255) NOT NULL,
    canonical_drug_id VARCHAR(50) NOT NULL,
    source_name VARCHAR(255),
    source_record_id VARCHAR(100),
    UNIQUE KEY uq_official_product_ingredient (item_seq, normalized_ingredient_name),
    KEY idx_official_ingredient_norm (normalized_ingredient_name),
    FOREIGN KEY (item_seq) REFERENCES official_drug_products(item_seq),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""


def normalize_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("밀리그램", "mg")
    normalized = normalized.replace("마이크로그램", "mcg")
    normalized = normalized.replace("그램", "g")
    normalized = normalized.replace("밀리리터", "ml")
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", normalized)


def first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        for candidate in {key, key.lower(), key.upper()}:
            value = record.get(candidate)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def clean_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        clean = value.strip()
        key = normalize_name(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(clean)
    return cleaned


def clean_ingredient_name(value: str) -> str:
    return re.sub(r"\[[A-Za-z]\d{3,}\]", "", value or "").strip()


def split_ingredients(raw: str) -> list[str]:
    text = re.sub(r"\([^)]*(?:총량|첨가제|기타)[^)]*\)", " ", raw)
    text = re.sub(r"\[[A-Za-z]\d{3,}\]", " ", text)
    text = re.sub(r"\b\d+(\.\d+)?\s*(mg|g|mcg|μg|ug|iu|ml|%)\b", " ", text, flags=re.IGNORECASE)
    parts = re.split(r"[|,;/\n]+|ㆍ|·| 및 | 그리고 ", text)
    return clean_unique([clean_ingredient_name(re.sub(r"\s+", " ", part).strip(" :-")) for part in parts])


def official_ingredient_id(name: str) -> str:
    digest = hashlib.sha1(normalize_name(name).encode("utf-8")).hexdigest()[:16].upper()
    return f"OFFICIAL_ING_{digest}"


def load_service_key(explicit_key: str | None) -> str:
    if explicit_key:
        return explicit_key
    for env_path in [
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / "ai" / ".env",
    ]:
        if env_path.exists():
            values = dotenv_values(env_path)
            for key_name in ("MFDS_API_KEY", "DATA_GO_KR_SERVICE_KEY"):
                if values.get(key_name):
                    return str(values[key_name])
    return os.environ.get("MFDS_API_KEY") or os.environ.get("DATA_GO_KR_SERVICE_KEY") or ""


def fetch_json(url: str, service_key: str, params: dict[str, str], timeout: int) -> dict[str, Any]:
    query = {
        "serviceKey": service_key,
        "type": "json",
        "pageNo": params.pop("pageNo", "1"),
        "numOfRows": params.pop("numOfRows", "10"),
        **params,
    }
    request_url = f"{url}?{urllib.parse.urlencode(query)}"
    with urllib.request.urlopen(request_url, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def response_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("body") or payload.get("Body") or {}
    items = body.get("items") or body.get("Items") or payload.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or items.get("ITEM") or []
    if isinstance(items, dict):
        items = [items]
    return [item for item in items if isinstance(item, dict)]


def fetch_product_records(query: str, service_key: str, timeout: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    sources = [
        (PERMIT_API_URL, "MFDS drug product permission OpenAPI", {"item_name": query}),
        (EASY_DRUG_API_URL, "MFDS e약은요 OpenAPI", {"itemName": query}),
    ]
    if os.environ.get("OFFICIAL_DRUG_IMPORT_INCLUDE_IDENT", "").strip() in {"1", "true", "TRUE", "yes"}:
        sources.insert(1, (IDENT_API_URL, "MFDS pill identification OpenAPI", {"item_name": query}))

    for url, source_name, params in sources:
        try:
            payload = fetch_json(url, service_key, params, timeout)
            for item in response_items(payload):
                item["_source_name"] = source_name
                if url == PERMIT_API_URL:
                    item["_source_url"] = PERMIT_SOURCE_URL
                elif url == IDENT_API_URL:
                    item["_source_url"] = IDENT_SOURCE_URL
                else:
                    item["_source_url"] = EASY_DRUG_SOURCE_URL
                records.append(item)
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")
    if errors:
        print("official_api_warnings=" + " | ".join(errors), file=sys.stderr)
    return records


def merge_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for record in records:
        item_seq = first_text(record, "ITEM_SEQ", "itemSeq", "item_seq")
        product_name = first_text(record, "ITEM_NAME", "itemName", "item_name")
        if not item_seq or not product_name:
            continue
        target = merged.setdefault(
            item_seq,
            {
                "item_seq": item_seq,
                "product_name": product_name,
                "normalized_product_name": normalize_name(product_name),
                "manufacturer_name": "",
                "dosage_form": "",
                "main_ingredient_raw": "",
                "product_image_url": "",
                "image_source_name": "",
                "image_source_url": "",
                "efficacy_text": "",
                "use_method_text": "",
                "warning_text": "",
                "interaction_text": "",
                "side_effect_text": "",
                "storage_text": "",
                "source_name": "",
                "source_url": "",
                "source_record_id": item_seq,
            },
        )
        target["manufacturer_name"] = target["manufacturer_name"] or first_text(record, "ENTP_NAME", "entpName")
        target["dosage_form"] = target["dosage_form"] or first_text(record, "FORM_CODE_NAME", "FORM_NAME", "CHART")
        target["main_ingredient_raw"] = target["main_ingredient_raw"] or first_text(
            record,
            "MAIN_ITEM_INGR",
            "MATERIAL_NAME",
            "MAIN_INGR",
        )
        image_url = first_text(record, "ITEM_IMAGE", "itemImage", "IMG_REGIST_TS")
        if image_url and image_url.startswith("http"):
            target["product_image_url"] = target["product_image_url"] or image_url
            target["image_source_name"] = target["image_source_name"] or str(record.get("_source_name") or "")
            target["image_source_url"] = target["image_source_url"] or str(record.get("_source_url") or "")
        target["efficacy_text"] = target["efficacy_text"] or first_text(record, "efcyQesitm")
        target["use_method_text"] = target["use_method_text"] or first_text(record, "useMethodQesitm")
        warning_parts = clean_unique([
            first_text(record, "atpnWarnQesitm"),
            first_text(record, "atpnQesitm"),
        ])
        target["warning_text"] = target["warning_text"] or "\n\n".join(warning_parts)
        target["interaction_text"] = target["interaction_text"] or first_text(record, "intrcQesitm")
        target["side_effect_text"] = target["side_effect_text"] or first_text(record, "seQesitm")
        target["storage_text"] = target["storage_text"] or first_text(record, "depositMethodQesitm")
        target["source_name"] = target["source_name"] or str(record.get("_source_name") or "")
        target["source_url"] = target["source_url"] or str(record.get("_source_url") or "")
    return list(merged.values())


def resolve_or_create_ingredient(cursor, ingredient_name: str) -> str:
    ingredient_name = clean_ingredient_name(ingredient_name)
    normalized = normalize_name(ingredient_name)
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
    row = cursor.fetchone()
    if row:
        return row["canonical_drug_id"]

    drug_id = official_ingredient_id(ingredient_name)
    cursor.execute(
        """
        INSERT INTO canonical_drug_entities (
            canonical_drug_id, entity_level, canonical_name_ko, canonical_name_en,
            alias_count, raw_aliases, external_id_status, mapping_status,
            verification_source_name, verification_source_url, notes
        )
        VALUES (%s, 'INGREDIENT', %s, NULL, 1, %s, 'PENDING', 'OFFICIAL_PRODUCT_CATALOG',
                'MFDS official product catalog', %s, '공식 제품 카탈로그에서 발견된 성분명')
        ON DUPLICATE KEY UPDATE
            canonical_name_ko = VALUES(canonical_name_ko),
            raw_aliases = VALUES(raw_aliases),
            mapping_status = VALUES(mapping_status),
            verification_source_name = VALUES(verification_source_name),
            verification_source_url = VALUES(verification_source_url)
        """,
        (drug_id, ingredient_name, ingredient_name, PERMIT_SOURCE_URL),
    )
    return drug_id


def upsert_products(products: list[dict[str, str]], dry_run: bool) -> int:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(CREATE_PRODUCTS_SQL)
        cursor.execute(CREATE_INGREDIENTS_SQL)
        count = 0
        for product in products:
            ingredients = split_ingredients(product.get("main_ingredient_raw", ""))
            if dry_run:
                print(json.dumps({"product": product, "ingredients": ingredients}, ensure_ascii=False))
                count += 1
                continue
            cursor.execute(
                """
                INSERT INTO official_drug_products (
                    item_seq, product_name, normalized_product_name, manufacturer_name,
                    dosage_form, main_ingredient_raw, product_image_url, image_source_name,
                    image_source_url, efficacy_text, use_method_text, warning_text,
                    interaction_text, side_effect_text, storage_text, source_name,
                    source_url, source_record_id, fetched_at
                )
                VALUES (%(item_seq)s, %(product_name)s, %(normalized_product_name)s,
                        %(manufacturer_name)s, %(dosage_form)s, %(main_ingredient_raw)s,
                        %(product_image_url)s, %(image_source_name)s, %(image_source_url)s,
                        %(efficacy_text)s, %(use_method_text)s, %(warning_text)s,
                        %(interaction_text)s, %(side_effect_text)s, %(storage_text)s,
                        %(source_name)s, %(source_url)s, %(source_record_id)s, NOW())
                ON DUPLICATE KEY UPDATE
                    product_name = VALUES(product_name),
                    normalized_product_name = VALUES(normalized_product_name),
                    manufacturer_name = VALUES(manufacturer_name),
                    dosage_form = VALUES(dosage_form),
                    main_ingredient_raw = VALUES(main_ingredient_raw),
                    product_image_url = VALUES(product_image_url),
                    image_source_name = VALUES(image_source_name),
                    image_source_url = VALUES(image_source_url),
                    efficacy_text = VALUES(efficacy_text),
                    use_method_text = VALUES(use_method_text),
                    warning_text = VALUES(warning_text),
                    interaction_text = VALUES(interaction_text),
                    side_effect_text = VALUES(side_effect_text),
                    storage_text = VALUES(storage_text),
                    source_name = VALUES(source_name),
                    source_url = VALUES(source_url),
                    fetched_at = VALUES(fetched_at)
                """,
                product,
            )
            for ingredient in ingredients:
                drug_id = resolve_or_create_ingredient(cursor, ingredient)
                cursor.execute(
                    """
                    INSERT INTO official_drug_product_ingredients (
                        item_seq, ingredient_name, normalized_ingredient_name,
                        canonical_drug_id, source_name, source_record_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        ingredient_name = VALUES(ingredient_name),
                        canonical_drug_id = VALUES(canonical_drug_id),
                        source_name = VALUES(source_name),
                        source_record_id = VALUES(source_record_id)
                    """,
                    (
                        product["item_seq"],
                        ingredient,
                        normalize_name(ingredient),
                        drug_id,
                        product.get("source_name"),
                        product.get("source_record_id"),
                    ),
                )
            count += 1
        conn.commit()
        return count
    finally:
        cursor.close()
        conn.close()


def legacy_product_queries(limit: int) -> list[str]:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT DISTINCT product_name
            FROM pill_product_ingredients
            ORDER BY product_name
            LIMIT %s
            """,
            (limit,),
        )
        return [row["product_name"] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", action="append", default=[], help="Product name to import.")
    parser.add_argument("--from-legacy-limit", type=int, default=0, help="Bootstrap by re-querying legacy product names against official APIs.")
    parser.add_argument("--service-key", default=None)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    service_key = load_service_key(args.service_key)
    if not service_key:
        raise SystemExit("MFDS_API_KEY 또는 DATA_GO_KR_SERVICE_KEY가 필요합니다.")

    queries = clean_unique(args.query)
    if args.from_legacy_limit:
        queries.extend([query for query in legacy_product_queries(args.from_legacy_limit) if query not in queries])
    if not queries:
        raise SystemExit("--query 또는 --from-legacy-limit 중 하나가 필요합니다.")

    imported = 0
    for query in queries:
        records = fetch_product_records(query, service_key, args.timeout)
        products = merge_records(records)
        imported += upsert_products(products, args.dry_run)
        time.sleep(args.sleep)
    print(f"imported_or_checked={imported}")


if __name__ == "__main__":
    main()
