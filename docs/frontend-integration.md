# 프론트엔드 연동 가이드

프론트엔드 팀원이 서버를 실행하고 API를 연동하기 위한 가이드입니다.

---

## 1. 서버 구성

총 3개의 서버가 필요합니다.

| 서버 | 담당 | 주소 | 용도 |
|---|---|---|---|
| 백엔드 | backend 레포 | `http://localhost:8000` 또는 tunnel URL | 상호작용 분석, 성분 매칭 |
| supplement 서버 | ai 레포 | `http://localhost:8001` 또는 tunnel URL | 건강기능식품 라벨 인식 |
| pill 서버 | ai 레포 | `http://localhost:8001` 또는 별도 pill API port | 알약 인식 |

프론트는 Expo 환경변수로 각 서버 주소를 받습니다.

```env
EXPO_PUBLIC_BACKEND_URL=https://backend.example.com
EXPO_PUBLIC_SUPPLEMENT_AI_URL=https://supplement-ai.example.com
EXPO_PUBLIC_PILL_AI_URL=https://pill-ai.example.com
```

동일 AI 서버에서 supplement/pill endpoint를 모두 노출하는 경우 `EXPO_PUBLIC_SUPPLEMENT_AI_URL`과 `EXPO_PUBLIC_PILL_AI_URL`을 같은 값으로 둘 수 있습니다.

---

## 2. 백엔드 서버 실행 방법

### 사전 준비

1. `.env` 파일 생성 (`.env.example` 복사 후 수정):

```
MYSQL_ROOT_PASSWORD=clickbackend0625
MYSQL_DATABASE=click_backend_db
MYSQL_USER=click_user
MYSQL_PASSWORD=click0623
MYSQL_HOST=localhost
MYSQL_PORT=3306
DEEPL_API_KEY=발급받은_키   ← 다국어 번역용, 없으면 한국어로만 동작
```

2. 패키지 설치:

```bash
pip install -r requirements.txt
```

### 실행

```bash
# MySQL DB 실행 (Docker 필요)
docker compose up -d

# 서버 실행
uvicorn app.main:app --reload
```

- Swagger UI: `http://localhost:8000/docs`
- 헬스체크: `http://localhost:8000/health` → `{ "status": "ok" }`

---

## 3. supplement 서버 실행 방법

`ai/` 디렉터리에서 실행합니다.

```bash
# DB 실행
docker compose up -d

# 서버 실행
uvicorn app.main:app --reload --port 8002
```

- Swagger UI: `http://localhost:8002/docs`
- 헬스체크: `http://localhost:8002/health`

---

## 4. 프론트엔드 코드 수정 사항

### 4-1. 서버 주소 설정

프론트는 코드 상수 대신 Expo public env를 사용합니다.

| 변수 | 연결 대상 |
|---|---|
| `EXPO_PUBLIC_BACKEND_URL` | `/api/v1/interactions/analyze` |
| `EXPO_PUBLIC_SUPPLEMENT_AI_URL` | `/api/v1/supplement/recognize` 또는 supplement 서버 root |
| `EXPO_PUBLIC_PILL_AI_URL` | `/recognize` 또는 `/api/v1/pill/recognize` |

Cloudflare Tunnel 또는 ngrok을 사용할 때도 위 값을 tunnel URL로 바꾸면 됩니다.

### 4-2. 분석 API 요청 바디

백엔드는 `name`과 `category`를 기준으로 분석합니다. `dosage`는 프론트 표시용으로 둘 수 있지만 API 분석에는 필요하지 않습니다.

```ts
{
  items: items.map((it) => ({ name: it.name, category: it.category })),
  lang: "ko"
}
```

알약 `name`에는 제품명 또는 성분명이 들어올 수 있습니다. 제품명은 백엔드의 `pill_product_ingredients`에서 성분으로 확장됩니다.

### 4-3. 다국어 지원 (선택)

언어 전환 버튼을 구현할 경우 `lang` 필드를 추가해서 보내면 됩니다:

```ts
{
  items: items.map((it) => ({ name: it.name, category: it.category })),
  lang: currentLang,  // "ko" | "en" | "fr"
}
```

- `summary`, `description`이 해당 언어로 번역되어 반환됩니다.
- `overall` / `level` 값(`danger`/`caution`/`safe`)은 항상 영문 고정 — 화면 표시 라벨은 프론트에서 직접 매핑하세요.
- `lang` 생략 시 기본값은 `"ko"`입니다.

---

## 5. 전체 연동 흐름

```
[1단계] 알약 사진 촬영
        ↓
[2단계] pill 서버
        POST {pill_서버_주소}/recognize
        multipart/form-data, field: file
        선택 field: recognizer=codeit | retrieval | aihub_classifier
        ↓
        응답에서 약물명 추출:
        candidates[0].product_name / ingredient
        후보가 여러 개면 프론트에서 Top-3 확인 UI 표시
        → { name: "제품명 또는 성분명", category: "알약" }

[1단계] 건기식 사진 촬영
        ↓
[2단계] supplement 서버 (port 8002)
        POST /api/v1/supplement/recognize
        multipart/form-data, field: image
        ↓
        응답에서 성분명 추출:
        product.ingredients 배열 각 항목
        product.product_image_url은 인식 결과 확인 UI에 표시 가능
        → { name: "비타민C", category: "건강기능식품 라벨" }

[3단계] 사용자 확인·수정 화면
        두 결과 합쳐서 목록 표시, 수정 가능
        ↓
[4단계] 백엔드 (port 8000)
        POST /api/v1/interactions/analyze
        {
          "items": [
            { "name": "아스피린", "category": "알약" },
            { "name": "비타민C", "category": "건강기능식품 라벨" }
          ],
          "lang": "ko"
        }
        ↓
        응답: { overall, summary, pairs, matchedDrugNames, matchedSupplementNames, checkedCount, ... }

[5단계] 결과 화면 표시
```

---

## 6. API 응답 타입

기존 `types/medication.ts`의 타입과 백엔드 응답이 일치합니다. 별도 수정 불필요.

```ts
// AnalysisResult — 백엔드 응답과 동일
interface AnalysisResult {
  overall: RiskLevel;       // "danger" | "caution" | "safe"
  summary: string;          // 종합 안내 문구
  pairs: InteractionPair[];
  matchedDrugNames: string[];
  matchedSupplementNames: string[];
  ignoredDrugNames: string[];
  checkedCount: number;
  detectedCount: number;
  undetectedCount: number;
  unmatchedSupplementCount: number;
  unmatchedDrugCount: number;
  unmatchedCombinationCount: number;
}

interface InteractionPair {
  id: string;
  items: string[];          // [성분명, 약물명]
  level: RiskLevel;
  description: string;      // 상호작용 설명
}
```

---

## 7. 에러 처리

| 상황 | HTTP 코드 | 응답 |
|---|---|---|
| 요청 바디 형식 오류 | `422` | `{ "detail": [...] }` |
| DB 연결 실패 등 서버 오류 | `500` | `{ "detail": "에러 메시지" }` |

---

## 8. 참고

- 전체 API 명세: [`docs/api-spec.md`](api-spec.md)
- `pairs`가 비어 있거나 `undetectedCount`가 크다고 해서 안전 검증이 끝난 것은 아닙니다. 현재 DB에서 주의 근거가 발견되지 않았다는 의미입니다.
- 알약 인식 엔진은 독립 pill API에서 `recognizer` form field로 선택할 수 있습니다. 현재 지원값은 `codeit`, `retrieval`, `aihub_classifier`입니다.
- 통합 AI 서버의 `/api/v1/pill/recognize` 래퍼는 기본 recognizer를 사용합니다. recognizer를 프론트에서 바꾸려면 독립 pill API `/recognize` 사용을 권장합니다.
