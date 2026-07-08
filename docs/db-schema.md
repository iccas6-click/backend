# DB 스키마 명세

CLICK Backend DB (`click_backend_db`) — drug-supplement schema 기준 (2025-07)

---

## 테이블 구성 (8개)

### 알약 side

#### `canonical_drug_entities`
약물 표준 엔티티.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `canonical_drug_id` | VARCHAR(64) PK | 약물 고유 ID |
| `canonical_drug_name_ko` | VARCHAR(255) | 표준 약물명 (한국어) |
| `canonical_drug_name_en` | VARCHAR(255) | 표준 약물명 (영어) |

#### `pill_products`
알약 제품 목록 (AIHub 데이터 기반).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `pill_product_id` | VARCHAR(64) PK | 제품 고유 ID |
| `product_name` | VARCHAR(255) | 제품명 원문 |
| `product_name_normalized` | VARCHAR(255) UQ | 정규화된 제품명 |

#### `drug_aliases`
약물 별칭 — `canonical_drug_entities` FK.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `drug_alias_id` | VARCHAR(64) PK | 별칭 고유 ID |
| `alias_name` | VARCHAR(255) | 별칭 원문 |
| `alias_name_normalized` | VARCHAR(255) | 정규화된 별칭 |
| `canonical_drug_id` | VARCHAR(64) FK | → canonical_drug_entities |

#### `pill_product_ingredients`
알약 제품 ↔ 약물 성분 연결 테이블.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `pill_product_id` | VARCHAR(64) FK | → pill_products |
| `ingredient_name` | VARCHAR(255) | 성분명 원문 |
| `ingredient_name_normalized` | VARCHAR(255) | 정규화된 성분명 |
| `canonical_drug_id` | VARCHAR(64) FK | → canonical_drug_entities |

---

### 건기식 side

#### `supplement_entities`
33종 건강기능식품 표준 엔티티.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `supplement_id` | VARCHAR(20) PK | 건기식 고유 ID (예: SUPP_001) |
| `supplement_name_ko` | VARCHAR(255) | 표준 성분명 (한국어) |
| `supplement_name_en` | VARCHAR(255) | 표준 성분명 (영어) |
| `created_at` | TIMESTAMP | 생성일시 |

#### `supplement_info`
식약처 MFDS 건기식 제품 DB (44,885건).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | 제품 고유 ID |
| `sttemnt_no` | VARCHAR(100) UQ | 신고번호 |
| `product` | TEXT | 제품명 원문 |
| `product_normalized` | TEXT | 정규화된 제품명 |
| `entrps` | TEXT | 제조사 |
| `regist_dt` | VARCHAR(20) | 등록일 |
| `main_fnctn` | TEXT | 주요 기능성 원료 |
| `base_standard` | TEXT | 기준 및 규격 |
| 기타 | TEXT | sungsang, srv_use, prsrv_pd, intake_hint1 |

#### `supplement_product_markers`
supplement_info에서 파싱한 성분 마커 — `supplement_entities` FK.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `marker_id` | BIGINT PK AUTO | 마커 고유 ID |
| `supplement_info_id` | BIGINT FK | → supplement_info |
| `marker_text` | VARCHAR(500) | 파싱된 성분명 |
| `marker_text_normalized` | VARCHAR(500) | 정규화된 성분명 |
| `marker_source_column` | VARCHAR(50) | 파싱 출처 컬럼명 |
| `marker_type` | VARCHAR(50) | 성분 타입 |
| `supplement_id` | VARCHAR(20) FK | → supplement_entities (매핑 결과) |
| `mapping_status` | VARCHAR(30) | mapped / unmapped |

---

### 상호작용 side

#### `source_claims`
상호작용 원본 클레임 데이터.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `source_claim_id` | VARCHAR(64) PK | 클레임 고유 ID |
| `source_name` | TEXT | 출처명 |
| `source_url` | TEXT | 출처 URL |
| `drug_text_original` | TEXT | 약물명 원문 |
| `supplement_text_original` | TEXT | 건기식명 원문 |
| `claim_text_original` | TEXT | 상호작용 설명 원문 (한국어) |

#### `standardized_interactions`
정제된 건기식–약물 상호작용.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `interaction_id` | VARCHAR(64) PK | 상호작용 고유 ID |
| `canonical_drug_id` | VARCHAR(64) FK | → canonical_drug_entities |
| `supplement_id` | VARCHAR(20) FK | → supplement_entities |
| `source_claim_id` | VARCHAR(64) FK | → source_claims |

---

## 이전 스키마 대비 변경 내역

| 이전 (init.sql) | 현재 | 변경 내용 |
|---|---|---|
| `supplement_map` | `supplement_entities` | 이름 변경, 컬럼 단순화 |
| `supplement_aliases` | 제거 | 별칭 테이블 삭제 |
| `canonical_drug_entities` (15컬럼) | `canonical_drug_entities` (3컬럼) | 구조 단순화 |
| `raw_interactions` | `source_claims` | 이름 변경, 구조 변경 |
| `standardized_interactions` (복잡) | `standardized_interactions` (FK 3개) | 구조 단순화, JOIN으로 데이터 조회 |
| 없음 | `supplement_info` | 신규 (AI DB에서 이전) |
| 없음 | `supplement_product_markers` | 신규 (AI DB에서 이전) |
| 없음 | `pill_products`, `drug_aliases`, `pill_product_ingredients` | 신규 (알약 담당자) |

---

## DB 초기화

```bash
# 볼륨 포함 삭제 후 재시작 (init.sql 재적용)
docker-compose down -v
docker-compose up -d db
```
