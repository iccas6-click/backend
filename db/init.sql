-- ============================================================
-- CLICK Backend DB - main schema
-- drug-supplement schema v1/v2 loader contract
-- ============================================================

CREATE TABLE IF NOT EXISTS canonical_drug_entities (
    canonical_drug_id VARCHAR(64) PRIMARY KEY,
    canonical_drug_name_ko VARCHAR(255) NOT NULL,
    canonical_drug_name_en VARCHAR(255),
    KEY idx_canonical_drug_name_ko (canonical_drug_name_ko),
    KEY idx_canonical_drug_name_en (canonical_drug_name_en)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pill_products (
    pill_product_id VARCHAR(64) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    product_name_normalized VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_pill_product_name_normalized (product_name_normalized),
    KEY idx_pill_product_name (product_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS drug_aliases (
    drug_alias_id VARCHAR(64) PRIMARY KEY,
    alias_name VARCHAR(255) NOT NULL,
    alias_name_normalized VARCHAR(255) NOT NULL,
    canonical_drug_id VARCHAR(64) NOT NULL,
    KEY idx_drug_alias_name (alias_name),
    KEY idx_drug_alias_norm (alias_name_normalized),
    KEY idx_drug_alias_drug (canonical_drug_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
        ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pill_product_ingredients (
    pill_product_id VARCHAR(64) NOT NULL,
    ingredient_name VARCHAR(255) NOT NULL,
    ingredient_name_normalized VARCHAR(255) NOT NULL,
    canonical_drug_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (pill_product_id, ingredient_name_normalized, canonical_drug_id),
    KEY idx_pill_ingredient_norm (ingredient_name_normalized),
    KEY idx_pill_ingredient_drug (canonical_drug_id),
    FOREIGN KEY (pill_product_id) REFERENCES pill_products(pill_product_id)
        ON DELETE CASCADE,
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
        ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supplement_entities (
    supplement_id VARCHAR(20) PRIMARY KEY,
    supplement_name_ko VARCHAR(255) NOT NULL,
    supplement_name_en VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_supplement_name_ko (supplement_name_ko),
    KEY idx_supplement_name_en (supplement_name_en)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supplement_info (
    id BIGINT PRIMARY KEY,
    sttemnt_no VARCHAR(100) UNIQUE,
    product TEXT,
    product_normalized TEXT,
    entrps TEXT,
    regist_dt VARCHAR(20),
    distb_pd TEXT,
    sungsang TEXT,
    srv_use TEXT,
    prsrv_pd TEXT,
    intake_hint1 TEXT,
    main_fnctn TEXT,
    base_standard TEXT,
    created_at VARCHAR(50)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supplement_product_markers (
    marker_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    supplement_info_id BIGINT NOT NULL,
    marker_text VARCHAR(500) NOT NULL,
    marker_text_normalized VARCHAR(500) NOT NULL,
    marker_source_column VARCHAR(50),
    marker_type VARCHAR(50),
    supplement_id VARCHAR(20),
    mapping_status VARCHAR(30),
    KEY idx_marker_text_norm (marker_text_normalized),
    KEY idx_marker_supplement (supplement_id),
    KEY idx_marker_info (supplement_info_id),
    FOREIGN KEY (supplement_info_id) REFERENCES supplement_info(id)
        ON DELETE CASCADE,
    FOREIGN KEY (supplement_id) REFERENCES supplement_entities(supplement_id)
        ON DELETE SET NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS source_claims (
    source_claim_id VARCHAR(64) PRIMARY KEY,
    source_name TEXT,
    source_url TEXT,
    drug_text_original TEXT,
    supplement_text_original TEXT,
    claim_text_original TEXT
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS standardized_interactions (
    interaction_id VARCHAR(64) PRIMARY KEY,
    canonical_drug_id VARCHAR(64) NOT NULL,
    supplement_id VARCHAR(20) NOT NULL,
    source_claim_id VARCHAR(64) NOT NULL,
    KEY idx_std_pair (supplement_id, canonical_drug_id),
    KEY idx_std_drug (canonical_drug_id),
    KEY idx_std_claim (source_claim_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
        ON DELETE CASCADE,
    FOREIGN KEY (supplement_id) REFERENCES supplement_entities(supplement_id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id)
        ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
