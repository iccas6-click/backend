"""
현재 DB의 건강기능식품 성분 x 약 성분 전체 조합에 대해
조사 상태와 주의 근거 claim을 기록한다.

이 스크립트가 만드는 층:
    interaction_source_registry
        - 사용할 근거 소스 목록
    interaction_evidence_claims
        - 소스에서 확인된 주의 근거 claim
    interaction_pair_source_checks
        - 각 조합을 각 소스에서 확인했는지의 상태

현재 1차 구현은 기존 standardized_interactions를 "이미 정제된 MFDS HID
워크북 근거"로 이관하고, 그 기준으로 전체 조합 45,954개의 확인 상태를
기록한다. 외부 API/데이터셋을 추가 수집하면 같은 evidence 테이블에
claim을 더 넣고 매트릭스를 다시 만들면 된다.

사용법:
    python scripts/build_interaction_investigation.py
    python scripts/build_interaction_investigation.py --include-pending-source-checks
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.api.v1.endpoints.interactions import _infer_level
from app.db.connection import get_conn

CURRENT_SOURCE_KEY = "mfds_hid_current_workbook"

SOURCE_REGISTRY = [
    {
        "source_key": CURRENT_SOURCE_KEY,
        "source_name": "식품의약품안전처 건강기능식품 종합정보 서비스 정제 워크북",
        "source_url": "https://data.mfds.go.kr/hid/opeaa01/drugUsjntIntkAttnMttrLst.do",
        "source_type": "curated_workbook",
        "ingestion_status": "ingested",
        "notes": "data/source 워크북의 standardized_interactions를 근거 claim으로 사용",
    },
    {
        "source_key": "mfds_e_drug_openapi",
        "source_name": "식품의약품안전처 의약품개요정보 e약은요 OpenAPI",
        "source_url": "https://www.data.go.kr/data/15075057/openapi.do",
        "source_type": "public_api",
        "ingestion_status": "planned",
        "notes": "intrcQesitm 문항을 약-음식/건강기능식품 상호작용 후보 근거로 수집 예정",
    },
    {
        "source_key": "mfds_dur_ingredient_openapi",
        "source_name": "식품의약품안전처 DUR 성분정보 OpenAPI",
        "source_url": "https://www.data.go.kr/data/15056780/openapi.do",
        "source_type": "public_api",
        "ingestion_status": "planned",
        "notes": "병용금기/주의 성분 정보 보강 예정",
    },
    {
        "source_key": "supp_ai",
        "source_name": "Supp.ai",
        "source_url": "https://supp.ai/",
        "source_type": "external_dataset",
        "ingestion_status": "ingested",
        "notes": "scripts/import_supp_ai_evidence.py로 공개 bulk dataset evidence sentence 적재",
    },
    {
        "source_key": "idisk2",
        "source_name": "iDISK2.0",
        "source_url": "https://github.com/houyurain/iDISK2.0",
        "source_type": "external_dataset",
        "ingestion_status": "planned",
        "notes": "영문 supplement/drug entity와 관계 데이터 정규화 후보",
    },
    {
        "source_key": "openfda_drug_label",
        "source_name": "openFDA Drug Label API",
        "source_url": "https://open.fda.gov/apis/drug/label/",
        "source_type": "public_api",
        "ingestion_status": "planned",
        "notes": "영문 의약품 라벨의 drug_interactions/warnings 문구에서 후보 근거 추출 예정",
    },
    {
        "source_key": "nih_ods_fact_sheets",
        "source_name": "NIH Office of Dietary Supplements Fact Sheets",
        "source_url": "https://ods.od.nih.gov/",
        "source_type": "public_reference",
        "ingestion_status": "planned",
        "notes": "영양소/허브별 medication interaction 근거 보강 예정",
    },
    {
        "source_key": "medlineplus_supplements",
        "source_name": "MedlinePlus Herbs and Supplements",
        "source_url": "https://medlineplus.gov/druginfo/herb_All.html",
        "source_type": "public_reference",
        "ingestion_status": "planned",
        "notes": "소비자용 supplement-drug interaction 설명 보강 예정",
    },
]

CREATE_SOURCE_REGISTRY_SQL = """
CREATE TABLE IF NOT EXISTS interaction_source_registry (
    source_key VARCHAR(80) PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT,
    source_type VARCHAR(100),
    ingestion_status VARCHAR(100) NOT NULL DEFAULT 'planned',
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

CREATE_EVIDENCE_CLAIMS_SQL = """
CREATE TABLE IF NOT EXISTS interaction_evidence_claims (
    evidence_id VARCHAR(100) PRIMARY KEY,
    source_key VARCHAR(80) NOT NULL,
    source_record_id VARCHAR(100),
    supplement_id VARCHAR(50) NOT NULL,
    supplement_name VARCHAR(255),
    canonical_drug_id VARCHAR(50) NOT NULL,
    drug_name VARCHAR(255),
    risk_level VARCHAR(50) NOT NULL,
    interaction_text TEXT NOT NULL,
    mechanism_text TEXT,
    recommendation_text TEXT,
    evidence_grade VARCHAR(100),
    source_url TEXT,
    raw_payload_json JSON,
    retrieved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_evidence_source_record_pair (source_key, source_record_id, supplement_id, canonical_drug_id),
    KEY idx_evidence_pair (supplement_id, canonical_drug_id),
    KEY idx_evidence_risk (risk_level),
    FOREIGN KEY (source_key) REFERENCES interaction_source_registry(source_key),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

CREATE_SOURCE_CHECKS_SQL = """
CREATE TABLE IF NOT EXISTS interaction_pair_source_checks (
    supplement_id VARCHAR(50) NOT NULL,
    canonical_drug_id VARCHAR(50) NOT NULL,
    source_key VARCHAR(80) NOT NULL,
    check_status VARCHAR(100) NOT NULL,
    evidence_count INT NOT NULL DEFAULT 0,
    checked_at TIMESTAMP NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (supplement_id, canonical_drug_id, source_key),
    KEY idx_pair_source_status (source_key, check_status),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id),
    FOREIGN KEY (source_key) REFERENCES interaction_source_registry(source_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

INSERT_SOURCE_SQL = """
INSERT INTO interaction_source_registry (
    source_key, source_name, source_url, source_type, ingestion_status, notes
)
VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    source_name = VALUES(source_name),
    source_url = VALUES(source_url),
    source_type = VALUES(source_type),
    ingestion_status = IF(
        ingestion_status = 'ingested' AND VALUES(ingestion_status) = 'planned',
        ingestion_status,
        VALUES(ingestion_status)
    ),
    notes = VALUES(notes)
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
    source_url = VALUES(source_url),
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

INSERT_PENDING_SOURCE_CHECK_SQL = """
INSERT INTO interaction_pair_source_checks (
    supplement_id, canonical_drug_id, source_key,
    check_status, evidence_count, checked_at, notes
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    updated_at = updated_at
"""


def stable_evidence_id(source_key: str, source_record_id: str, supplement_id: str, canonical_drug_id: str, text: str) -> str:
    base = "|".join([source_key, source_record_id, supplement_id, canonical_drug_id, text])
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:20].upper()
    return f"EVID_{digest}"


def ensure_tables(cursor) -> None:
    cursor.execute(CREATE_SOURCE_REGISTRY_SQL)
    cursor.execute(CREATE_EVIDENCE_CLAIMS_SQL)
    cursor.execute(CREATE_SOURCE_CHECKS_SQL)


def register_sources(cursor) -> None:
    for source in SOURCE_REGISTRY:
        cursor.execute(
            INSERT_SOURCE_SQL,
            (
                source["source_key"],
                source["source_name"],
                source["source_url"],
                source["source_type"],
                source["ingestion_status"],
                source["notes"],
            ),
        )


def load_pairs(cursor) -> list[tuple[str, str]]:
    cursor.execute(
        """
        SELECT s.supplement_id, d.canonical_drug_id
        FROM supplement_map s
        CROSS JOIN canonical_drug_entities d
        ORDER BY s.supplement_id, d.canonical_drug_id
        """
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]


def seed_current_workbook_evidence(cursor) -> int:
    cursor.execute(
        """
        SELECT claim_id, supplement_id, supplement_canonical_ko,
               canonical_drug_id, drug_canonical_ko, drug_canonical_en,
               interaction_text_raw, source_url
        FROM standardized_interactions
        WHERE supplement_id IS NOT NULL
          AND canonical_drug_id IS NOT NULL
          AND interaction_text_raw IS NOT NULL
          AND interaction_text_raw <> ''
        """
    )
    rows = cursor.fetchall()
    now = datetime.now(UTC).replace(tzinfo=None)
    count = 0
    for row in rows:
        (
            claim_id,
            supplement_id,
            supplement_name,
            canonical_drug_id,
            drug_name_ko,
            drug_name_en,
            interaction_text,
            source_url,
        ) = row
        risk_level = _infer_level(interaction_text)
        evidence_id = stable_evidence_id(
            CURRENT_SOURCE_KEY,
            claim_id or "",
            supplement_id,
            canonical_drug_id,
            interaction_text,
        )
        cursor.execute(
            INSERT_EVIDENCE_SQL,
            (
                evidence_id,
                CURRENT_SOURCE_KEY,
                claim_id,
                supplement_id,
                supplement_name,
                canonical_drug_id,
                drug_name_ko or drug_name_en,
                risk_level,
                interaction_text,
                None,
                None,
                "curated_workbook",
                source_url,
                None,
                now,
            ),
        )
        count += 1
    return count


def count_evidence_by_source_pair(cursor, source_key: str) -> dict[tuple[str, str], int]:
    cursor.execute(
        """
        SELECT supplement_id, canonical_drug_id, COUNT(*) AS evidence_count
        FROM interaction_evidence_claims
        WHERE source_key = %s
        GROUP BY supplement_id, canonical_drug_id
        """,
        (source_key,),
    )
    return {(row[0], row[1]): int(row[2]) for row in cursor.fetchall()}


def write_current_source_checks(cursor, pairs: list[tuple[str, str]]) -> tuple[int, int]:
    evidence_counts = count_evidence_by_source_pair(cursor, CURRENT_SOURCE_KEY)
    now = datetime.now(UTC).replace(tzinfo=None)
    attention = 0
    no_claim = 0
    batch: list[tuple] = []
    for supplement_id, canonical_drug_id in pairs:
        evidence_count = evidence_counts.get((supplement_id, canonical_drug_id), 0)
        if evidence_count:
            attention += 1
            status = "attention_found"
            notes = "현재 정제 워크북에서 주의 claim 확인"
        else:
            no_claim += 1
            status = "no_claim_found"
            notes = "현재 정제 워크북에서 주의 claim 미탐지"
        batch.append((supplement_id, canonical_drug_id, CURRENT_SOURCE_KEY, status, evidence_count, now, notes))

    for index in range(0, len(batch), 1000):
        cursor.executemany(INSERT_SOURCE_CHECK_SQL, batch[index:index + 1000])
    return attention, no_claim


def write_pending_source_checks(cursor, pairs: list[tuple[str, str]]) -> int:
    planned_sources = [
        source["source_key"]
        for source in SOURCE_REGISTRY
        if source["source_key"] != CURRENT_SOURCE_KEY and source["ingestion_status"] == "planned"
    ]
    now = datetime.now(UTC).replace(tzinfo=None)
    total = 0
    batch: list[tuple] = []
    for source_key in planned_sources:
        for supplement_id, canonical_drug_id in pairs:
            batch.append(
                (
                    supplement_id,
                    canonical_drug_id,
                    source_key,
                    "pending_source_ingestion",
                    0,
                    now,
                    "소스 수집/정규화 파이프라인 추가 후 확인 예정",
                )
            )
            total += 1
            if len(batch) >= 1000:
                cursor.executemany(INSERT_PENDING_SOURCE_CHECK_SQL, batch)
                batch.clear()
    if batch:
        cursor.executemany(INSERT_PENDING_SOURCE_CHECK_SQL, batch)
    return total


def print_summary(cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM interaction_evidence_claims")
    evidence_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT source_key, check_status, COUNT(*)
        FROM interaction_pair_source_checks
        GROUP BY source_key, check_status
        ORDER BY source_key, check_status
        """
    )
    print(f"근거 claim 기록: {evidence_count}개")
    print("소스별 조합 확인 상태:")
    for source_key, status, count in cursor.fetchall():
        print(f"  - {source_key}: {status} {count}개")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-pending-source-checks",
        action="store_true",
        help="아직 수집 전인 외부소스도 조합별 pending 상태로 기록",
    )
    args = parser.parse_args()

    conn = get_conn()
    cursor = conn.cursor()
    try:
        ensure_tables(cursor)
        register_sources(cursor)
        evidence_rows = seed_current_workbook_evidence(cursor)
        pairs = load_pairs(cursor)
        attention, no_claim = write_current_source_checks(cursor, pairs)
        pending = write_pending_source_checks(cursor, pairs) if args.include_pending_source_checks else 0
        conn.commit()
        print(
            "완료: "
            f"전체 조합 {len(pairs)}개, "
            f"현재 워크북 근거 claim {evidence_rows}개, "
            f"주의 확인 {attention}개, 미탐지 {no_claim}개, "
            f"외부소스 pending 기록 {pending}개"
        )
        print_summary(cursor)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
