# DB 초기 설정 가이드

처음 백엔드를 세팅하는 팀원을 위한 DB 구축 가이드입니다.

---

## 사전 준비

### 1. 필수 파일 확인

`drug-supplement schema v2` 폴더가 로컬에 있어야 합니다. 팀 공유 드라이브나 담당자에게 받아주세요.

폴더 안에 아래 7개 CSV 파일이 있어야 합니다:

```
drug-supplement schema v2/
├── canonical_drug_entities.csv     # 178행 — 표준 약물 엔티티
├── drug_aliases.csv                # 378행 — 약물 별칭
├── supplement_entities.csv         # 33행  — 건기식 표준 엔티티
├── source_claims.csv               # 138행 — 상호작용 원문 클레임
├── standardized_interactions.csv   # 475행 — 건기식×약물 상호작용
├── pill_products.csv               # 4,525행 — 알약 제품 목록
└── pill_product_ingredients.csv    # 892행 — 알약 제품별 성분
```

### 2. `.env` 설정

`.env.example`을 복사해 `.env` 파일을 만들고 값을 채웁니다:

```
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_DATABASE=click_backend_db
MYSQL_USER=click_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
DEEPL_API_KEY=your_deepl_api_key
```

> `DEEPL_API_KEY`는 없어도 됩니다. 없으면 다국어 번역 없이 한국어 원문 그대로 반환됩니다.

---

## DB 구축 순서

### 1단계 — Docker DB 컨테이너 실행

```powershell
docker compose up -d db
```

컨테이너가 처음 뜰 때 `db/init.sql`이 자동으로 실행되어 테이블이 생성됩니다.

### 2단계 — 데이터 적재

```powershell
python scripts/load_interaction_data.py
```

스크립트가 `drug-supplement schema v2/` 폴더의 CSV를 읽어 DB에 순서대로 넣습니다.

**폴더 경로가 다를 경우** `--processed-dir` 옵션으로 직접 지정합니다:

```powershell
python scripts/load_interaction_data.py --processed-dir "C:\경로\drug-supplement schema v2"
```

### 3단계 — 확인

```powershell
docker exec -it click_backend_db mysql -u click_user -p click_backend_db
```

```sql
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'click_backend_db'
ORDER BY table_name;
```

아래와 같이 나오면 정상입니다:

| table_name | table_rows |
|---|---|
| canonical_drug_entities | 178 |
| drug_aliases | 378 |
| pill_product_ingredients | 892 |
| pill_products | 4525 |
| source_claims | 138 |
| standardized_interactions | 475 |
| supplement_entities | 33 |

---

## 자주 겪는 문제

### DB에 연결이 안 될 때

`.env`의 `MYSQL_HOST`가 `db`로 되어 있으면 로컬 직접 실행 시 연결 실패합니다.
로컬에서 스크립트를 실행할 때는 반드시 `127.0.0.1`로 설정하세요.

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
```

> Docker 컨테이너 내부(api 서비스)에서는 `MYSQL_HOST=db`를 사용합니다.

### 테이블은 있는데 데이터가 없을 때

2단계 적재 스크립트를 실행하지 않았거나 CSV 폴더 경로가 틀린 경우입니다.
`--processed-dir` 옵션으로 정확한 경로를 지정해서 다시 실행하세요.

### DB를 초기화하고 싶을 때

```powershell
docker compose down -v
docker compose up -d db
python scripts/load_interaction_data.py
```

`-v` 옵션이 볼륨(데이터)까지 삭제합니다.
