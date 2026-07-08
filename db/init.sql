-- ============================================================
-- CLICK Backend DB — 통합 스키마
-- drug-supplement schema 기준 (2025-07)
-- ============================================================

-- 1. 알약 side --------------------------------------------------

CREATE TABLE IF NOT EXISTS canonical_drug_entities (
  canonical_drug_id   VARCHAR(64)  NOT NULL,
  canonical_drug_name_ko VARCHAR(255) NOT NULL,
  canonical_drug_name_en VARCHAR(255) NULL,
  PRIMARY KEY (canonical_drug_id),
  KEY idx_canonical_drug_name_ko (canonical_drug_name_ko),
  KEY idx_canonical_drug_name_en (canonical_drug_name_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pill_products (
  pill_product_id          VARCHAR(64)  NOT NULL,
  product_name             VARCHAR(255) NOT NULL,
  product_name_normalized  VARCHAR(255) NOT NULL,
  PRIMARY KEY (pill_product_id),
  UNIQUE KEY uq_pill_products_product_name_normalized (product_name_normalized),
  KEY idx_pill_products_product_name (product_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS drug_aliases (
  drug_alias_id          VARCHAR(64)  NOT NULL,
  alias_name             VARCHAR(255) NOT NULL,
  alias_name_normalized  VARCHAR(255) NOT NULL,
  canonical_drug_id      VARCHAR(64)  NOT NULL,
  PRIMARY KEY (drug_alias_id),
  UNIQUE KEY uq_drug_aliases_alias_canonical (alias_name_normalized, canonical_drug_id),
  KEY idx_drug_aliases_alias_name_normalized (alias_name_normalized),
  KEY idx_drug_aliases_canonical_drug_id (canonical_drug_id),
  CONSTRAINT fk_drug_aliases_canonical_drug
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities (canonical_drug_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pill_product_ingredients (
  pill_product_id          VARCHAR(64)  NOT NULL,
  ingredient_name          VARCHAR(255) NOT NULL,
  ingredient_name_normalized VARCHAR(255) NOT NULL,
  canonical_drug_id        VARCHAR(64)  NOT NULL,
  PRIMARY KEY (pill_product_id, ingredient_name_normalized, canonical_drug_id),
  KEY idx_pill_product_ingredients_ingredient_normalized (ingredient_name_normalized),
  KEY idx_pill_product_ingredients_canonical_drug_id (canonical_drug_id),
  CONSTRAINT fk_pill_product_ingredients_product
    FOREIGN KEY (pill_product_id) REFERENCES pill_products (pill_product_id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_pill_product_ingredients_canonical_drug
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities (canonical_drug_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 건기식 side -----------------------------------------------

CREATE TABLE IF NOT EXISTS supplement_entities (
  supplement_id      VARCHAR(20)  NOT NULL,
  supplement_name_ko VARCHAR(255) NOT NULL,
  supplement_name_en VARCHAR(255) NULL,
  created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (supplement_id),
  KEY idx_supplement_entities_name_ko (supplement_name_ko),
  KEY idx_supplement_entities_name_en (supplement_name_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supplement_info (
  id                 BIGINT       NOT NULL,
  sttemnt_no         VARCHAR(100) NOT NULL,
  product            TEXT         NOT NULL,
  product_normalized TEXT         NULL,
  entrps             TEXT         NULL,
  regist_dt          VARCHAR(20)  NULL,
  distb_pd           TEXT         NULL,
  sungsang           TEXT         NULL,
  srv_use            TEXT         NULL,
  prsrv_pd           TEXT         NULL,
  intake_hint1       TEXT         NULL,
  main_fnctn         TEXT         NULL,
  base_standard      TEXT         NULL,
  created_at         DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_supplement_info_sttemnt_no (sttemnt_no),
  KEY idx_supplement_info_product_normalized (product_normalized(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supplement_product_markers (
  marker_id               BIGINT       NOT NULL AUTO_INCREMENT,
  supplement_info_id      BIGINT       NOT NULL,
  marker_text             VARCHAR(500) NOT NULL,
  marker_text_normalized  VARCHAR(500) NOT NULL,
  marker_source_column    VARCHAR(50)  NOT NULL,
  marker_type             VARCHAR(50)  NOT NULL,
  supplement_id           VARCHAR(20)  NULL,
  mapping_status          VARCHAR(30)  NOT NULL,
  created_at              TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (marker_id),
  UNIQUE KEY uq_supplement_product_marker (
    supplement_info_id, marker_text_normalized, marker_source_column, supplement_id
  ),
  KEY idx_supplement_product_markers_info_id (supplement_info_id),
  KEY idx_supplement_product_markers_supplement_id (supplement_id),
  KEY idx_supplement_product_markers_marker_normalized (marker_text_normalized),
  KEY idx_supplement_product_markers_status (mapping_status),
  CONSTRAINT fk_supplement_product_markers_info
    FOREIGN KEY (supplement_info_id) REFERENCES supplement_info (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_supplement_product_markers_entity
    FOREIGN KEY (supplement_id) REFERENCES supplement_entities (supplement_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 상호작용 side ---------------------------------------------

CREATE TABLE IF NOT EXISTS source_claims (
  source_claim_id         VARCHAR(64) NOT NULL,
  source_name             TEXT        NULL,
  source_url              TEXT        NULL,
  drug_text_original      TEXT        NULL,
  supplement_text_original TEXT       NULL,
  claim_text_original     TEXT        NULL,
  PRIMARY KEY (source_claim_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS standardized_interactions (
  interaction_id    VARCHAR(64) NOT NULL,
  canonical_drug_id VARCHAR(64) NOT NULL,
  supplement_id     VARCHAR(20) NOT NULL,
  source_claim_id   VARCHAR(64) NOT NULL,
  PRIMARY KEY (interaction_id),
  UNIQUE KEY uq_standardized_interaction_claim (canonical_drug_id, supplement_id, source_claim_id),
  KEY idx_standardized_interactions_drug_supplement (canonical_drug_id, supplement_id),
  KEY idx_standardized_interactions_supplement_id (supplement_id),
  KEY idx_standardized_interactions_source_claim_id (source_claim_id),
  CONSTRAINT fk_standardized_interactions_drug
    FOREIGN KEY (canonical_drug_id) REFERENCES canonical_drug_entities (canonical_drug_id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_standardized_interactions_supplement
    FOREIGN KEY (supplement_id) REFERENCES supplement_entities (supplement_id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_standardized_interactions_source_claim
    FOREIGN KEY (source_claim_id) REFERENCES source_claims (source_claim_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
