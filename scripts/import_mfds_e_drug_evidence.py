"""
식품의약품안전처 의약품개요정보(e약은요) OpenAPI의 intrcQesitm
문항을 수집해 현 DB의 약 성분 x 건강기능식품 성분 조합 근거로 적재한다.

MFDS_API_KEY 위치:
    1. backend/.env
    2. ../ai/.env
    3. 환경변수

사용법:
    python scripts/import_mfds_e_drug_evidence.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import dotenv_values, load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.api.v1.endpoints.interactions import _infer_level
from app.db.connection import get_conn

SOURCE_KEY = "mfds_e_drug_openapi"
API_URL = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
SOURCE_URL = "https://www.data.go.kr/data/15075057/openapi.do"

SUPPLEMENT_TEXT_ALIASES = {
    "NUTR_001": ["비타민C", "비타민 C", "아스코르브산"],
    "NUTR_002": ["비타민D", "비타민 D"],
    "NUTR_003": ["비타민E", "비타민 E", "토코페롤"],
    "NUTR_004": ["비타민A", "비타민 A"],
    "NUTR_005": ["비타민K", "비타민 K"],
    "NUTR_014": ["칼슘", "칼슘제", "칼슘 함유"],
    "NUTR_015": ["마그네슘", "마그네슘제"],
    "NUTR_016": ["아연", "아연제"],
    "NUTR_017": ["철", "철분", "철분제", "철제"],
    "NUTR_023": ["칼륨", "칼륨함유제제", "칼륨 함유"],
    "SUPP_001": ["인삼", "홍삼", "고려인삼"],
    "SUPP_003": ["알로에"],
    "SUPP_004": ["오메가3", "오메가-3", "EPA", "DHA"],
    "SUPP_005": ["밀크씨슬", "실리마린"],
    "SUPP_010": ["대두", "이소플라본"],
    "SUPP_026": ["감초", "글리시리진"],
    "SUPP_027": ["울금", "커큐민", "강황"],
    "SUPP_028": ["마늘"],
    "SUPP_029": ["오미자"],
    "SUPP_032": ["글루코사민", "콘드로이친", "콘드로이틴"],
}

ENSURE_SOURCE_SQL = """
INSERT INTO interaction_source_registry (
    source_key, source_name, source_url, source_type, ingestion_status, notes
)
VALUES (
    'mfds_e_drug_openapi',
    '식품의약품안전처 의약품개요정보 e약은요 OpenAPI',
    'https://www.data.go.kr/data/15075057/openapi.do',
    'public_api',
    'ingested',
    'e약은요 intrcQesitm 문항을 수집해 현 DB 약 성분-건강기능식품 성분 조합에 매칭'
)
ON DUPLICATE KEY UPDATE
    ingestion_status = 'ingested',
    notes = VALUES(notes)
"""

CREATE_RAW_RECORDS_SQL = """
CREATE TABLE IF NOT EXISTS domestic_source_raw_records (
    source_key VARCHAR(80) NOT NULL,
    source_record_id VARCHAR(100) NOT NULL,
    title VARCHAR(255),
    source_url TEXT,
    raw_payload_json JSON,
    retrieved_at TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (source_key, source_record_id),
    FOREIGN KEY (source_key) REFERENCES interaction_source_registry(source_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

INSERT_RAW_RECORD_SQL = """
INSERT INTO domestic_source_raw_records (
    source_key, source_record_id, title, source_url, raw_payload_json, retrieved_at
)
VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    title = VALUES(title),
    source_url = VALUES(source_url),
    raw_payload_json = VALUES(raw_payload_json),
    retrieved_at = VALUES(retrieved_at)
"""

INSERT_EVIDENCE_SQL = """
INSERT INTO interaction_evidence_claims (
    evidence_id, source_key, source_record_id,
    supplement_id, supplement_name, canonical_drug_id, drug_name,
    risk_level, interaction_text, mechanism_text, recommendation_text,
    evidence_grade, source_url, raw_payload_json, retrieved_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    supplement_name = VALUES(supplement_name),
    drug_name = VALUES(drug_name),
    risk_level = VALUES(risk_level),
    interaction_text = VALUES(interaction_text),
    evidence_grade = VALUES(evidence_grade),
    source_url = VALUES(source_url),
    raw_payload_json = VALUES(raw_payload_json),
    retrieved_at = VALUES(retrieved_at)
"""

INSERT_SOURCE_CHECK_SQL = """
INSERT INTO interaction_pair_source_checks (
    supplement_id, canonical_drug_id, source_key,
    check_status, evidence_count, checked_at, notes
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    check_status = VALUES(check_status),
    evidence_count = VALUES(evidence_count),
    checked_at = VALUES(checked_at),
    notes = VALUES(notes)
"""


def normalize_name(value: str | None) -> str:
    return re.sub(r"[\s\-_()/·ㆍ.,:;\[\]{}<>]+", "", (value or "").lower())


def load_service_key() -> str:
    candidates = [
        os.environ.get("MFDS_API_KEY"),
        os.environ.get("DATA_GO_KR_SERVICE_KEY"),
        dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("MFDS_API_KEY"),
        dotenv_values(Path(__file__).resolve().parents[2] / "ai" / ".env").get("MFDS_API_KEY"),
    ]
    for value in candidates:
        if value and value.strip():
            return value.strip()
    raise SystemExit("MFDS_API_KEY가 없습니다. backend/.env 또는 ../ai/.env에 설정하세요.")


def fetch_page(service_key: str, page: int, rows: int) -> dict:
    params = {
        "serviceKey": service_key,
        "pageNo": str(page),
        "numOfRows": str(rows),
        "type": "json",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


def load_products(cursor) -> dict[str, set[tuple[str, str]]]:
    cursor.execute(
        """
        SELECT normalized_product_name, canonical_drug_id, ingredient_name
        FROM pill_product_ingredients
        """
    )
    products: dict[str, set[tuple[str, str]]] = {}
    for row in cursor.fetchall():
        products.setdefault(row["normalized_product_name"], set()).add((row["canonical_drug_id"], row["ingredient_name"]))
    return products


def load_supplements(cursor) -> dict[str, dict]:
    cursor.execute(
        """
        SELECT supplement_id, canonical_name_ko, canonical_name_en, raw_name
        FROM supplement_map
        """
    )
    return {row["supplement_id"]: row for row in cursor.fetchall()}


def load_drugs(cursor) -> dict[str, dict]:
    cursor.execute(
        """
        SELECT canonical_drug_id, canonical_name_ko, canonical_name_en, raw_aliases
        FROM canonical_drug_entities
        """
    )
    return {row["canonical_drug_id"]: row for row in cursor.fetchall()}


def match_product_drugs(item_name: str, products: dict[str, set[tuple[str, str]]]) -> set[tuple[str, str]]:
    normalized = normalize_name(item_name)
    stripped = normalize_name(re.sub(r"\(.*?\)", "", item_name or ""))
    matches: set[tuple[str, str]] = set()
    for product_norm, ingredients in products.items():
        if not product_norm:
            continue
        if product_norm == normalized or product_norm == stripped:
            matches.update(ingredients)
        elif len(product_norm) >= 4 and (product_norm in normalized or product_norm in stripped):
            matches.update(ingredients)
        elif len(stripped) >= 4 and stripped in product_norm:
            matches.update(ingredients)
    return matches


def build_supplement_aliases(supplements: dict[str, dict]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for supplement_id, supplement in supplements.items():
        values = {
            supplement.get("canonical_name_ko") or "",
            supplement.get("canonical_name_en") or "",
            supplement.get("raw_name") or "",
        }
        values.update(SUPPLEMENT_TEXT_ALIASES.get(supplement_id, []))
        aliases[supplement_id] = {normalize_name(value) for value in values if value}
    return aliases


def match_supplements(text: str, supplement_aliases: dict[str, set[str]]) -> list[tuple[str, str]]:
    normalized = normalize_name(text)
    matches: list[tuple[str, str]] = []
    for supplement_id, aliases in supplement_aliases.items():
        for alias in aliases:
            if alias and len(alias) >= 2 and alias in normalized:
                matches.append((supplement_id, alias))
                break
    return matches


def evidence_id(item_seq: str, supplement_id: str, drug_id: str) -> str:
    return f"MFDSDRB_{item_seq}_{supplement_id}_{drug_id}"[:100]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-rows", type=int, default=500)
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args()

    service_key = load_service_key()
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    plain_cursor = conn.cursor()
    try:
        plain_cursor.execute(CREATE_RAW_RECORDS_SQL)
        plain_cursor.execute(ENSURE_SOURCE_SQL)
        products = load_products(cursor)
        supplements = load_supplements(cursor)
        drugs = load_drugs(cursor)
        supplement_aliases = build_supplement_aliases(supplements)

        now = datetime.now(UTC).replace(tzinfo=None)
        evidence_rows: list[tuple] = []
        raw_count = 0
        intrc_count = 0
        product_match_count = 0
        supplement_match_count = 0
        pair_counts: dict[tuple[str, str], int] = {}

        first = fetch_page(service_key, 1, args.num_rows)
        body = first.get("body") or {}
        total = int(body.get("totalCount") or 0)
        total_pages = max(1, (total + args.num_rows - 1) // args.num_rows)

        for page in range(1, total_pages + 1):
            data = first if page == 1 else fetch_page(service_key, page, args.num_rows)
            items = ((data.get("body") or {}).get("items") or [])
            for item in items:
                raw_count += 1
                item_seq = str(item.get("itemSeq") or item.get("itemName") or raw_count)
                item_name = item.get("itemName") or ""
                intrc_text = (item.get("intrcQesitm") or "").strip()
                plain_cursor.execute(
                    INSERT_RAW_RECORD_SQL,
                    (
                        SOURCE_KEY,
                        item_seq,
                        item_name,
                        SOURCE_URL,
                        json.dumps(item, ensure_ascii=False),
                        now,
                    ),
                )
                if not intrc_text:
                    continue
                intrc_count += 1
                product_drugs = match_product_drugs(item_name, products)
                if not product_drugs:
                    continue
                product_match_count += 1
                supplement_matches = match_supplements(intrc_text, supplement_aliases)
                if not supplement_matches:
                    continue
                supplement_match_count += 1
                for drug_id, ingredient_name in product_drugs:
                    drug = drugs.get(drug_id, {})
                    for supplement_id, matched_alias in supplement_matches:
                        supplement = supplements[supplement_id]
                        pair_counts[(supplement_id, drug_id)] = pair_counts.get((supplement_id, drug_id), 0) + 1
                        evidence_rows.append(
                            (
                                evidence_id(item_seq, supplement_id, drug_id),
                                SOURCE_KEY,
                                item_seq,
                                supplement_id,
                                supplement.get("canonical_name_ko") or supplement.get("canonical_name_en"),
                                drug_id,
                                drug.get("canonical_name_ko") or drug.get("canonical_name_en") or ingredient_name,
                                _infer_level(intrc_text),
                                intrc_text,
                                None,
                                None,
                                "mfds_e_drug_intrcQesitm",
                                SOURCE_URL,
                                json.dumps(
                                    {
                                        "itemSeq": item_seq,
                                        "itemName": item_name,
                                        "ingredientName": ingredient_name,
                                        "matchedSupplementAlias": matched_alias,
                                        "openDe": item.get("openDe"),
                                        "updateDe": item.get("updateDe"),
                                    },
                                    ensure_ascii=False,
                                ),
                                now,
                            )
                        )
            time.sleep(args.sleep)

        for index in range(0, len(evidence_rows), 1000):
            plain_cursor.executemany(INSERT_EVIDENCE_SQL, evidence_rows[index:index + 1000])

        all_pairs = [(supplement_id, drug_id) for supplement_id in supplements for drug_id in drugs]
        check_rows = []
        for supplement_id, drug_id in all_pairs:
            count = pair_counts.get((supplement_id, drug_id), 0)
            check_rows.append(
                (
                    supplement_id,
                    drug_id,
                    SOURCE_KEY,
                    "attention_found" if count else "no_claim_found",
                    count,
                    now,
                    "e약은요 intrcQesitm에서 건강기능식품/영양소 관련 claim 확인" if count else "e약은요 intrcQesitm에서 관련 claim 미탐지",
                )
            )
        for index in range(0, len(check_rows), 1000):
            plain_cursor.executemany(INSERT_SOURCE_CHECK_SQL, check_rows[index:index + 1000])

        conn.commit()
        print(
            "완료: "
            f"e약은요 {raw_count}/{total}건 수집, intrcQesitm {intrc_count}건, "
            f"제품-성분 매칭 {product_match_count}건, supplement 텍스트 매칭 {supplement_match_count}건, "
            f"evidence {len(evidence_rows)}개, attention 조합 {len(pair_counts)}개"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        plain_cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
