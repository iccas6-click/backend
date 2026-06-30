# 프론트엔드 연동 가이드

## 서버 포트 정리

| 서버 | 포트 | 용도 |
|---|---|---|
| 백엔드 | 8000 | 상호작용 분석 |
| pill 서버 | 8001 | 알약 인식 (팀원 담당) |
| supplement 서버 | 8002 | 건강기능식품 인식 |

---

## 서버 실행

```bash
# backend/ 루트에서
docker compose up -d        # MySQL DB 실행
uvicorn app.main:app --reload --port 8000
```

헬스체크: `GET /health` → `{ "status": "ok" }`

---

## 엔드포인트

### 1. 단일 성분 상호작용 조회

기존 엔드포인트. 성분 하나의 원시 상호작용 데이터를 반환합니다.

```
GET /api/v1/interactions?supplement={성분명}
```

**예시**
```
GET /api/v1/interactions?supplement=오메가3
```

**응답**
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

---

### 2. 다중 항목 상호작용 분석 ← **프론트엔드 메인 연동 대상**

촬영한 알약 + 건강기능식품 목록을 한번에 보내면 프론트엔드 화면에 바로 표시할 수 있는 형식으로 반환합니다.

```
POST /api/v1/interactions/analyze
Content-Type: application/json
```

**요청 바디**
```json
{
  "items": [
    { "name": "아스피린", "category": "알약" },
    { "name": "오메가-3 지방산", "category": "건강기능식품 라벨" },
    { "name": "비타민D", "category": "건강기능식품 라벨" }
  ],
  "lang": "ko"
}
```

- `category` 값: `"알약"` 또는 `"건강기능식품 라벨"` (프론트엔드 `ItemCategory` 타입과 동일)
- `name`: AI 서버가 반환한 성분명 또는 사용자가 입력한 이름
  - 개별인정원료 브랜드명(예: `TWK10`, `락토핏`)도 alias 테이블로 자동 해석
- `lang`: `"ko"`(기본값) | `"en"` | `"fr"` — 생략하면 한국어로 응답 (버튼 등으로 사용자가 언어 전환 시 이 값만 바꿔서 보내면 됨)

**응답**
```json
{
  "overall": "caution",
  "summary": "일부 조합에서 주의가 필요합니다. 전문가와 상담을 권장합니다.",
  "pairs": [
    {
      "id": "1",
      "items": ["오메가-3 지방산", "아스피린"],
      "level": "caution",
      "description": "함께 복용 시 출혈 위험이 증가할 수 있음. 주의가 필요합니다."
    }
  ]
}
```

**`overall` / `level` 값**
| 값 | 의미 |
|---|---|
| `"danger"` | 위험 — 복용 전 반드시 전문가 상담 필요 |
| `"caution"` | 주의 — 전문가 상담 권장 |
| `"safe"` | 안전 — 확인된 상호작용 없음 |

**동작 방식**
1. `items`를 `알약` / `건강기능식품 라벨`로 분류
2. 건강기능식품 성분 × 알약 조합을 DB에서 조회
3. 알약이 없으면 건강기능식품 성분의 전체 상호작용 반환
4. `interaction_text_raw` 키워드로 위험도 자동 추론
5. 위험도 높은 순 정렬 후 `overall`은 가장 높은 등급

**건강기능식품만 있는 경우**
```json
// 요청
{ "items": [{ "name": "비타민D", "category": "건강기능식품 라벨" }] }

// 응답 — DB에 해당 성분 상호작용 데이터가 없으면
{
  "overall": "safe",
  "summary": "확인된 상호작용이 없습니다. 복용 전 전문가와 상담하세요.",
  "pairs": []
}
```

**건강기능식품이 없는 경우**
```json
// 요청
{ "items": [{ "name": "아스피린", "category": "알약" }] }

// 응답
{
  "overall": "safe",
  "summary": "분석할 건강기능식품이 없습니다.",
  "pairs": []
}
```

---

### 다국어 (lang)

`lang`을 `"en"` 또는 `"fr"`로 보내면 `summary`와 `description`이 번역되어 반환됩니다.

- `summary`: 고정 문구는 즉시 번역 (자체 번역 테이블)
- `description`: DB 원문(한국어)을 DeepL API로 실시간 번역
- `overall` / `level` 값(`danger`/`caution`/`safe`)은 언어와 무관하게 항상 동일한 enum — 화면 표시 라벨("위험"/"Danger"/"Danger")은 프론트엔드에서 `lang`에 맞춰 직접 매핑

```json
// 요청
{
  "items": [
    { "name": "아스피린", "category": "알약" },
    { "name": "오메가-3 지방산", "category": "건강기능식품 라벨" }
  ],
  "lang": "fr"
}

// 응답
{
  "overall": "danger",
  "summary": "Une combinaison dangereuse a été détectée. Consultez un professionnel avant toute prise.",
  "pairs": [
    {
      "id": "1",
      "items": ["EPA 및 DHA 함유 유지(오메가-3 지방산)", "아스피린"],
      "level": "danger",
      "description": "Cela peut augmenter le risque d'hémorragie !"
    }
  ]
}
```

`items` 배열 안의 성분명·약물명(`EPA 및 DHA 함유 유지...`, `아스피린`)은 DB의 canonical 이름이라 번역되지 않고 한국어 그대로 반환됩니다.

---

## 전체 연동 흐름

```
[1단계] 알약 사진 촬영
        ↓
[2단계] pill 서버 (port 8001)
        POST /recognize
        multipart/form-data, field: file
        → { candidates: [{ product_name, drug_canonical_ko, ... }], ... }
        ↓  candidates[0].product_name 또는 drug_canonical_ko 추출
        → RecognizedItem { name: "아스피린", category: "알약" }

[1단계] 건기식 사진 촬영
        ↓
[2단계] supplement 서버 (port 8002)
        POST /api/v1/supplement/recognize
        multipart/form-data, field: image
        → { status, product: { product_name, ingredients: ["비타민C", "오메가-3", ...], confidence } }
        ↓  ingredients 각 항목 추출
        → RecognizedItem { name: "비타민C", category: "건강기능식품 라벨" }

[3단계] 사용자 확인·수정 화면
        두 결과를 합쳐서 목록 표시, 사용자가 수정 가능
        ↓
[4단계] 백엔드 (port 8000)
        POST /api/v1/interactions/analyze
        { items: [
            { name: "아스피린", category: "알약" },
            { name: "비타민C", category: "건강기능식품 라벨" },
            { name: "오메가-3", category: "건강기능식품 라벨" }
          ] }
        → AnalysisResult { overall, summary, pairs }
        ↓
[5단계] 결과 화면 표시
```

### pill 서버 응답에서 약물명 추출 방법

```json
// POST /recognize 응답 구조 (요약)
{
  "candidates": [
    {
      "pill_id": "123456",
      "product_name": "아스피린정100mg",
      "drug_canonical_ko": "아스피린",
      "score": 92.3
    }
  ]
}
```

백엔드 `/interactions/analyze`에 넘길 이름은 `candidates[0].drug_canonical_ko` 또는 `candidates[0].product_name`을 사용합니다.
- `drug_canonical_ko`가 있으면 우선 사용 (상호작용 DB 매칭에 유리)
- 없으면 `product_name` 사용

---

## 에러 응답

```json
// 500 Internal Server Error
{ "detail": "에러 메시지" }
```

DB 연결 실패, 쿼리 오류 등 서버 내부 문제 발생 시 반환됩니다.

---

## 현재 데이터 범위

- 건강기능식품 성분: 식약처 고시형 원료 및 개별인정원료 포함
- 약물 상호작용 DB: `standardized_interactions` 테이블 기준
- 개별인정원료 alias: 157건 (`supplement_aliases` 테이블)
- DB에 없는 성분은 상호작용 없음(`safe`)으로 처리됨 — 실제 안전을 보장하지 않음
