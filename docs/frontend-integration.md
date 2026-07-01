# 프론트엔드 연동 가이드

프론트엔드 팀원이 서버를 실행하고 API를 연동하기 위한 가이드입니다.

---

## 1. 서버 구성

총 3개의 서버가 필요합니다.

| 서버 | 담당 | 주소 | 용도 |
|---|---|---|---|
| 백엔드 | 강민 | `http://localhost:8000` | 상호작용 분석 |
| supplement 서버 | 강민 | `http://localhost:8002` | 건강기능식품 라벨 인식 |
| pill 서버 | 팀원 담당 | 별도 주소 확인 필요 | 알약 인식 |

> pill 서버 주소는 팀원에게 따로 확인하세요.

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

`services/ocr.ts`의 `API_BASE_URL`을 서버 주소로 채워야 합니다:

```ts
// 현재 (목업 모드)
export const API_BASE_URL = '';

// 로컬 개발 시
export const API_BASE_URL = 'http://localhost:8000';

// 외부 접근 시 (Cloudflare Tunnel 등)
export const API_BASE_URL = 'https://xxxx.trycloudflare.com';
```

### 4-2. 분석 API 경로 수정

`services/interactions.ts`의 호출 경로를 수정해야 합니다:

```ts
// 현재 코드 (잘못된 경로)
`${API_BASE_URL}/api/interactions`

// 수정 후 (실제 경로)
`${API_BASE_URL}/api/v1/interactions/analyze`
```

### 4-3. 요청 바디 수정

백엔드는 `dosage` 필드를 받지 않습니다. `name`과 `category`만 보내면 됩니다:

```ts
// 현재 코드
items.map((it) => ({ name: it.name, dosage: it.dosage, category: it.category }))

// 수정 후
items.map((it) => ({ name: it.name, category: it.category }))
```

### 4-4. 다국어 지원 (선택)

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
        ↓
        응답에서 약물명 추출:
        candidates[0].drug_canonical_ko   ← 있으면 우선 사용
        candidates[0].product_name        ← 없을 때 대체
        → { name: "아스피린", category: "알약" }

[1단계] 건기식 사진 촬영
        ↓
[2단계] supplement 서버 (port 8002)
        POST /api/v1/supplement/recognize
        multipart/form-data, field: image
        ↓
        응답에서 성분명 추출:
        product.ingredients 배열 각 항목
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
        응답: { overall, summary, pairs }

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
- 상호작용 DB에 없는 성분은 자동으로 `safe` 처리됩니다 (실제 안전을 보장하지 않음)
