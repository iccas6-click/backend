CREATE TABLE IF NOT EXISTS supplement_map (
    supplement_id VARCHAR(50) PRIMARY KEY,
    raw_name VARCHAR(255),
    canonical_name_ko VARCHAR(255),
    canonical_name_en VARCHAR(255),
    scientific_name VARCHAR(255),
    entity_type VARCHAR(100),
    mapping_status VARCHAR(100),
    mapping_basis TEXT,
    source_name VARCHAR(255),
    source_url TEXT,
    notes TEXT
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS canonical_drug_entities (
    canonical_drug_id VARCHAR(50) PRIMARY KEY,
    entity_level VARCHAR(100),
    canonical_name_ko VARCHAR(255),
    canonical_name_en VARCHAR(255),
    alias_count INT,
    raw_aliases TEXT,
    rxcui VARCHAR(50),
    atc_code VARCHAR(50),
    unii VARCHAR(50),
    kr_ingredient_code VARCHAR(50),
    external_id_status VARCHAR(100),
    mapping_status VARCHAR(100),
    verification_source_name VARCHAR(255),
    verification_source_url TEXT,
    notes TEXT
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pill_product_ingredients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_code VARCHAR(50),
    product_name VARCHAR(255) NOT NULL,
    normalized_product_name VARCHAR(255) NOT NULL,
    ingredient_name VARCHAR(255) NOT NULL,
    normalized_ingredient_name VARCHAR(255) NOT NULL,
    canonical_drug_id VARCHAR(50) NOT NULL,
    source_name VARCHAR(255),
    UNIQUE KEY uq_product_ingredient (product_code, normalized_product_name, normalized_ingredient_name),
    KEY idx_pill_product_norm (normalized_product_name),
    KEY idx_pill_ingredient_norm (normalized_ingredient_name),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS standardized_interactions (
    claim_id VARCHAR(50) PRIMARY KEY,
    raw_id VARCHAR(50),
    supplement_name_raw VARCHAR(255),
    supplement_id VARCHAR(50),
    supplement_canonical_ko VARCHAR(255),
    supplement_canonical_en VARCHAR(255),
    drug_name_raw VARCHAR(255),
    drug_alias_id VARCHAR(50),
    canonical_drug_id VARCHAR(50),
    drug_canonical_ko VARCHAR(255),
    drug_canonical_en VARCHAR(255),
    entity_level VARCHAR(100),
    interaction_target_group_raw TEXT,
    drug_category_raw VARCHAR(255),
    interaction_text_raw TEXT,
    source_name VARCHAR(255),
    source_record_id VARCHAR(100),
    source_url TEXT,
    source_review_status VARCHAR(100),
    supplement_mapping_status VARCHAR(100),
    drug_mapping_status VARCHAR(100),
    external_id_status VARCHAR(100),
    overall_review_status VARCHAR(100),
    FOREIGN KEY (supplement_id) REFERENCES supplement_map(supplement_id),
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities(canonical_drug_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS raw_interactions (
    raw_id VARCHAR(50) PRIMARY KEY,
    supplement_name_raw VARCHAR(255),
    drug_name_raw VARCHAR(255),
    interaction_target_group_raw TEXT,
    drug_category_raw VARCHAR(255),
    interaction_text_raw TEXT,
    severity_raw VARCHAR(100),
    recommendation_raw TEXT,
    evidence_text_raw TEXT,
    source_name VARCHAR(255),
    source_url TEXT,
    source_record_id VARCHAR(100),
    retrieved_date VARCHAR(50),
    review_status VARCHAR(100),
    collector VARCHAR(100),
    notes TEXT
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
