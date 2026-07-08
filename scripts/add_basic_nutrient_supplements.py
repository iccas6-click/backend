"""
기본 비타민/미네랄/영양소 성분을 supplement_map과 supplement_aliases에 보강한다.

이 스크립트는 상호작용 claim이 아직 없는 성분도 "성분으로는 인식"되도록
표준 성분 사전에 넣는다. 실제 주의 문구는 standardized_interactions에
별도 claim이 있을 때만 반환된다.

사용법:
    python scripts/add_basic_nutrient_supplements.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

CREATE_ALIAS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS supplement_aliases (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    supplement_id VARCHAR(50)  NOT NULL,
    alias         VARCHAR(255) NOT NULL,
    alias_type    ENUM('common','brand','scientific','individual_recognized') NOT NULL DEFAULT 'common',
    UNIQUE KEY uq_alias (alias),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

SOURCE_NAME = "CLICK 기본 영양소 매칭 사전"

# supplement_id, raw_name, canonical_ko, canonical_en, aliases
NUTRIENTS: list[tuple[str, str, str, str, list[str]]] = [
    ("NUTR_001", "비타민 C", "비타민 C", "Vitamin C", ["비타민C", "VitaminC", "아스코르브산", "Ascorbic acid", "L-아스코르브산"]),
    ("NUTR_002", "비타민 D", "비타민 D", "Vitamin D", ["비타민D", "VitaminD", "비타민 D3", "비타민D3", "콜레칼시페롤", "Cholecalciferol"]),
    ("NUTR_003", "비타민 E", "비타민 E", "Vitamin E", ["비타민E", "VitaminE", "토코페롤", "Tocopherol", "d-α-토코페롤"]),
    ("NUTR_004", "비타민 A", "비타민 A", "Vitamin A", ["비타민A", "VitaminA", "레티놀", "Retinol", "베타카로틴", "Beta-carotene"]),
    ("NUTR_005", "비타민 K", "비타민 K", "Vitamin K", ["비타민K", "VitaminK", "비타민 K1", "비타민K1", "비타민 K2", "비타민K2", "필로퀴논", "메나퀴논"]),
    ("NUTR_006", "비타민 B1", "비타민 B1", "Vitamin B1", ["비타민B1", "티아민", "티아민염산염", "Thiamine", "Thiamine hydrochloride"]),
    ("NUTR_007", "비타민 B2", "비타민 B2", "Vitamin B2", ["비타민B2", "리보플라빈", "리보플라빈부티레이트", "Riboflavin"]),
    ("NUTR_008", "나이아신", "나이아신", "Niacin", ["비타민 B3", "비타민B3", "니아신", "니코틴산", "니코틴산아미드", "Niacinamide", "Nicotinamide"]),
    ("NUTR_009", "판토텐산", "판토텐산", "Pantothenic acid", ["비타민 B5", "비타민B5", "판토텐산칼슘", "Pantothenate"]),
    ("NUTR_010", "비타민 B6", "비타민 B6", "Vitamin B6", ["비타민B6", "피리독신", "피리독신염산염", "Pyridoxine", "Pyridoxine hydrochloride"]),
    ("NUTR_011", "비오틴", "비오틴", "Biotin", ["비타민 B7", "비타민B7", "Vitamin B7", "VitaminB7"]),
    ("NUTR_012", "엽산", "엽산", "Folate", ["폴산", "비타민 B9", "비타민B9", "Folic acid", "Folate"]),
    ("NUTR_013", "비타민 B12", "비타민 B12", "Vitamin B12", ["비타민B12", "코발라민", "시아노코발라민", "Cobalamin", "Cyanocobalamin"]),
    ("NUTR_014", "칼슘", "칼슘", "Calcium", ["Calcium", "Ca", "구연산칼슘", "탄산칼슘", "해조칼슘"]),
    ("NUTR_015", "마그네슘", "마그네슘", "Magnesium", ["Magnesium", "Mg", "산화마그네슘", "구연산마그네슘"]),
    ("NUTR_016", "아연", "아연", "Zinc", ["Zinc", "Zn", "산화아연", "글루콘산아연"]),
    ("NUTR_017", "철", "철", "Iron", ["철분", "Iron", "Fe", "푸마르산제일철", "황산제일철"]),
    ("NUTR_018", "구리", "구리", "Copper", ["Copper", "Cu"]),
    ("NUTR_019", "망간", "망간", "Manganese", ["Manganese", "Mn"]),
    ("NUTR_020", "셀레늄", "셀레늄", "Selenium", ["Selenium", "Se", "셀렌"]),
    ("NUTR_021", "요오드", "요오드", "Iodine", ["Iodine", "I", "아이오딘", "요오드칼륨"]),
    ("NUTR_022", "크롬", "크롬", "Chromium", ["Chromium", "Cr", "크로뮴"]),
    ("NUTR_023", "몰리브덴", "몰리브덴", "Molybdenum", ["Molybdenum", "Mo"]),
    ("NUTR_024", "칼륨", "칼륨", "Potassium", ["Potassium", "K", "포타슘"]),
    ("NUTR_025", "인", "인", "Phosphorus", ["Phosphorus", "P", "인산"]),
    ("NUTR_026", "L-시스테인", "L-시스테인", "L-cysteine", ["시스테인", "L Cysteine", "L-Cysteine"]),
    ("NUTR_027", "L-테아닌", "L-테아닌", "L-theanine", ["테아닌", "L Theanine", "L-Theanine"]),
    ("NUTR_028", "루테인", "루테인", "Lutein", ["Lutein"]),
    ("NUTR_029", "지아잔틴", "지아잔틴", "Zeaxanthin", ["제아잔틴", "Zeaxanthin"]),
    ("NUTR_030", "콜라겐", "콜라겐", "Collagen", ["Collagen", "저분자콜라겐", "피쉬콜라겐"]),
    ("NUTR_031", "히알루론산", "히알루론산", "Hyaluronic acid", ["Hyaluronic acid", "히알루론산나트륨"]),
    ("NUTR_032", "MSM", "MSM", "Methylsulfonylmethane", ["엠에스엠", "식이유황", "Methylsulfonylmethane"]),
    ("NUTR_033", "식이섬유", "식이섬유", "Dietary fiber", ["난소화성말토덱스트린", "차전자피", "Psyllium", "Dietary fiber"]),
    ("NUTR_034", "가르시니아캄보지아", "가르시니아캄보지아", "Garcinia cambogia", ["가르시니아", "HCA", "Hydroxycitric acid"]),
    ("NUTR_035", "밀크칼슘", "밀크칼슘", "Milk calcium", ["유청칼슘", "Milk calcium"]),
    ("NUTR_036", "멀티비타민", "멀티비타민", "Multivitamin", ["멀티 비타민", "종합비타민", "종합 비타민", "Multivitamin", "고려은단 멀티비타민 이뮨샷"]),
]


def main() -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(CREATE_ALIAS_TABLE_SQL)

        inserted_map = 0
        updated_map = 0
        inserted_alias = 0
        skipped_alias = 0

        for supplement_id, raw_name, canonical_ko, canonical_en, aliases in NUTRIENTS:
            cursor.execute(
                """
                INSERT INTO supplement_map (
                    supplement_id, raw_name, canonical_name_ko, canonical_name_en,
                    scientific_name, entity_type, mapping_status, mapping_basis,
                    source_name, source_url, notes
                )
                VALUES (%s, %s, %s, %s, NULL, 'NUTRIENT', 'BASIC_DICTIONARY',
                        'Basic nutrient dictionary for frontend/AI ingredient matching',
                        %s, NULL, '상호작용 claim 유무와 별개로 성분명 매칭을 위해 추가')
                ON DUPLICATE KEY UPDATE
                    raw_name = VALUES(raw_name),
                    canonical_name_ko = VALUES(canonical_name_ko),
                    canonical_name_en = VALUES(canonical_name_en),
                    entity_type = VALUES(entity_type),
                    mapping_status = VALUES(mapping_status),
                    mapping_basis = VALUES(mapping_basis),
                    source_name = VALUES(source_name),
                    notes = VALUES(notes)
                """,
                (supplement_id, raw_name, canonical_ko, canonical_en, SOURCE_NAME),
            )
            if cursor.rowcount == 1:
                inserted_map += 1
            elif cursor.rowcount == 2:
                updated_map += 1

            alias_values = {raw_name, canonical_ko, canonical_en, *aliases}
            for alias in sorted(value.strip() for value in alias_values if value and value.strip()):
                cursor.execute(
                    """
                    INSERT IGNORE INTO supplement_aliases (supplement_id, alias, alias_type)
                    VALUES (%s, %s, 'common')
                    """,
                    (supplement_id, alias),
                )
                if cursor.rowcount:
                    inserted_alias += 1
                else:
                    skipped_alias += 1

        conn.commit()
        print(
            "완료: "
            f"supplement_map 추가 {inserted_map}건, 갱신 {updated_map}건, "
            f"alias 추가 {inserted_alias}건, 중복 스킵 {skipped_alias}건"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
