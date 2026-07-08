"""
MFDS 건강기능식품 종합정보 서비스의 "의약품 병용 섭취정보" 공개
페이지를 직접 수집해 국내 공식 근거 claim으로 적재한다.

이 소스는 data.go.kr 인증키가 필요 없는 공개 웹 페이지다.
기존 정제 워크북의 원천과 같은 계열이지만, 현재 공개 페이지를 다시
읽어 원문/표/성분 그룹을 raw record와 evidence claim으로 남긴다.

사용법:
    python scripts/import_mfds_hid_live_evidence.py
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.api.v1.endpoints.interactions import _infer_level
from app.db.connection import get_conn

SOURCE_KEY = "mfds_hid_live"
BASE_URL = "https://data.mfds.go.kr"
LIST_URL = f"{BASE_URL}/hid/opeaa01/drugUsjntIntkAttnMttrLst.do"
DETAIL_URL = f"{BASE_URL}/hid/opeab01/drugUsjntIntkAttnMttrDtl.do"

ENSURE_SOURCE_SQL = """
INSERT INTO interaction_source_registry (
    source_key, source_name, source_url, source_type, ingestion_status, notes
)
VALUES (
    'mfds_hid_live',
    '식품의약품안전처 건강기능식품 종합정보 서비스 의약품 병용섭취정보',
    'https://data.mfds.go.kr/hid/opeaa01/drugUsjntIntkAttnMttrLst.do',
    'public_web',
    'ingested',
    'MFDS HID 공개 상세 페이지를 직접 수집해 국내 공식 근거 claim으로 적재'
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


class DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_title = False
        self.capture_intro = False
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.table_rows: list[list[str]] = []
        self.in_med_list = False
        self.in_med_item = False
        self.capture_med_heading = False
        self.capture_med_text = False
        self.current_med_heading: list[str] = []
        self.current_med_text: list[str] = []
        self.med_items: list[dict[str, str]] = []
        self.title = ""
        self.intro = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        if tag == "h2" and "ingre-tit" in class_name:
            self.capture_title = True
        elif tag == "p" and "ingre-txt" in class_name:
            self.capture_intro = True
        elif tag == "table" and "product_table" in class_name:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []
        elif tag == "ul" and "med-list" in class_name:
            self.in_med_list = True
        elif self.in_med_list and tag == "li":
            self.in_med_item = True
            self.current_med_heading = []
            self.current_med_text = []
        elif self.in_med_item and tag == "h3":
            self.capture_med_heading = True
        elif self.in_med_item and tag == "p":
            self.capture_med_text = True
        elif self.capture_med_text and tag == "br":
            self.current_med_text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self.capture_title:
            self.capture_title = False
        elif tag == "p" and self.capture_intro:
            self.capture_intro = False
        elif tag in {"td", "th"} and self.in_cell:
            self.current_row.append(clean_text("".join(self.current_cell)))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if len(self.current_row) >= 2 and self.current_row[0] != "주의 약물":
                self.table_rows.append(self.current_row[:2])
            self.in_row = False
        elif tag == "table" and self.in_table:
            self.in_table = False
        elif tag == "h3" and self.capture_med_heading:
            self.capture_med_heading = False
        elif tag == "p" and self.capture_med_text:
            self.capture_med_text = False
        elif tag == "li" and self.in_med_item:
            heading = clean_text("".join(self.current_med_heading))
            text = clean_text("".join(self.current_med_text), keep_newlines=True)
            if heading or text:
                self.med_items.append({"heading": heading, "text": text})
            self.in_med_item = False
        elif tag == "ul" and self.in_med_list:
            self.in_med_list = False

    def handle_data(self, data: str) -> None:
        if self.capture_title:
            self.title += data
        if self.capture_intro:
            self.intro += data
        if self.in_cell:
            self.current_cell.append(data)
        if self.capture_med_heading:
            self.current_med_heading.append(data)
        if self.capture_med_text:
            self.current_med_text.append(data)


def clean_text(value: str, keep_newlines: bool = False) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    if keep_newlines:
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
        value = re.sub(r"\n\s*", "\n", value)
    else:
        value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_ko(value: str | None) -> str:
    return re.sub(r"[\s\-_()/·ㆍ.,]+", "", (value or "").strip().lower())


def fetch(url: str, data: dict[str, str] | None = None) -> str:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "ignore")


def parse_list(html_text: str) -> list[tuple[str, str]]:
    items = re.findall(r"pageGoPrdInfo\('([0-9]+)'\).*?<h3><span>\d+</span>(.*?)</h3>", html_text, re.S)
    return [(record_id, clean_text(title)) for record_id, title in items]


def parse_detail(html_text: str) -> dict:
    parser = DetailParser()
    parser.feed(html_text)
    return {
        "title": clean_text(parser.title),
        "intro": clean_text(parser.intro),
        "table_rows": parser.table_rows,
        "med_items": parser.med_items,
    }


def load_supplements(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT supplement_id, canonical_name_ko, canonical_name_en, raw_name
        FROM supplement_map
        ORDER BY supplement_id
        """
    )
    return cursor.fetchall()


def load_drugs(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT canonical_drug_id, canonical_name_ko, canonical_name_en, raw_aliases
        FROM canonical_drug_entities
        ORDER BY canonical_drug_id
        """
    )
    return cursor.fetchall()


def split_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,|;/]", value) if item.strip()]


def find_supplement(title: str, supplements: list[dict]) -> dict | None:
    normalized_title = normalize_ko(title)
    best: tuple[int, dict] | None = None
    for supplement in supplements:
        names = [
            supplement.get("canonical_name_ko"),
            supplement.get("canonical_name_en"),
            supplement.get("raw_name"),
        ]
        score = 0
        for name in names:
            normalized_name = normalize_ko(name)
            if not normalized_name:
                continue
            if normalized_name == normalized_title:
                score = max(score, 100)
            elif normalized_name in normalized_title or normalized_title in normalized_name:
                score = max(score, min(len(normalized_name), len(normalized_title)))
        if score and (best is None or score > best[0]):
            best = (score, supplement)
    return best[1] if best else None


def build_drug_index(drugs: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for drug in drugs:
        names = [drug.get("canonical_name_ko"), drug.get("canonical_name_en")]
        names.extend(split_aliases(drug.get("raw_aliases")))
        for name in names:
            normalized = normalize_ko(name)
            if normalized:
                index.setdefault(normalized, []).append(drug)
    return index


def extract_ingredients(text: str) -> list[str]:
    text = text.replace("뮤로모냅", "무로모납")
    text = text.replace("아스프린", "아스피린")
    text = text.replace("에노사파린", "에녹사파린")
    text = re.sub(r"성분\s*:", "", text)
    parts = re.split(r"[,·/\n]|\s및\s|\s또는\s", text)
    cleaned: list[str] = []
    for part in parts:
        part = re.sub(r"^-+\s*", "", part)
        part = re.sub(r"\(.*?\)", "", part).strip()
        if part and len(part) >= 2:
            cleaned.append(part)
    return cleaned


def med_group_ingredients(row_group: str, med_items: list[dict]) -> list[str]:
    normalized_group = normalize_ko(re.sub(r"\(.*?\)", "", row_group))
    ingredients: list[str] = []
    for item in med_items:
        heading = normalize_ko(item.get("heading"))
        if heading and (heading in normalized_group or normalized_group in heading):
            ingredients.extend(extract_ingredients(item.get("text", "")))
    parens = re.findall(r"\((.*?)\)", row_group)
    for value in parens:
        ingredients.extend(extract_ingredients(value))
    ingredients.append(re.sub(r"\(.*?\)", "", row_group).strip())
    return ingredients


def match_drugs(names: list[str], drug_index: dict[str, list[dict]]) -> list[dict]:
    matched: dict[str, dict] = {}
    for name in names:
        normalized = normalize_ko(name)
        if not normalized:
            continue
        candidates = drug_index.get(normalized, [])
        if not candidates:
            for key, drugs in drug_index.items():
                if len(normalized) >= 3 and (normalized == key or normalized in key or key in normalized):
                    candidates.extend(drugs)
        for drug in candidates:
            matched[drug["canonical_drug_id"]] = drug
    return list(matched.values())


def evidence_id(record_id: str, supplement_id: str, drug_id: str, index: int) -> str:
    return f"MFDSHID_{record_id}_{supplement_id}_{drug_id}_{index}"[:100]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args()

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    plain_cursor = conn.cursor()
    try:
        plain_cursor.execute(CREATE_RAW_RECORDS_SQL)
        plain_cursor.execute(ENSURE_SOURCE_SQL)
        supplements = load_supplements(cursor)
        drugs = load_drugs(cursor)
        drug_index = build_drug_index(drugs)

        list_html = fetch(LIST_URL)
        records = parse_list(list_html)
        now = datetime.now(UTC).replace(tzinfo=None)
        evidence_rows: list[tuple] = []
        source_checks: dict[tuple[str, str], int] = {}
        pages_matched = 0
        rows_matched = 0

        for record_id, list_title in records:
            detail_url = f"{DETAIL_URL}?drugInfoSn={record_id}"
            detail_html = fetch(detail_url)
            parsed = parse_detail(detail_html)
            title = parsed["title"] or list_title
            supplement = find_supplement(title, supplements)
            raw_payload = {
                "record_id": record_id,
                "list_title": list_title,
                "title": title,
                "intro": parsed["intro"],
                "table_rows": parsed["table_rows"],
                "med_items": parsed["med_items"],
            }
            plain_cursor.execute(
                INSERT_RAW_RECORD_SQL,
                (
                    SOURCE_KEY,
                    record_id,
                    title,
                    detail_url,
                    json.dumps(raw_payload, ensure_ascii=False),
                    now,
                ),
            )
            if not supplement:
                time.sleep(args.sleep)
                continue
            pages_matched += 1
            supplement_id = supplement["supplement_id"]
            supplement_name = supplement.get("canonical_name_ko") or title
            for index, (drug_group, interaction_text) in enumerate(parsed["table_rows"], start=1):
                names = med_group_ingredients(drug_group, parsed["med_items"])
                matched_drugs = match_drugs(names, drug_index)
                if not matched_drugs:
                    continue
                rows_matched += 1
                for drug in matched_drugs:
                    drug_id = drug["canonical_drug_id"]
                    source_checks[(supplement_id, drug_id)] = source_checks.get((supplement_id, drug_id), 0) + 1
                    evidence_rows.append(
                        (
                            evidence_id(record_id, supplement_id, drug_id, index),
                            SOURCE_KEY,
                            record_id,
                            supplement_id,
                            supplement_name,
                            drug_id,
                            drug.get("canonical_name_ko") or drug.get("canonical_name_en"),
                            _infer_level(interaction_text),
                            interaction_text,
                            parsed["intro"],
                            None,
                            "mfds_hid_public_page",
                            detail_url,
                            json.dumps(
                                {
                                    "record_id": record_id,
                                    "title": title,
                                    "drug_group": drug_group,
                                    "candidate_names": names,
                                },
                                ensure_ascii=False,
                            ),
                            now,
                        )
                    )
            time.sleep(args.sleep)

        for index in range(0, len(evidence_rows), 1000):
            plain_cursor.executemany(INSERT_EVIDENCE_SQL, evidence_rows[index:index + 1000])

        all_pairs = [(supplement["supplement_id"], drug["canonical_drug_id"]) for supplement in supplements for drug in drugs]
        check_rows = []
        for supplement_id, drug_id in all_pairs:
            count = source_checks.get((supplement_id, drug_id), 0)
            check_rows.append(
                (
                    supplement_id,
                    drug_id,
                    SOURCE_KEY,
                    "attention_found" if count else "no_claim_found",
                    count,
                    now,
                    "MFDS HID 공개 페이지에서 claim 확인" if count else "MFDS HID 공개 페이지에서 claim 미탐지",
                )
            )
        for index in range(0, len(check_rows), 1000):
            plain_cursor.executemany(INSERT_SOURCE_CHECK_SQL, check_rows[index:index + 1000])

        conn.commit()
        print(
            "완료: "
            f"상세 페이지 {len(records)}개 수집, supplement 매칭 {pages_matched}개, "
            f"표 row 매칭 {rows_matched}개, evidence {len(evidence_rows)}개, "
            f"attention 조합 {len(source_checks)}개"
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
