# CLICK Drug–Supplement Interaction Dataset

이 저장소는 건강기능식품·보충제와 약물 간 상호작용 원문을 보존하고, 이를 표준화된 보충제·약물 엔티티와 연결 구조로 제공하기 위한 backend 데이터 저장소입니다. 현재 데이터셋은 `v0.21` release candidate이며, 연구·프로토타입 데이터베이스와 API 개발을 위한 구조화 데이터를 목표로 합니다.

## 이번 브랜치의 main 대비 변경점

- 앱 분석 결과를 `v2_standardized_interactions` 기반으로 고정했습니다.
- 처방전·약봉투 AI 인식 결과의 제품명/성분명을 v2 약 성분 엔티티로 우선 매핑합니다.
- 건강기능식품 라벨 인식 결과를 v2 원료 alias와 exclusion 기준으로 표준화합니다.
- 공식 의약품 제품/성분 캐시용 테이블과 importer를 추가했습니다.
- AIHub 1000종 제품-성분 slim CSV와 검색 스크립트를 추가해 legacy fallback 데이터를 보강했습니다.
- `/api/v1/interactions/analyze` 응답에 checked/detected/unmatched count를 유지해 분석 범위를 프론트에서 표시할 수 있게 했습니다.
- legacy `standardized_interactions`, `ingredient_interaction_matrix`, Supp.ai 문헌 문장은 앱 결과 표시에서 제외했습니다.
- phpMyAdmin 포트 설정을 `.env.example`과 docker compose에 추가했습니다.

### 현재 프로토타입 데이터 규모

```text
v2_standardized_interactions       475 rows
v2_canonical_drug_entities         178 rows
v2_drug_ingredient_aliases         384 rows
v2_official_supplement_ingredients  37 rows
v2_supplement_label_aliases        200 rows
pill_product_ingredients          2030 rows
```

## 저장소 목적

식약처 원문 기반의 상호작용 claim을 보존하면서, 보충제와 약물 표현을 표준화된 엔티티로 연결합니다. 또한 외부 식별자, claim-target 관계, 검토 상태, 변경 이력을 함께 관리하여 데이터의 출처와 처리 상태를 추적할 수 있게 합니다.

## 책임 범위

- 식약처 원문 보존
- 보충제 및 약물 엔티티 표준화
- 외부 식별자 연결
- `claim-target` 관계 관리
- 검토 상태와 변경 이력 관리
- 자동 무결성 검증
- AI 인식 결과의 제품명·성분명을 canonical entity로 해석
- 약 성분 x 건강기능식품 성분 조합의 현재 DB 기준 주의 근거 조회

## 범위에 포함하지 않는 것

- 이미지 인식
- OCR
- 독립적인 임상 진단
- 처방 또는 의료진 판단 대체
- 사용자용 최종 위험도 결정

## 전체 데이터 처리 흐름

```text
source_claims (원문 클레임)
  + supplement_entities (33종 건기식 표준)
  + canonical_drug_entities (약물 표준 엔티티)
→ standardized_interactions (정제된 상호작용)

supplement_info (식약처 제품 DB 44,885건)
→ supplement_product_markers (성분 파싱 결과)
→ supplement_entities 매핑
```

- `source_claims`: 원문 출처에서 수집한 상호작용 claim을 보존합니다.
- `supplement_entities`: 33종 건기식 표준 엔티티를 관리합니다.
- `canonical_drug_entities`: 표준 약물 엔티티를 관리합니다.
- `standardized_interactions`: 건기식–약물 상호작용을 세 FK로 연결합니다.
- `supplement_info`: 식약처 MFDS 건기식 제품 DB입니다.
- `supplement_product_markers`: supplement_info에서 파싱한 성분 마커입니다.
- `pill_products` / `drug_aliases` / `pill_product_ingredients`: 알약 인식 side (알약 담당자 관리).

### 현재 API용 분석 지식베이스

앱 연동 브랜치에서는 workbook 원본 테이블 위에 프론트/AI 인식 결과를 바로 분석하기 위한 테이블을 추가로 사용합니다.

```text
AI 인식 결과
-> pill_product_ingredients / supplement_aliases
-> canonical_drug_entities / supplement_map
-> interaction_evidence_claims
-> ingredient_interaction_matrix
-> /api/v1/interactions/analyze
```

- `pill_product_ingredients`: AIHub 1000종 및 Codeit 인식 제품명을 성분 canonical drug entity로 확장합니다.
- `supplement_aliases`: 건강기능식품 성분 별칭을 표준 `supplement_map` row로 연결합니다.
- `interaction_source_registry`: MFDS HID, e약은요 OpenAPI, Supp.ai 등 근거 소스를 등록합니다.
- `interaction_evidence_claims`: 외부/국내 소스에서 확인한 주의 claim을 표준 조합에 연결합니다.
- `interaction_pair_source_checks`: 성분 조합을 어떤 소스에서 확인했는지 상태를 기록합니다.
- `ingredient_interaction_matrix`: 현재 DB에 존재하는 건강기능식품 성분 x 약 성분 전체 조합 판정표입니다. `needs_attention=0`은 안전 보장이 아니라 현재 DB에서 주의 근거가 발견되지 않았다는 뜻입니다.

## AI 저장소와의 연결

AI 저장소는 알약/건강기능식품 이미지에서 제품 후보, 성분명, 공식 이미지 URL, `confidence`, `needs_confirmation`과 같은 인식 결과를 반환합니다. backend는 다음 순서로 결과를 분석합니다.

1. 알약 입력이 제품명으로 들어오면 `pill_product_ingredients`에서 실제 성분으로 확장합니다.
2. 알약 입력이 성분명으로 들어오면 `canonical_drug_entities`와 alias를 기준으로 해석합니다.
3. 건강기능식품 입력은 `supplement_map`과 `supplement_aliases`로 canonical supplement entity에 연결합니다.
4. 성분 조합을 `interaction_evidence_claims` 및 기존 `standardized_interactions`에서 조회합니다.
5. 프론트가 표시할 수 있도록 `pairs`, 매칭된 성분 목록, 미매칭 카운트, 전체 확인 조합 수를 반환합니다.

## 디렉터리 구조

```text
backend/
├── app/
│   ├── api/v1/endpoints/   # API 엔드포인트
│   ├── core/               # 설정 (환경변수)
│   ├── db/                 # DB 연결
│   ├── schemas/            # Pydantic 응답 스키마
│   ├── services/           # supplement_resolver, translator
│   └── main.py             # FastAPI 앱 진입점
├── db/
│   └── init.sql            # MySQL 테이블 생성
├── scripts/
│   ├── load_interaction_data.py          # 엑셀 → MySQL 데이터 적재
│   ├── load_aihub_pill_ingredients.py    # AIHub 제품명-성분 CSV 적재
│   ├── import_codeit_pill_ingredients.py # Codeit 제품명-성분 매핑 적재
│   ├── import_mfds_*_evidence.py         # MFDS 근거 수집
│   ├── import_supp_ai_evidence.py        # Supp.ai 근거 수집
│   └── build_interaction_matrix.py       # 전체 성분 조합 판정표 생성
├── data/source/            # 원본 엑셀 데이터셋
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 서버 실행 방법

### 사전 준비

`.env.example`을 복사해 `.env` 파일 생성 후 값 설정:

```
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_DATABASE=click_backend_db
MYSQL_USER=click_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
DEEPL_API_KEY=your_deepl_api_key
```

`DEEPL_API_KEY`는 [DeepL API Free](https://www.deepl.com/pro-api)에서 발급받습니다. 키가 없으면 다국어 번역 없이 원문(한국어) 그대로 반환됩니다.

### Docker DB 실행

```powershell
docker compose up -d
```

### 데이터 적재

`click/drug-supplement schema/drug-supplement schema/processed/` 폴더의 CSV 파일을 읽어 DB에 적재합니다.

```powershell
# 전체 적재 (supplement_info 44,885행 포함 — 수 분 소요)
python scripts/load_interaction_data.py

# supplement_info / supplement_product_markers 생략 (빠른 테스트)
python scripts/load_interaction_data.py --skip-supplement-info

# processed 폴더 경로를 직접 지정할 경우
python scripts/load_interaction_data.py --processed-dir "경로/to/processed"
```

앱 연동용 분석 지식베이스까지 구성하려면 다음 순서로 보강 데이터를 적재합니다.

```powershell
python scripts/add_basic_drug_entities.py
python scripts/add_basic_nutrient_supplements.py
python scripts/load_aihub_pill_ingredients.py path/to/aihub_1000_pill_ingredients_slim.csv
python scripts/import_codeit_pill_ingredients.py
python scripts/build_interaction_investigation.py
python scripts/import_mfds_hid_live_evidence.py
python scripts/import_mfds_e_drug_evidence.py
python scripts/import_supp_ai_evidence.py
python scripts/build_interaction_matrix.py
```

`load_aihub_pill_ingredients.py`는 해당 source의 `pill_product_ingredients` row를 재적재하고, `build_interaction_matrix.py`는 `ingredient_interaction_matrix`를 전체 재빌드합니다.

### FastAPI 서버 실행

```powershell
uvicorn app.main:app --reload
```

서버 실행 후 `http://localhost:8000/docs` 에서 Swagger UI로 API 테스트 가능.

## 주요 API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/health` | 서버 상태 확인 |
| GET | `/api/v1/interactions?supplement=성분명` | 건기식 성분 단건 상호작용 조회 |
| POST | `/api/v1/interactions/analyze` | 알약 + 건기식 다중 항목 상호작용 분석 |

### POST /api/v1/interactions/analyze

프론트엔드 메인 연동 엔드포인트. 촬영한 알약·건기식 인식 결과를 한번에 보내면 위험도 분석 결과를 반환합니다.

```json
// 요청
{
  "items": [
    { "name": "아스피린", "category": "알약" },
    { "name": "오메가-3 지방산", "category": "건강기능식품 라벨" }
  ],
  "lang": "ko"
}

// 응답
{
  "overall": "caution",
  "summary": "일부 조합에서 주의가 필요합니다. 전문가와 상담을 권장합니다.",
  "matchedDrugNames": ["아스피린"],
  "matchedSupplementNames": ["오메가-3 지방산"],
  "checkedCount": 1,
  "detectedCount": 1,
  "undetectedCount": 0,
  "unmatchedSupplementCount": 0,
  "unmatchedDrugCount": 0,
  "unmatchedCombinationCount": 0,
  "pairs": [
    {
      "id": "1",
      "items": ["오메가-3 지방산", "아스피린"],
      "level": "caution",
      "description": "함께 복용 시 출혈 위험이 증가할 수 있음."
    }
  ]
}
```

`overall` / `level` 값: `"danger"` (위험) | `"caution"` (주의) | `"safe"` (안전)

### 다국어 지원 (`lang`)

`lang`: `"ko"`(기본값) | `"en"` | `"fr"`

- `summary`: 자체 번역 테이블로 즉시 번역 (`app/i18n.py`)
- `description`: DeepL API로 DB 원문(한국어)을 실시간 번역 (`app/services/translator.py`)
- `DEEPL_API_KEY` 미설정 시 `description`은 한국어 원문 그대로 반환

```json
// 요청 (lang: "en")
{
  "items": [
    { "name": "아스피린", "category": "알약" },
    { "name": "오메가-3 지방산", "category": "건강기능식품 라벨" }
  ],
  "lang": "en"
}

// 응답
{
  "overall": "danger",
  "summary": "A dangerous combination was found. Consult a professional before use.",
  "pairs": [
    {
      "id": "1",
      "items": ["EPA 및 DHA 함유 유지(오메가-3 지방산)", "아스피린"],
      "level": "danger",
      "description": "It can increase the risk of bleeding!"
    }
  ]
}
```

자세한 연동 방법은 [`docs/frontend-integration.md`](docs/frontend-integration.md)를 참고하세요.

## 현재 데이터셋 파일

```text
data/source/drug_supplement_interactions_standardized_v0.21_release_candidate.xlsx
```

## workbook 주요 시트

- `raw_interactions`: `raw_id`를 기준으로 원문 보충제명, 약물명, 상호작용 원문, 출처, 수집일, 검토 상태를 보존합니다.
- `supplement_map`: `supplement_id`를 기준으로 원문 보충제명과 표준 보충제명, `entity_type`, `mapping_status`, 출처를 관리합니다.
- `drug_entity_map`: `drug_alias_id`를 기준으로 원문 약물 표현을 `canonical_drug_id`에 연결하고, `entity_level`, `mapping_status`를 관리합니다.
- `canonical_drug_entities`: `canonical_drug_id`를 기준으로 표준 약물 엔티티명, `rxcui`, `atc_code`, `unii`, `kr_ingredient_code`, `external_id_status`를 관리합니다.
- `standardized_interactions`: `claim_id`를 기준으로 `raw_id`, `supplement_id`, `drug_alias_id`, `canonical_drug_id`와 source/review/mapping 상태를 연결합니다.
- `claim_target_map`: `claim_target_id`를 기준으로 `claim_id`, source alias 또는 composite canonical drug, target canonical drug 관계를 관리합니다.
- `claim_drug_expansion`: `expansion_id`를 기준으로 특정 `claim_id`에서 class 성격의 source drug entity를 확장 대상 canonical drug entity에 연결합니다.
- `review_queue`: `record_id`를 기준으로 검토 대상 유형(`queue_type`), 현재 상태(`current_status`), 필요한 조치와 근거를 관리합니다.
- `code_sources`: 외부 식별자 체계와 공식 출처, 데이터셋 내 사용 목적을 기록합니다.
- `data_quality_summary`: release candidate의 데이터 품질 요약과 상태 집계를 기록합니다.
- `change_log`: `change_id`를 기준으로 변경 대상, 변경 전후 값, 결정 사유, 검토자, 후속 조치 필요 여부를 기록합니다.

## 현재 v0.21 상태

workbook에서 빈 행을 제외하고 다시 계산한 현재 상태는 다음과 같습니다.

| 항목 | 값 |
| --- | ---: |
| raw interactions | 475 |
| standardized interactions | 475 |
| canonical drug entities | 140 |
| VERIFIED external ID entities | 119 |
| PENDING_VERIFICATION entities | 4 |
| NOT_ASSIGNED_FOR_NON_INGREDIENT | 17 |
| review queue | 30 |
| review_queue CHECKED | 19 |
| review_queue PROVISIONAL | 11 |

`canonical_drug_entities`에는 `entity_type` 컬럼이 없으며, entity 구분은 `entity_level` 컬럼에서 확인됩니다. `supplement_map`에는 `entity_type` 컬럼이 있습니다.

## 자동 검증 방법

Windows PowerShell에서는 저장소 루트에서 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe validation\validate_workbook.py
```

다른 Python 환경을 사용할 경우, `pandas`와 `openpyxl`이 설치된 상태에서 다음처럼 실행할 수 있습니다.

```powershell
python validation\validate_workbook.py
```

검증 스크립트는 workbook을 읽기 전용으로 로드하며, 원본 Excel 파일이나 별도 결과 파일을 저장하지 않습니다. 명령행 인자로 다른 `.xlsx` 경로를 전달하면 해당 workbook을 검증할 수 있습니다.

## 현재 검증 결과

다음 명령으로 현재 workbook을 검증했습니다.

```powershell
.\.venv\Scripts\python.exe validation\validate_workbook.py
```

검증 요약은 다음과 같습니다.

```text
PASS: 20
WARNING: 0
ERROR: 0
```

검증 범위는 주요 기본키의 빈 값·중복 검사, 주요 외래키 관계 검사, 상태값 분포 출력입니다. 현재는 `mapping_status` 등 상태값의 허용 목록을 오류로 강제하지 않고, 참고 정보로만 출력합니다.

## 주의사항

- 현재 버전은 release candidate입니다.
- `PROVISIONAL`은 확정 매핑을 의미하지 않습니다.
- 구조적 무결성 검증 통과가 임상적 타당성 검증 완료를 의미하지 않습니다.
- 이 데이터셋은 의료적 판단, 처방 또는 의료진의 판단을 대체하지 않습니다.
