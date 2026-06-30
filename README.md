# CLICK Drug–Supplement Interaction Dataset

이 저장소는 건강기능식품·보충제와 약물 간 상호작용 원문을 보존하고, 이를 표준화된 보충제·약물 엔티티와 연결 구조로 제공하기 위한 backend 데이터 저장소입니다. 현재 데이터셋은 `v0.21` release candidate이며, 연구·프로토타입 데이터베이스와 API 개발을 위한 구조화 데이터를 목표로 합니다.

## 저장소 목적

식약처 원문 기반의 상호작용 claim을 보존하면서, 보충제와 약물 표현을 표준화된 엔티티로 연결합니다. 또한 외부 식별자, claim-target 관계, 검토 상태, 변경 이력을 함께 관리하여 데이터의 출처와 처리 상태를 추적할 수 있게 합니다.

## 책임 범위

- 식약처 원문 보존
- 보충제 및 약물 엔티티 표준화
- 외부 식별자 연결
- `claim-target` 관계 관리
- 검토 상태와 변경 이력 관리
- 자동 무결성 검증

## 범위에 포함하지 않는 것

- 이미지 인식
- OCR
- 독립적인 임상 진단
- 처방 또는 의료진 판단 대체
- 사용자용 최종 위험도 결정

## 전체 데이터 처리 흐름

```text
raw_interactions
-> supplement_map / drug_entity_map
-> canonical_drug_entities
-> standardized_interactions
-> claim_target_map / claim_drug_expansion
-> review_queue / change_log
```

- `raw_interactions`: 원문에서 수집한 상호작용 claim을 보존합니다.
- `supplement_map`: 원문 보충제명을 표준 보충제 엔티티로 매핑합니다.
- `drug_entity_map`: 원문 약물 표현을 표준 약물 엔티티로 매핑합니다.
- `canonical_drug_entities`: 표준 약물 엔티티와 외부 식별자 상태를 관리합니다.
- `standardized_interactions`: 원문 claim, 보충제 매핑, 약물 매핑, 검토 상태를 연결한 표준화 상호작용 테이블입니다.
- `claim_target_map`: 복합 또는 예시 약물 표현이 실제 target 약물 엔티티와 어떻게 연결되는지 관리합니다.
- `claim_drug_expansion`: 약물 class claim을 개별 약물 엔티티로 확장하는 관계를 관리합니다.
- `review_queue`: 추가 검토가 필요한 source claim, supplement mapping, drug mapping 항목을 관리합니다.
- `change_log`: 데이터 수정, 검토, 동기화 이력을 기록합니다.

## AI 저장소와의 연결

AI 저장소는 제품명, 성분명, 함량, `confidence`, `needs_confirmation`과 같은 인식 결과를 반환하는 역할을 맡을 수 있습니다. backend는 그 결과에 포함된 성분명을 이 저장소의 canonical entity에 연결하고, `standardized_interactions`에서 관련 상호작용을 조회한 뒤 출처와 검토 상태를 함께 반환하는 데이터 계층을 담당합니다.

현재 이 저장소에서 확인되는 것은 workbook 데이터 구조와 읽기 전용 무결성 검증 스크립트입니다. 구체적인 API endpoint, 제품 이미지 처리, 사용자 응답 로직은 이 저장소에 구현된 기능으로 표현하지 않습니다.

## 디렉터리 구조

```text
backend/
├── app/
│   ├── api/v1/endpoints/   # API 엔드포인트
│   ├── core/               # 설정 (환경변수)
│   ├── db/                 # DB 연결
│   ├── schemas/            # Pydantic 응답 스키마
│   └── main.py             # FastAPI 앱 진입점
├── db/
│   └── init.sql            # MySQL 테이블 생성
├── scripts/
│   └── load_interaction_data.py  # 엑셀 → MySQL 데이터 적재
├── data/source/            # 원본 엑셀 데이터셋
├── validation/             # 데이터 무결성 검증 스크립트
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

```powershell
python scripts/load_interaction_data.py
```

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
