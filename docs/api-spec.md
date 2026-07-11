# API 명세서

CLICK Backend API v0.1.0

베이스 URL: `http://localhost:8000` (배포 환경에서는 실제 도메인으로 대체)

---

## GET /health

서버 상태 확인.

**요청**

파라미터 없음.

**응답** `200 OK`
```json
{ "status": "ok" }
```

---

## GET /api/v1/interactions

건강기능식품 성분 하나의 원시 상호작용 데이터를 조회합니다.

**Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `supplement` | string | Y | 성분명. 표준 성분명, 원문 표기, 개별인정원료 브랜드명(예: `TWK10`) 모두 가능 |

**요청 예시**
```
GET /api/v1/interactions?supplement=오메가3
```

**응답** `200 OK`

| 필드 | 타입 | 설명 |
|---|---|---|
| `supplement_name` | string | 요청에 사용된 원본 검색어 |
| `resolved_name` | string \| null | alias 해석 후 확정된 표준 성분명. 해석 실패 시 `null` |
| `matched_alias` | string \| null | 실제 매칭에 사용된 표기 |
| `match_type` | string \| null | `exact_canonical` \| `exact_raw` \| `exact_alias` \| `partial` \| `not_found` |
| `interactions` | array | 상호작용 목록 (아래 `InteractionResult` 참고) |
| `total` | integer | `interactions` 개수 |

**`InteractionResult`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `claim_id` | string | 상호작용 claim 고유 ID |
| `supplement_canonical_ko` | string \| null | 표준 성분명(한국어) |
| `drug_canonical_ko` | string \| null | 표준 약물명(한국어) |
| `drug_canonical_en` | string \| null | 표준 약물명(영어) |
| `interaction_text_raw` | string \| null | 상호작용 설명 원문(한국어) |
| `source_review_status` | string \| null | 원문 출처 검토 상태 |
| `overall_review_status` | string \| null | 전체 검토 상태 |

**응답 예시**
```json
{
  "supplement_name": "오메가3",
  "resolved_name": "오메가-3 지방산",
  "matched_alias": "오메가3",
  "match_type": "exact_alias",
  "interactions": [
    {
      "claim_id": "SI-0001",
      "supplement_canonical_ko": "오메가-3 지방산",
      "drug_canonical_ko": "아스피린",
      "drug_canonical_en": "Aspirin",
      "interaction_text_raw": "함께 복용 시 출혈 위험이 증가할 수 있음. 주의가 필요합니다.",
      "source_review_status": "reviewed",
      "overall_review_status": "confirmed"
    }
  ],
  "total": 1
}
```

**에러**
- `500 Internal Server Error` — DB 연결 실패 등 서버 내부 오류

---

## POST /api/v1/interactions/analyze

알약 + 건강기능식품 다중 항목을 한번에 분석해 프론트엔드 표시 형식으로 반환합니다. **프론트엔드 메인 연동 대상.**

**Request Body** (`application/json`)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `items` | array | Y | 분석할 항목 목록 (아래 `AnalyzeItem` 참고) |
| `lang` | string | N | `"ko"`(기본값) \| `"en"` \| `"fr"` — 응답 언어 |

**`AnalyzeItem`**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `name` | string | Y | 성분명 또는 약물명 |
| `category` | string | Y | `"알약"` \| `"건강기능식품 라벨"` |

**요청 예시**
```json
{
  "items": [
    { "name": "아스피린", "category": "알약" },
    { "name": "오메가-3 지방산", "category": "건강기능식품 라벨" }
  ],
  "lang": "ko"
}
```

**응답** `200 OK`

| 필드 | 타입 | 설명 |
|---|---|---|
| `overall` | string | `"danger"` \| `"caution"` \| `"safe"` — 전체 종합 위험도 |
| `summary` | string | 종합 안내 문구 (`lang`에 맞춰 번역됨) |
| `pairs` | array | 위험도 높은 순으로 정렬된 조합 목록 (아래 `InteractionPair` 참고) |
| `matchedDrugNames` | string[] | 분석에 실제 사용된 약 성분명 |
| `matchedSupplementNames` | string[] | 분석에 실제 사용된 건강기능식품 성분명 |
| `ignoredDrugNames` | string[] | 제품명/포장값 등 성분 분석에서 제외된 알약 입력값 |
| `checkedCount` | integer | 실제로 확인한 건강기능식품 성분 x 약 성분 조합 수 |
| `detectedCount` | integer | 주의 근거가 발견된 조합 수 |
| `undetectedCount` | integer | 현재 DB 기준 주의 근거가 발견되지 않은 조합 수 |
| `unmatchedSupplementCount` | integer | 건강기능식품 성분으로 해석하지 못한 입력 수 |
| `unmatchedDrugCount` | integer | 약 성분으로 해석하지 못한 입력 수 |
| `unmatchedCombinationCount` | integer | 해석 실패 때문에 조합 확인이 불가능했던 수 |

**`InteractionPair`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string | 조합 순번(1부터) |
| `items` | string[] | `[성분명, 약물명]` — DB canonical name, 번역 대상 아님 |
| `level` | string | `"danger"` \| `"caution"` \| `"safe"` |
| `description` | string | 상호작용 설명 (`lang`에 맞춰 DeepL로 번역됨) |

**응답 예시**
```json
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
  ],
  "matchedDrugNames": ["아스피린"],
  "matchedSupplementNames": ["오메가-3 지방산"],
  "ignoredDrugNames": [],
  "checkedCount": 1,
  "detectedCount": 1,
  "undetectedCount": 0,
  "unmatchedSupplementCount": 0,
  "unmatchedDrugCount": 0,
  "unmatchedCombinationCount": 0
}
```

### 동작 규칙

1. `items`를 `category` 기준 `알약` / `건강기능식품 라벨`로 분류
2. 알약 입력이 제품명으로 들어온 경우 `pill_product_ingredients`에서 실제 성분으로 확장
3. 알약 성분명은 `canonical_drug_entities`와 alias를 기준으로 해석
4. 건강기능식품 입력은 `supplement_map`과 `supplement_aliases`로 표준 성분에 연결
5. 건강기능식품이 하나도 없으면 즉시 `{ overall: "safe", summary: "분석할 건강기능식품이 없습니다.", pairs: [] }` 반환
6. 건강기능식품 성분 × 약 성분 조합을 `standardized_interactions`와 `interaction_evidence_claims` 기준으로 조회
7. `interaction_text_raw` 또는 evidence text에 포함된 키워드로 위험도 자동 추론
   - `danger` 키워드: 금기, 심각, 위험, 사망, 피해야, 절대
   - 그 외 확인된 claim은 기본적으로 `caution`
8. 매칭된 주의 근거가 없으면 `pairs`는 비며 `overall: "safe"`가 반환됩니다. 이때 `undetectedCount`는 현재 DB 기준 근거 미탐지 조합 수를 뜻하며 안전 검증 완료를 의미하지 않습니다.
9. `pairs`를 위험도 높은 순(`danger` > `caution` > `safe`)으로 정렬, `overall`은 최상위 등급

### 제품명/성분명 매칭

- 알약 인식 결과의 `product_name`이 들어오면 `pill_product_ingredients`를 통해 여러 성분으로 확장됩니다.
- 같은 성분이 여러 입력에서 반복되면 중복 제거 후 분석합니다.
- `PTP`, `PVC`, `ALU`, 단순 함량값, 포장 단위처럼 성분이 아닌 값은 분석에서 제외될 수 있습니다.
- 건강기능식품은 표준명, 원문명, alias, 일부 부분 일치 순으로 해석합니다.
- 해석 실패 항목은 실패 카운트에 반영되며, 프론트는 사용자가 직접 수정할 수 있게 표시하는 것이 좋습니다.

### 다국어 (`lang`)

| 값 | 적용 범위 |
|---|---|
| `summary` | 고정 문구 — 자체 번역 테이블 즉시 적용 (`app/i18n.py`) |
| `description` | DB 원문(한국어) — DeepL API로 실시간 번역 (`app/services/translator.py`) |
| `pairs[].items` | 번역 안 됨 — DB canonical name 그대로 |
| `overall` / `level` | 번역 안 됨 — 고정 enum (`danger`/`caution`/`safe`), 화면 라벨은 프론트엔드에서 `lang`에 맞춰 직접 매핑 |

`DEEPL_API_KEY` 미설정 시 `description`은 번역 없이 한국어 원문 그대로 반환됩니다 (오류 발생하지 않음, fail-safe).

**에러**
- `422 Unprocessable Entity` — 요청 바디 형식 오류 (`items` 누락 등)
- `500 Internal Server Error` — DB 연결 실패 등 서버 내부 오류

---

## 공통 사항

- 모든 응답은 `application/json`
- CORS: 모든 origin 허용 (`allow_origins=["*"]`)
- 인증: 없음 (현재 버전 기준)
- Swagger UI: `GET /docs`
- OpenAPI 스키마: `GET /openapi.json`
