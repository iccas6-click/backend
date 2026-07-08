"""
프론트/AI가 인식한 흔한 알약 유효성분을 canonical_drug_entities에 보강한다.

상호작용 claim이 아직 없어도 약물/성분명 자체는 매칭되어야 하므로,
기본 약물 성분 사전으로 사용한다.

사용법:
    python scripts/add_basic_drug_entities.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

SOURCE_NAME = "CLICK 기본 약물 성분 매칭 사전"

# id, ko, en, aliases
DRUGS: list[tuple[str, str, str, list[str]]] = [
    ("DRUG_BASIC_001", "텔미사르탄", "Telmisartan", ["telmisartan"]),
    ("DRUG_BASIC_002", "암로디핀", "Amlodipine", ["amlodipine", "에스암로디핀", "에스암로디핀베실산염", "에스암로디핀베실산염이수화물", "S-amlodipine"]),
    ("DRUG_BASIC_003", "노스카핀", "Noscapine", ["noscapine"]),
    ("DRUG_BASIC_004", "메틸에페드린", "Methylephedrine", ["dl-메틸에페드린염산염", "메틸에페드린염산염", "Methylephedrine hydrochloride"]),
    ("DRUG_BASIC_005", "카르비녹사민", "Carbinoxamine", ["카르비녹사민말레산염", "Carbinoxamine maleate"]),
    ("DRUG_BASIC_006", "구아야콜설폰산칼륨", "Potassium guaiacolsulfonate", ["구아야콜설폰산칼륨", "Potassium guaiacolsulfonate"]),
    ("DRUG_BASIC_007", "덱스트로메토르판", "Dextromethorphan", ["덱스트로메토르판브롬화수소산염수화물", "덱스트로메토르판브롬화수소산염", "Dextromethorphan hydrobromide"]),
    ("DRUG_BASIC_008", "구아이페네신", "Guaifenesin", ["구아이페네신", "Guaifenesin"]),
    ("DRUG_BASIC_009", "클로르페니라민", "Chlorpheniramine", ["클로르페니라민말레산염", "Chlorpheniramine maleate"]),
    ("DRUG_BASIC_010", "카페인", "Caffeine", ["카페인무수물", "무수카페인", "Caffeine anhydrous"]),
    ("DRUG_BASIC_011", "은행엽건조엑스", "Ginkgo leaf extract", ["은행엽건조엑스", "은행잎건조엑스", "Ginkgo biloba extract"]),
    ("DRUG_BASIC_012", "디아스타제", "Diastase", ["Diastase"]),
    ("DRUG_BASIC_013", "프로테아제", "Protease", ["Protease"]),
    ("DRUG_BASIC_014", "셀룰라제", "Cellulase", ["Cellulase"]),
    ("DRUG_BASIC_015", "우담즙건조엑스", "Dried ox bile extract", ["우담즙건조엑스", "Ox bile extract"]),
    ("DRUG_BASIC_016", "글리시리진산암모늄", "Ammonium glycyrrhizinate", ["글리시리진산암모늄", "Ammonium glycyrrhizinate"]),
    ("DRUG_BASIC_017", "리보플라빈", "Riboflavin", ["리보플라빈부티레이트", "비타민 B2", "비타민B2", "Riboflavin butyrate"]),
    ("DRUG_BASIC_018", "피리독신", "Pyridoxine", ["피리독신염산염", "비타민 B6", "비타민B6", "Pyridoxine hydrochloride"]),
    ("DRUG_BASIC_019", "니코틴산아미드", "Nicotinamide", ["나이아신아미드", "Niacinamide", "Nicotinamide"]),
    ("DRUG_BASIC_020", "비오틴", "Biotin", ["Biotin", "비타민 B7", "비타민B7"]),
    ("DRUG_BASIC_021", "L-시스테인", "L-cysteine", ["시스테인", "L Cysteine", "L-Cysteine"]),
    ("DRUG_BASIC_022", "L-카르니틴", "L-carnitine", ["dl-카르니틴염산염", "카르니틴", "Carnitine", "L-carnitine hydrochloride"]),
    ("DRUG_BASIC_023", "티아민", "Thiamine", ["티아민염산염", "비타민 B1", "비타민B1", "Thiamine hydrochloride"]),
]


def main() -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        inserted = 0
        updated = 0
        for drug_id, ko, en, aliases in DRUGS:
            raw_aliases = ", ".join(sorted({ko, en, *aliases}))
            cursor.execute(
                """
                INSERT INTO canonical_drug_entities (
                    canonical_drug_id, entity_level, canonical_name_ko, canonical_name_en,
                    alias_count, raw_aliases, rxcui, atc_code, unii, kr_ingredient_code,
                    external_id_status, mapping_status, verification_source_name,
                    verification_source_url, notes
                )
                VALUES (%s, 'INGREDIENT', %s, %s, %s, %s, NULL, NULL, NULL, NULL,
                        'NOT_VERIFIED', 'BASIC_DICTIONARY', %s, NULL,
                        '프론트/AI 인식 결과의 성분명 매칭을 위해 추가')
                ON DUPLICATE KEY UPDATE
                    canonical_name_ko = VALUES(canonical_name_ko),
                    canonical_name_en = VALUES(canonical_name_en),
                    alias_count = VALUES(alias_count),
                    raw_aliases = VALUES(raw_aliases),
                    mapping_status = VALUES(mapping_status),
                    verification_source_name = VALUES(verification_source_name),
                    notes = VALUES(notes)
                """,
                (drug_id, ko, en, len(set(aliases)), raw_aliases, SOURCE_NAME),
            )
            if cursor.rowcount == 1:
                inserted += 1
            elif cursor.rowcount == 2:
                updated += 1

        conn.commit()
        print(f"완료: canonical_drug_entities 추가 {inserted}건, 갱신 {updated}건")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
