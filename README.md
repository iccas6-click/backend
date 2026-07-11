# CLICK Backend

건강기능식품·보충제와 약물 간 상호작용을 분석하는 백엔드 서버입니다.

---

## DB 아키텍처 (v3)

| DB | 포트 | 역할 |
|---|---|---|
| Backend DB (`click_backend_db`) | **3307** | 상호작용 분석 |
| AI DB (`click_db`) | **3306** | 제품명 → 성분 조회 |

### Backend DB 테이블 (이 레포에서 관리)

| 테이블 | 행 수 | 설명 |
|---|---:|---|
| canonical_drug_entities | 178 | 표준 약물 성분 |
| drug_aliases | 378 | 약물명 변형 매핑 |
| supplement_entities | 33 | 표준 건기식 성분 |
| source_claims | 138 | 상호작용 근거 원문 |
| standardized_interactions | 475 | 건기식–약물 상호작용 (33성분 × 178약물) |

### AI DB 테이블 (`click/ai` 레포에서 관리)

| 테이블 | 행 수 |
|---|---:|
| supplement_info | 44,885 |
| supplement_product_markers | 69,845 |
| pill_products | 4,525 |
| pill_product_ingredients | 892 |

### 상호작용 커버리지 측정 결과

| 지표 | 수치 | 설명 |
|---|---|---|
| 건기식 DB Top-1 매칭 정확도 | **84.0%** (42/50장) | Gemini 추출명 → MFDS DB Top-1 매칭 |
| 건기식 성분 해석율 F1 | **79.6%** | Precision 100%, Recall 66.1% |
| 처방전 DB 매칭 정확도 | **94.7%** (89/94건) | pill_products LIKE 기준 |
| 처방전 인식 F1 | **95.7%** | Precision 93.7%, Recall 97.8% |
| 상호작용 DB 역조회 정확도 | **100%** (475/475건) | standardized_interactions 전체 역조회 성공 |
| 처방약×건기식 상호작용 감지율 | **8.7%** (40/462 조합) | 처방전 14종 × supplement_entities 33종 |
| 고위험 약물 커버 | **14/78종** | pill_products 매칭 약물 중 상호작용 DB 연결 가능 |

---

## 전체 데이터 처리 흐름

```text
[Backend DB]
  canonical_drug_entities + supplement_entities + source_claims
    → standardized_interactions (건기식–약물 상호작용 475건)
  drug_aliases
    → 약물명 변형 → canonical_drug_id 매핑

[AI DB — click/ai 레포]
  pill_products + pill_product_ingredients
    → 알약 제품명 → 약물 성분 확장
  supplement_info (식약처 MFDS 건기식 제품 DB)
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
# Backend DB 5개 테이블 적재 (canonical_drug_entities, supplement_entities, source_claims, drug_aliases, standardized_interactions)
python scripts/import_v3_data.py --csv-dir "C:\경로\drug-supplement schema v3"
```

> AI DB(supplement_info, pill_products 등) 적재는 `click/ai` 레포의 [`docs/db-setup.md`](../ai/docs/db-setup.md)를 참고하세요.

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
│   └── init.sql            # MySQL 테이블 생성 (5개 테이블)
├── docs/
│   ├── db-setup.md         # DB 구축 가이드
│   ├── db-schema.md        # 테이블 스키마 명세
│   ├── api-spec.md         # API 명세
│   └── frontend-integration.md
├── scripts/
│   └── import_v3_data.py   # CSV → MySQL 적재 (v3)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 주의사항

- 이 서비스는 의료적 판단, 처방 또는 의료진의 판단을 대체하지 않습니다.
- 상호작용이 감지되지 않았다고 해서 안전이 보장된 것은 아닙니다. 현재 DB에서 주의 근거가 발견되지 않았다는 의미입니다.
