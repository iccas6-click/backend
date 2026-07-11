# CLICK Backend

건강기능식품·보충제와 약물 간 상호작용을 분석하는 백엔드 서버입니다.

---

## DB 아키텍처 (v3)

| DB | 포트 | 역할 |
|---|---|---|
| AI DB (`click_db`) | 3306 | 제품명 → 성분 조회 (pill_products, supplement_info 등) |
| Backend DB (`click_backend_db`) | 3307 | 상호작용 분석 (standardized_interactions, canonical_drug_entities 등) |

### Backend DB 데이터 규모

| 테이블 | 행 수 | 설명 |
|---|---|---|
| canonical_drug_entities | 178 | 표준 약물 성분 |
| drug_aliases | 378 | 약물명 변형 매핑 |
| supplement_entities | 33 | 표준 건기식 성분 |
| source_claims | 138 | 상호작용 근거 원문 |
| standardized_interactions | **475** | 건기식–약물 상호작용 (33성분 × 178약물) |

### 상호작용 커버리지 측정 결과

| 지표 | 수치 | 설명 |
|---|---|---|
| 건기식 DB 매칭 정확도 | **32.0%** (16/50장) | supplement_info → supplement_entities 연결 |
| 처방전 canonical_drug_id 확보율 | **28.6%** (26/91건) | pill_product_ingredients 기준 |
| 상호작용 커버리지 | **3.2%** (32/1,000 조합) | 처방전 20장 × 건기식 50장 기준 |
| 매핑 성공 조합 중 감지율 | **16.7%** (32/192) | 양쪽 매핑 성공 시 상호작용 존재 비율 |

> 병목: 건기식 supplement_entities 33종 / pill_product_ingredients canonical_drug_id 29% 커버로 인한 미연결

---

## 전체 데이터 처리 흐름

```text
[v2] canonical_drug_entities + supplement_entities + source_claims
  → standardized_interactions (건기식–약물 상호작용 475건)

[v2] pill_products + pill_product_ingredients
  → 알약 제품명 → 약물 성분 확장

[v2] drug_aliases
  → 약물명 변형 → canonical_drug_id 매핑

[v1] supplement_info (식약처 MFDS 건기식 제품 DB)
  → supplement_product_markers (성분 파싱 결과)
  → supplement_entities 매핑
```

---

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

`DEEPL_API_KEY`는 없어도 됩니다. 없으면 다국어 번역 없이 한국어 원문 그대로 반환됩니다.

### Docker DB 실행

```powershell
docker compose up -d db
```

### 데이터 적재

자세한 설명은 [`docs/db-setup.md`](docs/db-setup.md)를 참고하세요.

```powershell
# 1단계: v1 데이터 (supplement_info / supplement_product_markers)
python scripts/load_interaction_data.py --processed-dir "C:\경로\drug-supplement schema\drug-supplement schema\processed"

# 2단계: v2 데이터 (핵심 상호작용 데이터)
python scripts/load_interaction_data.py
```

### FastAPI 서버 실행

```powershell
uvicorn app.main:app --reload
```

서버 실행 후 `http://localhost:8000/docs` 에서 Swagger UI로 API 테스트 가능.

---

## 주요 API

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 확인 |
| POST | `/api/v1/interactions/analyze` | 알약 + 건기식 다중 항목 상호작용 분석 |

### POST /api/v1/interactions/analyze

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

`overall` / `level`: `"danger"` | `"caution"` | `"safe"`

`lang`: `"ko"`(기본값) | `"en"` | `"fr"` — `DEEPL_API_KEY` 설정 시 `description` 번역 지원.

자세한 연동 방법은 [`docs/frontend-integration.md`](docs/frontend-integration.md)를 참고하세요.

---

## 디렉터리 구조

```text
backend/
├── app/
│   ├── api/v1/endpoints/   # API 엔드포인트
│   ├── core/               # 설정 (환경변수)
│   ├── db/                 # DB 연결
│   ├── schemas/            # Pydantic 응답 스키마
│   ├── services/           # supplement_resolver, drug_resolver, translator
│   └── main.py
├── db/
│   └── init.sql            # MySQL 테이블 생성 (8개 테이블)
├── docs/
│   ├── db-setup.md         # DB 구축 가이드
│   ├── db-schema.md        # 테이블 스키마 명세
│   ├── api-spec.md         # API 명세
│   └── frontend-integration.md
├── scripts/
│   └── load_interaction_data.py  # CSV → MySQL 적재
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 주의사항

- 이 서비스는 의료적 판단, 처방 또는 의료진의 판단을 대체하지 않습니다.
- 상호작용이 감지되지 않았다고 해서 안전이 보장된 것은 아닙니다. 현재 DB에서 주의 근거가 발견되지 않았다는 의미입니다.
