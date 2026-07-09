# DB 초기 설정 가이드

처음 백엔드를 세팅하는 팀원을 위한 DB 구축 가이드입니다.

---

## 사전 준비

### 1. 필수 폴더 확인

두 폴더가 모두 로컬에 있어야 합니다. 팀 공유 드라이브나 담당자에게 받아주세요.

**`drug-supplement schema/drug-supplement schema/processed/`** — v1 데이터 폴더

핵심 테이블 CSV와 각종 분석 보조 파일이 들어 있습니다. 이 폴더로 적재하면 9개 테이블 전체가 v1 데이터로 채워집니다.  
이후 v2로 재적재하면 `supplement_info`와 `supplement_product_markers`를 제외한 7개 테이블이 최신 데이터로 덮어씌워집니다.

**`drug-supplement schema v2/`** — 상호작용 분석 핵심 데이터

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

### 2단계 — v1 데이터 적재 (9개 테이블 전체)

`drug-supplement schema/drug-supplement schema/processed/` 폴더를 지정해서 실행합니다.

```powershell
python scripts/load_interaction_data.py --processed-dir "C:\경로\drug-supplement schema\drug-supplement schema\processed"
```

> `C:\경로` 부분을 실제 로컬 경로로 바꿔서 실행하세요.

스크립트가 폴더 안의 CSV를 읽어 **9개 테이블 전체**를 적재합니다. `supplement_info`(44,885행)와 `supplement_product_markers`(70,018행)는 이 단계에서만 들어옵니다.

| 테이블 | v1 적재 행 수 |
|---|---:|
| canonical_drug_entities | 178 |
| pill_products | 993 |
| drug_aliases | 378 |
| pill_product_ingredients | 313 |
| supplement_entities | 33 |
| source_claims | 138 |
| standardized_interactions | 475 |
| supplement_info | 44,885 |
| supplement_product_markers | 70,018 |

### 3단계 — v2 데이터 적재 (핵심 7개 테이블 덮어쓰기)

```powershell
python scripts/load_interaction_data.py
```

v2에는 `supplement_info`, `supplement_product_markers`가 없으므로 스크립트가 자동으로 건너뜁니다. 핵심 7개 테이블만 v2 데이터로 덮어씌워집니다.

스크립트가 `drug-supplement schema v2/` 폴더의 CSV를 읽어 DB에 순서대로 넣습니다.

**폴더 경로가 다를 경우** `--processed-dir` 옵션으로 직접 지정합니다:

```powershell
python scripts/load_interaction_data.py --processed-dir "C:\경로\drug-supplement schema v2"
```

### 4단계 — DB 접속 및 데이터 확인

#### MySQL 접속

```powershell
docker exec -it click_backend_db mysql -u click_user -p click_backend_db
```

비밀번호 입력 프롬프트가 뜨면 `.env`의 `MYSQL_PASSWORD` 값을 입력합니다.

> `click_backend_db`가 컨테이너 이름과 다를 경우 `docker ps`로 실제 컨테이너 이름을 확인하세요.

#### 테이블 목록 확인

```sql
SHOW TABLES;
```

9개 테이블이 모두 있어야 합니다:

```
canonical_drug_entities
drug_aliases
pill_product_ingredients
pill_products
source_claims
standardized_interactions
supplement_entities
supplement_info
supplement_product_markers
```

#### 테이블별 데이터 개수 확인

`information_schema`의 `table_rows`는 근사치라 실제 개수와 다를 수 있습니다. 정확한 개수는 `COUNT(*)`로 확인합니다:

```sql
SELECT 'canonical_drug_entities'   AS tbl, COUNT(*) AS cnt FROM canonical_drug_entities
UNION ALL
SELECT 'drug_aliases',                      COUNT(*) FROM drug_aliases
UNION ALL
SELECT 'pill_products',                     COUNT(*) FROM pill_products
UNION ALL
SELECT 'pill_product_ingredients',          COUNT(*) FROM pill_product_ingredients
UNION ALL
SELECT 'supplement_entities',               COUNT(*) FROM supplement_entities
UNION ALL
SELECT 'source_claims',                     COUNT(*) FROM source_claims
UNION ALL
SELECT 'standardized_interactions',         COUNT(*) FROM standardized_interactions
UNION ALL
SELECT 'supplement_info',                   COUNT(*) FROM supplement_info
UNION ALL
SELECT 'supplement_product_markers',        COUNT(*) FROM supplement_product_markers;
```

아래와 같이 나오면 정상입니다:

| tbl | cnt |
|---|---:|
| canonical_drug_entities | 178 |
| drug_aliases | 378 |
| pill_products | 4525 |
| pill_product_ingredients | 892 |
| supplement_entities | 33 |
| source_claims | 138 |
| standardized_interactions | 475 |
| supplement_info | 44885 |
| supplement_product_markers | 70018 |

#### MySQL 접속 종료

```sql
EXIT;
```

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

적재 스크립트를 실행하지 않았거나 CSV 폴더 경로가 틀린 경우입니다.
`--processed-dir` 옵션으로 정확한 경로를 지정해서 2단계 → 3단계 순서로 다시 실행하세요.

### supplement_info / supplement_product_markers 가 비어 있을 때

`drug-supplement schema v2/`에는 이 두 파일이 없습니다. 2단계에서 v1 폴더를 지정해서 먼저 실행했는지 확인하세요.

### DB를 초기화하고 싶을 때

```powershell
docker compose down -v
docker compose up -d db
python scripts/load_interaction_data.py --processed-dir "C:\경로\drug-supplement schema\drug-supplement schema\processed"
python scripts/load_interaction_data.py
```

`-v` 옵션이 볼륨(데이터)까지 삭제합니다. 초기화 후에는 v1 → v2 순서로 두 번 실행해야 합니다.
