"""
현재 DB의 건강기능식품 성분 x 약 성분 전체 조합 판정표를 생성한다.

결과 테이블:
    ingredient_interaction_matrix

의미:
    - needs_attention=1: standardized_interactions에 상호작용 claim이 있음
    - needs_attention=0: 현재 DB에서 확인된 주의 정보가 없음

주의:
    needs_attention=0은 "안전 검증 완료"가 아니라 "현재 DB 기준 주의 정보 미탐지"다.

사용법:
    python scripts/build_interaction_matrix.py
    python scripts/build_interaction_matrix.py --csv /tmp/interaction_matrix.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.api.v1.endpoints.interactions import _infer_level
from app.db.connection import get_conn

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingredient_interaction_matrix (
    supplement_id VARCHAR(50) NOT NULL,
    supplement_name VARCHAR(255),
    canonical_drug_id VARCHAR(50) NOT NULL,
    drug_name VARCHAR(255),
    risk_level VARCHAR(50) NOT NULL,
    needs_attention TINYINT(1) NOT NULL DEFAULT 0,
    evidence_status VARCHAR(100) NOT NULL,
    reason TEXT,
    claim_count INT NOT NULL DEFAULT 0,
    claim_ids TEXT,
    source_names TEXT,
    source_urls TEXT,
    source_review_statuses TEXT,
    overall_review_statuses TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (supplement_id, canonical_drug_id),
    KEY idx_matrix_risk (risk_level),
    KEY idx_matrix_attention (needs_attention),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

INSERT_SQL = """
INSERT INTO ingredient_interaction_matrix (
    supplement_id, supplement_name, canonical_drug_id, drug_name,
    risk_level, needs_attention, evidence_status, reason,
    claim_count, claim_ids, source_names, source_urls,
    source_review_statuses, overall_review_statuses
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    supplement_name = VALUES(supplement_name),
    drug_name = VALUES(drug_name),
    risk_level = VALUES(risk_level),
    needs_attention = VALUES(needs_attention),
    evidence_status = VALUES(evidence_status),
    reason = VALUES(reason),
    claim_count = VALUES(claim_count),
    claim_ids = VALUES(claim_ids),
    source_names = VALUES(source_names),
    source_urls = VALUES(source_urls),
    source_review_statuses = VALUES(source_review_statuses),
    overall_review_statuses = VALUES(overall_review_statuses)
"""

NO_KNOWN_WARNING_REASON = "현재 DB에서 확인된 주의 정보 없음"


def unique_join(values: list[str | None], sep: str = " | ") -> str | None:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return sep.join(result) if result else None


def risk_rank(level: str) -> int:
    return {"danger": 3, "caution": 2, "safe": 1, "no_known_warning": 0}.get(level, 0)


def load_supplements(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT supplement_id, canonical_name_ko, canonical_name_en
        FROM supplement_map
        ORDER BY supplement_id
        """
    )
    return cursor.fetchall()


def load_drugs(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT canonical_drug_id, canonical_name_ko, canonical_name_en
        FROM canonical_drug_entities
        ORDER BY canonical_drug_id
        """
    )
    return cursor.fetchall()


def load_claims(cursor) -> dict[tuple[str, str], list[dict]]:
    cursor.execute(
        """
        SELECT claim_id, supplement_id, supplement_canonical_ko,
               canonical_drug_id, drug_canonical_ko, drug_canonical_en,
               interaction_text_raw, source_name, source_url,
               source_review_status, overall_review_status
        FROM standardized_interactions
        WHERE supplement_id IS NOT NULL
          AND canonical_drug_id IS NOT NULL
          AND interaction_text_raw IS NOT NULL
          AND interaction_text_raw <> ''
        """
    )
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in cursor.fetchall():
        grouped[(row["supplement_id"], row["canonical_drug_id"])].append(row)
    return grouped


def build_row(supplement: dict, drug: dict, claims: list[dict]) -> tuple:
    supplement_name = supplement["canonical_name_ko"] or supplement["canonical_name_en"]
    drug_name = drug["canonical_name_ko"] or drug["canonical_name_en"]

    if not claims:
        return (
            supplement["supplement_id"],
            supplement_name,
            drug["canonical_drug_id"],
            drug_name,
            "no_known_warning",
            0,
            "no_claim_in_current_db",
            NO_KNOWN_WARNING_REASON,
            0,
            None,
            None,
            None,
            None,
            None,
        )

    levels = [_infer_level(row["interaction_text_raw"]) for row in claims]
    risk_level = max(levels, key=risk_rank)
    reasons = unique_join([row["interaction_text_raw"] for row in claims])
    return (
        supplement["supplement_id"],
        supplement_name,
        drug["canonical_drug_id"],
        drug_name,
        risk_level,
        1,
        "known_interaction_claim",
        reasons,
        len(claims),
        unique_join([row["claim_id"] for row in claims], ","),
        unique_join([row["source_name"] for row in claims]),
        unique_join([row["source_url"] for row in claims]),
        unique_join([row["source_review_status"] for row in claims], ","),
        unique_join([row["overall_review_status"] for row in claims], ","),
    )


def write_csv(rows: list[tuple], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "supplement_id",
        "supplement_name",
        "canonical_drug_id",
        "drug_name",
        "risk_level",
        "needs_attention",
        "evidence_status",
        "reason",
        "claim_count",
        "claim_ids",
        "source_names",
        "source_urls",
        "source_review_statuses",
        "overall_review_statuses",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=None, help="전체 조합 CSV export 경로")
    args = parser.parse_args()

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(CREATE_TABLE_SQL)
        supplements = load_supplements(cursor)
        drugs = load_drugs(cursor)
        claims_by_pair = load_claims(cursor)

        rows: list[tuple] = []
        for supplement in supplements:
            for drug in drugs:
                rows.append(build_row(supplement, drug, claims_by_pair.get((supplement["supplement_id"], drug["canonical_drug_id"]), [])))

        plain_cursor = conn.cursor()
        try:
            plain_cursor.execute("DELETE FROM ingredient_interaction_matrix")
            for index in range(0, len(rows), 1000):
                plain_cursor.executemany(INSERT_SQL, rows[index:index + 1000])
            conn.commit()
        finally:
            plain_cursor.close()

        if args.csv:
            write_csv(rows, args.csv)

        attention = sum(1 for row in rows if row[5])
        danger = sum(1 for row in rows if row[4] == "danger")
        caution = sum(1 for row in rows if row[4] == "caution")
        no_known = sum(1 for row in rows if row[4] == "no_known_warning")
        print(
            "완료: "
            f"건기식 {len(supplements)}개 x 약 {len(drugs)}개 = 전체 {len(rows)}개, "
            f"주의 {attention}개(danger {danger}, caution {caution}), "
            f"현재 DB 주의 정보 미탐지 {no_known}개"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
