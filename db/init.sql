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

CREATE TABLE IF NOT EXISTS ingredient_interaction_matrix (
    supplement_id VARCHAR(50) NOT NULL,
    supplement_name VARCHAR(255),
    canonical_drug_id VARCHAR(50) NOT NULL,
    drug_name VARCHAR(255),
    risk_level VARCHAR(50) NOT NULL,
    needs_attention TINYINT(1) NOT NULL DEFAULT 0,
    evidence_status VARCHAR(100) NOT NULL,
    reason TEXT,
    claim_count INT NOT NULL DEFAULT 0,
    claim_ids TEXT,
    source_names TEXT,
    source_urls TEXT,
    source_review_statuses TEXT,
    overall_review_statuses TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (supplement_id, canonical_drug_id),
    KEY idx_matrix_risk (risk_level),
    KEY idx_matrix_attention (needs_attention),
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

CREATE TABLE IF NOT EXISTS interaction_source_registry (
    source_key VARCHAR(80) PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT,
    source_type VARCHAR(100),
    ingestion_status VARCHAR(100) NOT NULL DEFAULT 'planned',
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

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

CREATE TABLE IF NOT EXISTS domestic_source_raw_records (
    source_key VARCHAR(80) NOT NULL,
    source_record_id VARCHAR(100) NOT NULL,
    title VARCHAR(255),
    source_url TEXT,
    raw_payload_json JSON,
    retrieved_at TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (source_key, source_record_id),
    FOREIGN KEY (source_key) REFERENCES interaction_source_registry(source_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
