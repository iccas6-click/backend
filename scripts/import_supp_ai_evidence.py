"""
Supp.ai 공개 데이터셋을 현 DB 성분 조합에 매칭해 외부 근거 claim으로 적재한다.

입력 데이터:
    https://supp.ai/ 에서 공개한 bulk dataset
    - cui_metadata.json
    - sentence_dict.json
    - paper_metadata.json

사용법:
    python scripts/import_supp_ai_evidence.py --data-dir /path/to/extracted/supp_ai
    python scripts/import_supp_ai_evidence.py --archive /tmp/supp_ai.tar.gz --data-dir /tmp/supp_ai
    python scripts/import_supp_ai_evidence.py --download
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

SOURCE_KEY = "supp_ai"
DATASET_URL = "https://storage.googleapis.com/uw-supp-ai-data/20211020_01.tar.gz"

SUPPLEMENT_ALIASES_KO = {
    "인삼": ["Ginseng", "Panax ginseng", "Korean ginseng"],
    "녹차": ["Green Tea Extract", "Green Tea"],
    "은행잎": ["Ginkgo Biloba Whole", "Ginkgo biloba", "Ginkgo"],
    "크랜베리": ["Cranberry", "Vaccinium macrocarpon"],
    "대두": ["Soy Isoflavones", "Soy"],
    "울금": ["Turmeric", "Curcumin"],
    "커큐민": ["Turmeric", "Curcumin"],
    "오메가3": ["Fatty Acids, Omega-3", "Omega-3 Fatty Acids", "Fish Oils"],
    "프로바이오틱스": ["Probiotics"],
    "밀크씨슬": ["Milk Thistle Extract", "Silybum marianum", "Milk Thistle"],
    "감초": ["Licorice", "Glycyrrhiza"],
    "마늘": ["Garlic"],
    "비타민 C": ["Vitamin C", "Ascorbic Acid"],
    "비타민 D": ["Vitamin D", "Cholecalciferol"],
    "비타민 E": ["Vitamin E", "Tocopherol"],
    "비타민 A": ["Vitamin A", "Retinol"],
    "비타민 K": ["Vitamin K"],
    "비타민 B1": ["Thiamine"],
    "비타민 B2": ["Riboflavin"],
    "비타민 B6": ["Pyridoxine"],
    "비타민 B12": ["Vitamin B 12", "Cobalamin"],
    "나이아신": ["Niacin"],
    "판토텐산": ["Pantothenic acid"],
    "비오틴": ["Biotin"],
    "엽산": ["Folic Acid", "Folate"],
    "칼슘": ["Calcium"],
    "마그네슘": ["Magnesium"],
    "아연": ["Zinc"],
    "철": ["Iron"],
    "구리": ["Copper"],
    "망간": ["Manganese"],
    "셀레늄": ["Selenium"],
    "요오드": ["Iodine"],
    "칼륨": ["Potassium"],
}

DRUG_ALIASES_KO = {
    "은행엽건조엑스": ["Ginkgo Biloba Whole", "Ginkgo biloba", "Ginkgo"],
    "아스코르브산": ["Ascorbic Acid", "Vitamin C"],
    "토코페롤": ["Vitamin E", "Tocopherol"],
    "토코페롤아세테이트": ["Vitamin E", "Tocopherol"],
    "리보플라빈": ["Riboflavin"],
    "피리독신": ["Pyridoxine"],
    "니코틴산아미드": ["Nicotinamide", "Niacinamide"],
    "티아민": ["Thiamine"],
    "비오틴": ["Biotin"],
    "L-시스테인": ["Cysteine"],
    "L-카르니틴": ["Carnitine"],
    "커큐민": ["Curcumin"],
    "오메가": ["Fatty Acids, Omega-3"],
}

CREATE_EXTERNAL_MAPPING_SQL = """
CREATE TABLE IF NOT EXISTS external_agent_mappings (
    source_key VARCHAR(80) NOT NULL,
    local_entity_type VARCHAR(50) NOT NULL,
    local_entity_id VARCHAR(50) NOT NULL,
    local_name VARCHAR(255),
    external_id VARCHAR(100) NOT NULL,
    external_name VARCHAR(255),
    external_entity_type VARCHAR(50),
    match_status VARCHAR(100) NOT NULL,
    match_basis TEXT,
    matched_alias VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (source_key, local_entity_type, local_entity_id, external_id),
    KEY idx_external_mapping_local (local_entity_type, local_entity_id),
    KEY idx_external_mapping_external (source_key, external_id),
    FOREIGN KEY (source_key) REFERENCES interaction_source_registry(source_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

ENSURE_SUPP_AI_SOURCE_SQL = """
INSERT INTO interaction_source_registry (
    source_key, source_name, source_url, source_type, ingestion_status, notes
)
VALUES (
    'supp_ai',
    'Supp.ai',
    'https://supp.ai/',
    'external_dataset',
    'ingested',
    'Supp.ai 2021-10-20 공개 bulk dataset의 evidence sentence를 현 DB 성분 조합에 매칭'
)
ON DUPLICATE KEY UPDATE
    ingestion_status = 'ingested',
    notes = VALUES(notes)
"""

INSERT_MAPPING_SQL = """
INSERT INTO external_agent_mappings (
    source_key, local_entity_type, local_entity_id, local_name,
    external_id, external_name, external_entity_type,
    match_status, match_basis, matched_alias
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    local_name = VALUES(local_name),
    external_name = VALUES(external_name),
    external_entity_type = VALUES(external_entity_type),
    match_status = VALUES(match_status),
    match_basis = VALUES(match_basis),
    matched_alias = VALUES(matched_alias)
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
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def split_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,|;/]", value) if item.strip()]


def download_dataset(archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and archive_path.stat().st_size > 0:
        return
    print(f"Supp.ai dataset 다운로드: {DATASET_URL}")
    urllib.request.urlretrieve(DATASET_URL, archive_path)


def extract_dataset(archive_path: Path, data_dir: Path) -> None:
    expected = data_dir / "cui_metadata.json"
    if expected.exists():
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(data_dir)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def agent_names(agent: dict) -> list[str]:
    values = [agent.get("preferred_name", "")]
    values.extend(agent.get("synonyms") or [])
    values.extend(agent.get("tradenames") or [])
    return [value for value in values if value]


def build_agent_index(cui_metadata: dict, allowed_types: set[str]) -> dict[str, list[tuple[str, dict, str]]]:
    index: dict[str, list[tuple[str, dict, str]]] = defaultdict(list)
    for cui, agent in cui_metadata.items():
        if agent.get("ent_type") not in allowed_types:
            continue
        for name in agent_names(agent):
            normalized = normalize_name(name)
            if normalized:
                index[normalized].append((cui, agent, name))
    return index


def best_agent_matches(names: list[str], index: dict[str, list[tuple[str, dict, str]]]) -> list[tuple[str, dict, str]]:
    seen: set[str] = set()
    matches: list[tuple[str, dict, str]] = []
    for name in names:
        normalized = normalize_name(name)
        if not normalized:
            continue
        for cui, agent, matched_alias in index.get(normalized, []):
            if cui not in seen:
                seen.add(cui)
                matches.append((cui, agent, matched_alias))
    return matches


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


def supplement_candidate_names(row: dict) -> list[str]:
    names = [row.get("canonical_name_en"), row.get("raw_name")]
    ko = row.get("canonical_name_ko") or ""
    for key, aliases in SUPPLEMENT_ALIASES_KO.items():
        if key in ko:
            names.extend(aliases)
    return [name for name in names if name]


def drug_candidate_names(row: dict) -> list[str]:
    names = [row.get("canonical_name_en")]
    names.extend(split_aliases(row.get("raw_aliases")))
    ko = row.get("canonical_name_ko") or ""
    for key, aliases in DRUG_ALIASES_KO.items():
        if key in ko:
            names.extend(aliases)
    return [name for name in names if name]


def classify_risk(sentence: str, paper: dict | None) -> str:
    text = sentence.lower()
    danger_keywords = [
        "bleeding",
        "hemorrhage",
        "haemorrhage",
        "toxicity",
        "toxic",
        "fatal",
        "death",
        "contraindicated",
        "severe",
        "adverse",
        "inhibit",
        "increase the risk",
    ]
    if any(keyword in text for keyword in danger_keywords):
        return "danger"
    if paper and paper.get("clinical_study"):
        return "caution"
    return "caution"


def evidence_grade(paper: dict | None) -> str:
    if not paper:
        return "supp_ai_literature_sentence"
    if paper.get("retraction"):
        return "supp_ai_retracted_paper"
    if paper.get("clinical_study"):
        return "supp_ai_clinical_study_sentence"
    if paper.get("human_study"):
        return "supp_ai_human_study_sentence"
    if paper.get("animal_study"):
        return "supp_ai_animal_study_sentence"
    return "supp_ai_literature_sentence"


def evidence_source_url(paper: dict | None) -> str:
    if not paper:
        return "https://supp.ai/"
    if paper.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/"
    if paper.get("doi"):
        return f"https://doi.org/{paper['doi']}"
    return "https://supp.ai/"


def stable_evidence_id(interaction_id: str, uid: str | int, supplement_id: str, drug_id: str) -> str:
    return f"SUPPAI_{interaction_id}_{uid}_{supplement_id}_{drug_id}"[:100]


def write_mappings(cursor, local_type: str, local_id_key: str, rows: list[dict], matches_by_local: dict[str, list[tuple[str, dict, str]]]) -> None:
    batch = []
    for row in rows:
        local_id = row[local_id_key]
        local_name = row.get("canonical_name_ko") or row.get("canonical_name_en") or row.get("raw_name")
        for cui, agent, matched_alias in matches_by_local.get(local_id, []):
            batch.append(
                (
                    SOURCE_KEY,
                    local_type,
                    local_id,
                    local_name,
                    cui,
                    agent.get("preferred_name"),
                    agent.get("ent_type"),
                    "matched_exact_alias",
                    "정규화된 영문명/alias exact match",
                    matched_alias,
                )
            )
    for index in range(0, len(batch), 1000):
        cursor.executemany(INSERT_MAPPING_SQL, batch[index:index + 1000])


def find_interaction_id(supp_cui: str, drug_cui: str, sentence_dict: dict) -> str | None:
    first = f"{drug_cui}-{supp_cui}"
    if first in sentence_dict:
        return first
    second = f"{supp_cui}-{drug_cui}"
    if second in sentence_dict:
        return second
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("/tmp/click_supp_ai"))
    parser.add_argument("--archive", type=Path, default=Path("/tmp/click_supp_ai.tar.gz"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--max-sentences-per-pair", type=int, default=5)
    args = parser.parse_args()

    if args.download:
        download_dataset(args.archive)
        extract_dataset(args.archive, args.data_dir)

    required = ["cui_metadata.json", "sentence_dict.json", "paper_metadata.json"]
    missing = [name for name in required if not (args.data_dir / name).exists()]
    if missing:
        raise SystemExit(f"Supp.ai 데이터 파일 없음: {missing}. --download 또는 --data-dir 확인 필요")

    cui_metadata = load_json(args.data_dir / "cui_metadata.json")
    sentence_dict = load_json(args.data_dir / "sentence_dict.json")
    paper_metadata = load_json(args.data_dir / "paper_metadata.json")

    supplement_index = build_agent_index(cui_metadata, {"supplement", "drug"})
    drug_index = build_agent_index(cui_metadata, {"drug", "supplement"})

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    plain_cursor = conn.cursor()
    try:
        plain_cursor.execute(CREATE_EXTERNAL_MAPPING_SQL)
        plain_cursor.execute(ENSURE_SUPP_AI_SOURCE_SQL)

        supplements = load_supplements(cursor)
        drugs = load_drugs(cursor)

        supp_matches: dict[str, list[tuple[str, dict, str]]] = {}
        for supplement in supplements:
            matches = best_agent_matches(supplement_candidate_names(supplement), supplement_index)
            if matches:
                supp_matches[supplement["supplement_id"]] = matches

        drug_matches: dict[str, list[tuple[str, dict, str]]] = {}
        for drug in drugs:
            matches = best_agent_matches(drug_candidate_names(drug), drug_index)
            if matches:
                drug_matches[drug["canonical_drug_id"]] = matches

        write_mappings(plain_cursor, "supplement", "supplement_id", supplements, supp_matches)
        write_mappings(plain_cursor, "drug", "canonical_drug_id", drugs, drug_matches)

        now = datetime.now(UTC).replace(tzinfo=None)
        checks: list[tuple] = []
        evidence_rows: list[tuple] = []
        pairs_with_evidence = 0

        for supplement in supplements:
            supplement_id = supplement["supplement_id"]
            supplement_name = supplement["canonical_name_ko"] or supplement["canonical_name_en"]
            supplement_agents = supp_matches.get(supplement_id, [])

            for drug in drugs:
                drug_id = drug["canonical_drug_id"]
                drug_name = drug["canonical_name_ko"] or drug["canonical_name_en"]
                drug_agents = drug_matches.get(drug_id, [])
                pair_evidence_count = 0

                for supp_cui, _supp_agent, _supp_alias in supplement_agents:
                    for drug_cui, _drug_agent, _drug_alias in drug_agents:
                        interaction_id = find_interaction_id(supp_cui, drug_cui, sentence_dict)
                        if not interaction_id:
                            continue
                        sentences = sentence_dict.get(interaction_id, [])[: args.max_sentences_per_pair]
                        for sentence_row in sentences:
                            sentence = sentence_row.get("sentence") or ""
                            if not sentence:
                                continue
                            paper = paper_metadata.get(str(sentence_row.get("paper_id"))) or {}
                            uid = sentence_row.get("uid") or f"{interaction_id}-{pair_evidence_count}"
                            raw_payload = {
                                "interaction_id": interaction_id,
                                "sentence": sentence_row,
                                "paper": paper,
                                "supp_ai_supplement_cui": supp_cui,
                                "supp_ai_drug_cui": drug_cui,
                            }
                            evidence_rows.append(
                                (
                                    stable_evidence_id(interaction_id, uid, supplement_id, drug_id),
                                    SOURCE_KEY,
                                    str(uid),
                                    supplement_id,
                                    supplement_name,
                                    drug_id,
                                    drug_name,
                                    classify_risk(sentence, paper),
                                    sentence,
                                    None,
                                    None,
                                    evidence_grade(paper),
                                    evidence_source_url(paper),
                                    json.dumps(raw_payload, ensure_ascii=False),
                                    now,
                                )
                            )
                            pair_evidence_count += 1

                if pair_evidence_count:
                    pairs_with_evidence += 1
                    checks.append(
                        (
                            supplement_id,
                            drug_id,
                            SOURCE_KEY,
                            "attention_found",
                            pair_evidence_count,
                            now,
                            "Supp.ai 문헌 evidence sentence 매칭",
                        )
                    )
                else:
                    status = "no_claim_found" if supplement_agents and drug_agents else "unmatched_agent"
                    checks.append(
                        (
                            supplement_id,
                            drug_id,
                            SOURCE_KEY,
                            status,
                            0,
                            now,
                            "Supp.ai CUI 매칭 후 evidence 미탐지" if status == "no_claim_found" else "Supp.ai CUI 매칭 실패",
                        )
                    )

        for index in range(0, len(evidence_rows), 1000):
            plain_cursor.executemany(INSERT_EVIDENCE_SQL, evidence_rows[index:index + 1000])
        for index in range(0, len(checks), 1000):
            plain_cursor.executemany(INSERT_SOURCE_CHECK_SQL, checks[index:index + 1000])

        conn.commit()
        print(
            "완료: "
            f"Supp.ai supplement 매칭 {len(supp_matches)}/{len(supplements)}개, "
            f"drug 매칭 {len(drug_matches)}/{len(drugs)}개, "
            f"evidence 조합 {pairs_with_evidence}개, "
            f"evidence 문장 {len(evidence_rows)}개"
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
