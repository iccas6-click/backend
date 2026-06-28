"""
supplement_aliases 테이블 생성 및 alias 데이터 투입 스크립트.
사용법: python scripts/add_supplement_aliases.py
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.connection import get_conn

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS supplement_aliases (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    supplement_id VARCHAR(50)  NOT NULL,
    alias         VARCHAR(255) NOT NULL,
    alias_type    ENUM('common', 'brand', 'scientific', 'individual_recognized') NOT NULL DEFAULT 'common',
    UNIQUE KEY uq_alias (alias),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

# (supplement_id, alias, alias_type)
ALIASES: list[tuple[str, str, str]] = [
    # SUPP_001 인삼
    ("SUPP_001", "홍삼", "common"),
    ("SUPP_001", "홍삼추출물", "common"),
    ("SUPP_001", "인삼추출물", "common"),
    ("SUPP_001", "홍삼분말", "common"),
    ("SUPP_001", "Korean red ginseng", "common"),
    ("SUPP_001", "Red ginseng", "common"),
    ("SUPP_001", "Panax ginseng", "scientific"),

    # SUPP_002 프로바이오틱스
    ("SUPP_002", "유산균", "common"),
    ("SUPP_002", "Lactobacillus", "scientific"),
    ("SUPP_002", "Bifidobacterium", "scientific"),
    ("SUPP_002", "락토바실러스", "common"),
    ("SUPP_002", "비피도박테리움", "common"),
    ("SUPP_002", "TWK10", "individual_recognized"),
    ("SUPP_002", "Lactiplantibacillus plantarum TWK10", "individual_recognized"),
    ("SUPP_002", "Lactobacillus plantarum TWK10", "individual_recognized"),
    ("SUPP_002", "Lactobacillus sakei Probio65", "individual_recognized"),
    ("SUPP_002", "Bifidobacterium breve B-3", "individual_recognized"),
    ("SUPP_002", "HY7714", "individual_recognized"),
    ("SUPP_002", "드시모네", "brand"),
    ("SUPP_002", "리스펙타", "brand"),
    ("SUPP_002", "L. curvatus HY7601", "individual_recognized"),
    ("SUPP_002", "L. plantarum KY1032", "individual_recognized"),

    # SUPP_003 알로에
    ("SUPP_003", "알로에베라", "common"),
    ("SUPP_003", "알로에겔", "common"),
    ("SUPP_003", "알로에추출물", "common"),
    ("SUPP_003", "Aloe vera", "scientific"),

    # SUPP_004 오메가-3
    ("SUPP_004", "오메가3", "common"),
    ("SUPP_004", "오메가-3", "common"),
    ("SUPP_004", "EPA", "common"),
    ("SUPP_004", "DHA", "common"),
    ("SUPP_004", "피쉬오일", "common"),
    ("SUPP_004", "어유", "common"),
    ("SUPP_004", "피시오일", "common"),
    ("SUPP_004", "EPA 및 DHA", "common"),

    # SUPP_005 밀크씨슬
    ("SUPP_005", "실리마린", "common"),
    ("SUPP_005", "밀크시슬", "common"),
    ("SUPP_005", "카르두스마리아누스", "common"),
    ("SUPP_005", "엉겅퀴", "common"),
    ("SUPP_005", "Silybum marianum", "scientific"),

    # SUPP_006 감마리놀렌산
    ("SUPP_006", "달맞이꽃종자유", "common"),
    ("SUPP_006", "GLA", "common"),
    ("SUPP_006", "보리지오일", "common"),
    ("SUPP_006", "감마리놀렌산", "common"),

    # SUPP_007 당귀
    ("SUPP_007", "당귀추출물", "common"),
    ("SUPP_007", "당귀분말", "common"),
    ("SUPP_007", "Angelica gigas", "scientific"),

    # SUPP_008 마테
    ("SUPP_008", "마테차", "common"),
    ("SUPP_008", "예르바마테", "common"),
    ("SUPP_008", "Ilex paraguariensis", "scientific"),

    # SUPP_009 돌외잎
    ("SUPP_009", "돌외잎추출물", "common"),
    ("SUPP_009", "교소란", "common"),
    ("SUPP_009", "지피노사이드", "common"),
    ("SUPP_009", "Gynostemma pentaphyllum", "scientific"),

    # SUPP_010 대두
    ("SUPP_010", "이소플라본", "common"),
    ("SUPP_010", "대두이소플라본", "common"),
    ("SUPP_010", "콩이소플라본", "common"),
    ("SUPP_010", "Glycine max", "scientific"),

    # SUPP_011 L-카르니틴
    ("SUPP_011", "카르니틴", "common"),
    ("SUPP_011", "Carnitine", "common"),
    ("SUPP_011", "엘카르니틴", "common"),
    ("SUPP_011", "L-Carnitine", "common"),

    # SUPP_012 녹차
    ("SUPP_012", "녹차추출물", "common"),
    ("SUPP_012", "카테킨", "common"),
    ("SUPP_012", "EGCG", "common"),
    ("SUPP_012", "녹차폴리페놀", "common"),
    ("SUPP_012", "Camellia sinensis", "scientific"),

    # SUPP_013 키토산/키토올리고당
    ("SUPP_013", "키토올리고당", "individual_recognized"),
    ("SUPP_013", "키토산", "common"),
    ("SUPP_013", "Chitosan", "common"),
    ("SUPP_013", "chitooligosaccharide", "common"),

    # SUPP_014 스피루리나
    ("SUPP_014", "스피루리나분말", "common"),
    ("SUPP_014", "Arthrospira", "scientific"),
    ("SUPP_014", "Spirulina", "common"),

    # SUPP_015 글루코사민
    ("SUPP_015", "글루코사민염산염", "common"),
    ("SUPP_015", "글루코사민황산염", "common"),
    ("SUPP_015", "N-아세틸글루코사민", "common"),
    ("SUPP_015", "Glucosamine", "common"),

    # SUPP_016 석류
    ("SUPP_016", "석류농축액", "individual_recognized"),
    ("SUPP_016", "석류추출물", "common"),
    ("SUPP_016", "석류분말", "common"),
    ("SUPP_016", "엘라그산", "common"),
    ("SUPP_016", "Ellagic acid", "common"),
    ("SUPP_016", "Punica granatum", "scientific"),

    # SUPP_017 가시오갈피
    ("SUPP_017", "가시오가피", "common"),
    ("SUPP_017", "가시오갈피추출물", "common"),
    ("SUPP_017", "시베리아인삼", "common"),
    ("SUPP_017", "Eleutherococcus senticosus", "scientific"),

    # SUPP_018 아프리카망고
    ("SUPP_018", "아프리카 망고", "common"),
    ("SUPP_018", "아프리카망고추출물", "common"),
    ("SUPP_018", "Irvingia gabonensis", "scientific"),

    # SUPP_019 클로렐라
    ("SUPP_019", "클로렐라분말", "common"),
    ("SUPP_019", "Chlorella", "scientific"),

    # SUPP_020 공액리놀레산
    ("SUPP_020", "CLA", "common"),
    ("SUPP_020", "공액리놀레산유지", "common"),
    ("SUPP_020", "Conjugated linoleic acid", "common"),

    # SUPP_021 코엔자임 Q10
    ("SUPP_021", "코큐텐", "common"),
    ("SUPP_021", "CoQ10", "common"),
    ("SUPP_021", "유비퀴논", "common"),
    ("SUPP_021", "유비퀴놀", "common"),
    ("SUPP_021", "코엔자임Q10", "common"),

    # SUPP_022 은행잎
    ("SUPP_022", "은행잎추출물", "common"),
    ("SUPP_022", "징코", "common"),
    ("SUPP_022", "진코", "common"),
    ("SUPP_022", "Ginkgo biloba", "scientific"),
    ("SUPP_022", "Ginkgo", "common"),

    # SUPP_023 쏘팔메토
    ("SUPP_023", "쏘팔메토추출물", "common"),
    ("SUPP_023", "소팔메토", "common"),
    ("SUPP_023", "Serenoa repens", "scientific"),
    ("SUPP_023", "Saw palmetto", "common"),

    # SUPP_024 포스파티딜세린
    ("SUPP_024", "PS", "common"),
    ("SUPP_024", "Phosphatidylserine", "common"),

    # SUPP_025 크랜베리
    ("SUPP_025", "크랜베리추출물", "common"),
    ("SUPP_025", "크렌베리", "common"),
    ("SUPP_025", "Vaccinium macrocarpon", "scientific"),
    ("SUPP_025", "Cranberry", "common"),

    # SUPP_026 감초
    ("SUPP_026", "감초추출물", "common"),
    ("SUPP_026", "스페인감초추출물", "individual_recognized"),
    ("SUPP_026", "리코리스", "common"),
    ("SUPP_026", "Glycyrrhiza", "scientific"),
    ("SUPP_026", "Licorice", "common"),

    # SUPP_027 울금(커큐민)
    ("SUPP_027", "커큐민", "common"),
    ("SUPP_027", "강황", "common"),
    ("SUPP_027", "터메릭", "common"),
    ("SUPP_027", "울금추출물", "common"),
    ("SUPP_027", "Curcumin", "common"),
    ("SUPP_027", "Turmeric", "common"),
    ("SUPP_027", "울금[커큐민]", "common"),
    ("SUPP_027", "울금 [커큐민]", "common"),

    # SUPP_028 마늘
    ("SUPP_028", "마늘추출물", "common"),
    ("SUPP_028", "마늘분말", "common"),
    ("SUPP_028", "알리신", "common"),
    ("SUPP_028", "흑마늘", "common"),
    ("SUPP_028", "흑마늘추출물", "common"),
    ("SUPP_028", "Allicin", "common"),
    ("SUPP_028", "Garlic", "common"),

    # SUPP_029 오미자
    ("SUPP_029", "오미자추출물", "individual_recognized"),
    ("SUPP_029", "오미자분말", "common"),
    ("SUPP_029", "오미자베리", "common"),
    ("SUPP_029", "Schisandra", "scientific"),

    # SUPP_030 호로파 종자
    ("SUPP_030", "호로파", "common"),
    ("SUPP_030", "호로파종자추출물", "common"),
    ("SUPP_030", "Fenugreek", "common"),
    ("SUPP_030", "Trigonella foenum-graecum", "scientific"),

    # SUPP_031 루바브뿌리
    ("SUPP_031", "루바브", "common"),
    ("SUPP_031", "대황", "common"),
    ("SUPP_031", "Rhubarb", "common"),
    ("SUPP_031", "Rheum", "scientific"),

    # SUPP_032 글루코사민-콘드로이틴
    ("SUPP_032", "콘드로이틴", "common"),
    ("SUPP_032", "콘드로이친", "common"),
    ("SUPP_032", "글루코사민콘드로이틴", "common"),
    ("SUPP_032", "Chondroitin", "common"),

    # SUPP_033 인동덩굴
    ("SUPP_033", "인동덩굴추출물", "common"),
    ("SUPP_033", "인동덩굴꽃봉오리추출물", "individual_recognized"),
    ("SUPP_033", "그린세라-F", "brand"),
    ("SUPP_033", "인동", "common"),
    ("SUPP_033", "금은화", "common"),
    ("SUPP_033", "Lonicera japonica", "scientific"),
]


def main():
    conn = get_conn()
    cursor = conn.cursor()

    print("supplement_aliases 테이블 생성 중...")
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()

    print(f"alias {len(ALIASES)}건 투입 중...")
    inserted = 0
    skipped = 0
    for supp_id, alias, alias_type in ALIASES:
        try:
            cursor.execute(
                "INSERT IGNORE INTO supplement_aliases (supplement_id, alias, alias_type) VALUES (%s, %s, %s)",
                (supp_id, alias, alias_type),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [WARN] {alias}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"완료: 투입 {inserted}건, 중복 스킵 {skipped}건")


if __name__ == "__main__":
    main()
