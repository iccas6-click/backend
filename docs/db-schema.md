# DB 스키마 명세

drug-supplement schema v3 기준

---

## DB 구성

| DB | 포트 | 담당 |
|---|---|---|
| `click_db` (AI DB) | 3306 | 건기식/알약 제품 조회 |
| `click_backend_db` (Backend DB) | 3307 | 상호작용 조회 |

---

## AI DB (`click_db`)

### `supplement_info`
식약처 MFDS 건기식 제품 마스터 (44,885건). 컬럼명은 식약처 원문 기준.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | INT PK | 제품 고유 ID |
| `sttemnt_no` | VARCHAR(30) UQ | 품목제조신고번호 |
| `prduct` | VARCHAR(200) | 제품명 원문 |
| `entrps` | VARCHAR(200) | 업체명 |
| `main_fnctn` | TEXT | 주요기능 (성분 텍스트) |
| `base_standard` | TEXT | 기준규격 |
| `product_image_url` | TEXT | 공식 이미지 URL |

### `supplement_product_markers`
건기식 제품 ↔ 표준 보충제 연결. `supplement_id`는 Backend DB `supplement_entities` 참조.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `marker_id` | BIGINT PK | |
| `supplement_info_id` | INT FK | → supplement_info.id |
| `marker_text` | VARCHAR(500) | 매칭된 원문 마커 |
| `marker_text_normalized` | VARCHAR(500) | 정규화 마커 |
| `marker_source_column` | VARCHAR(50) | 출처 컬럼명 (prduct/main_fnctn/base_standard/intake_hint1) |
| `marker_type` | VARCHAR(50) | 마커 유형 |
| `supplement_id` | VARCHAR(20) | Backend DB supplement_entities.supplement_id |
| `mapping_status` | VARCHAR(30) | confirmed / needs_review |

### `pill_products`
알약 제품 마스터 (46,836건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `pill_product_id` | VARCHAR(64) PK | |
| `product_name` | VARCHAR(255) | 제품명 원문 |
| `product_name_normalized` | VARCHAR(255) UQ | 검색용 정규화 제품명 |

### `pill_product_ingredients`
알약 제품 ↔ canonical drug 연결 (26,362건). `canonical_drug_id`는 Backend DB 참조 (FK 미적용).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | |
| `pill_product_id` | VARCHAR(64) FK | → pill_products |
| `ingredient_name` | VARCHAR(255) | 성분명 원문 |
| `ingredient_name_normalized` | VARCHAR(255) | 정규화 성분명 |
| `canonical_drug_id` | VARCHAR(64) | Backend DB canonical_drug_entities.canonical_drug_id |

---

## Backend DB (`click_backend_db`)

### `canonical_drug_entities`
상호작용 조회 기준 표준 약물/약물군 (178건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `canonical_drug_id` | VARCHAR(64) PK | |
| `canonical_drug_name_ko` | VARCHAR(255) | 표준 약물명 (한국어) |
| `canonical_drug_name_en` | VARCHAR(255) | 표준 약물명 (영어) |

### `drug_aliases`
canonical drug 매칭용 alias (378건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `drug_alias_id` | VARCHAR(64) PK | |
| `alias_name` | VARCHAR(255) | alias 원문 |
| `alias_name_normalized` | VARCHAR(255) | 정규화 alias |
| `canonical_drug_id` | VARCHAR(64) FK | → canonical_drug_entities |

### `supplement_entities`
상호작용 조회 기준 표준 보충제 (33종).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `supplement_id` | VARCHAR(20) PK | (예: SUPP_001) |
| `supplement_name_ko` | VARCHAR(255) | 표준 성분명 (한국어) |
| `supplement_name_en` | VARCHAR(255) | 표준 성분명 (영어) |

### `source_claims`
상호작용 근거 원문/출처 (138건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `source_claim_id` | VARCHAR(64) PK | |
| `source_name` | VARCHAR(255) | 출처명 |
| `source_url` | TEXT | 출처 URL |
| `drug_text_original` | TEXT | 원문 약물 표현 |
| `supplement_text_original` | TEXT | 원문 보충제 표현 |
| `claim_text_original` | TEXT | 원문 상호작용 설명 |

### `standardized_interactions`
표준 약물-보충제 상호작용 edge (475건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `interaction_id` | VARCHAR(64) PK | |
| `canonical_drug_id` | VARCHAR(64) FK | → canonical_drug_entities |
| `supplement_id` | VARCHAR(20) FK | → supplement_entities |
| `source_claim_id` | VARCHAR(64) FK | → source_claims |

---

## 전체 조회 흐름

```
[처방전 인식 - AI 서버]
pill_products → pill_product_ingredients → canonical_drug_id 목록 반환

[건기식 인식 - AI 서버]
supplement_info → supplement_product_markers → supplement_id 목록 반환

[상호작용 조회 - Backend 서버]
canonical_drug_id × supplement_id → standardized_interactions → source_claims
```

---

## 데이터 import

v3 CSV 경로: `../drug-supplement schema v3/`

```bash
# AI DB (pill 테이블 + supplement_product_markers 교체)
cd ai
python scripts/import_v3_pill_data.py --csv-dir "../drug-supplement schema v3"

# Backend DB
cd backend
python scripts/import_v3_data.py --csv-dir "../drug-supplement schema v3"
```

import 순서 (FK 의존성):
1. `canonical_drug_entities`
2. `supplement_entities`
3. `source_claims`
4. `pill_products`
5. `supplement_info` (기존 데이터 유지)
6. `drug_aliases`
7. `pill_product_ingredients`
8. `supplement_product_markers`
9. `standardized_interactions`
