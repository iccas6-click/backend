-- ============================================================
-- CLICK Backend DB (click_backend_db)
-- 상호작용 조회용
-- drug-supplement schema v3 기준
-- ============================================================

-- 표준 약물 엔티티 (178건) ------------------------------------

CREATE TABLE IF NOT EXISTS canonical_drug_entities (
    canonical_drug_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    canonical_drug_name_ko VARCHAR(255) NOT NULL,
    canonical_drug_name_en VARCHAR(255),
    KEY idx_canonical_drug_name_ko (canonical_drug_name_ko),
    KEY idx_canonical_drug_name_en (canonical_drug_name_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 약물 alias (378건) ------------------------------------------

CREATE TABLE IF NOT EXISTS drug_aliases (
    drug_alias_id        VARCHAR(64)  NOT NULL PRIMARY KEY,
    alias_name           VARCHAR(255) NOT NULL,
    alias_name_normalized VARCHAR(255) NOT NULL,
    canonical_drug_id    VARCHAR(64)  NOT NULL,
    KEY idx_alias_name_normalized (alias_name_normalized),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 표준 보충제 엔티티 (33건) -----------------------------------

CREATE TABLE IF NOT EXISTS supplement_entities (
    supplement_id        VARCHAR(20)  NOT NULL PRIMARY KEY,
    supplement_name_ko   VARCHAR(255) NOT NULL,
    supplement_name_en   VARCHAR(255),
    KEY idx_supplement_name_ko (supplement_name_ko)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 상호작용 근거 원문 (138건) ----------------------------------

CREATE TABLE IF NOT EXISTS source_claims (
    source_claim_id      VARCHAR(64)  NOT NULL PRIMARY KEY,
    source_name          VARCHAR(255),
    source_url           TEXT,
    drug_text_original   TEXT,
    supplement_text_original TEXT,
    claim_text_original  TEXT
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 표준 약물-보충제 상호작용 edge (475건) ----------------------

CREATE TABLE IF NOT EXISTS standardized_interactions (
    interaction_id       VARCHAR(64)  NOT NULL PRIMARY KEY,
    canonical_drug_id    VARCHAR(64)  NOT NULL,
    supplement_id        VARCHAR(20)  NOT NULL,
    source_claim_id      VARCHAR(64)  NOT NULL,
    KEY idx_interaction_drug (canonical_drug_id),
    KEY idx_interaction_supplement (supplement_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id),
    FOREIGN KEY (supplement_id) REFERENCES supplement_entities(supplement_id),
    FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
