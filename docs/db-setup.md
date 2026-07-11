# DB 구축 가이드

처음 세팅하는 팀원을 위한 단계별 DB 구축 가이드입니다.

---

## 전체 구조

CLICK은 **DB가 두 개**로 나뉘어 있습니다.

| DB | 포트 | 레포 | 역할 |
|---|---|---|---|
| AI DB (`click_db`) | **3306** | `click/ai` | 제품명 → 성분 조회 |
| Backend DB (`click_backend_db`) | **3307** | `click/backend` | 상호작용 분석 |

두 DB 모두 **`drug-supplement schema v3/`** 폴더 안의 CSV 파일로 적재합니다.

```
drug-supplement schema v3/
├── supplement_info.csv              → AI DB
├── supplement_product_markers.csv   → AI DB
├── pill_products.csv                → AI DB
├── pill_product_ingredients.csv     → AI DB
├── canonical_drug_entities.csv      → Backend DB
├── drug_aliases.csv                 → Backend DB
├── supplement_entities.csv          → Backend DB
├── source_claims.csv                → Backend DB
└── standardized_interactions.csv    → Backend DB
```

---

## 사전 준비

### 1. 필수 환경

- Docker Desktop 실행 중인 상태
- Python 3.10 이상
- 두 레포 클론 완료: `click/ai`, `click/backend`
- `drug-supplement schema v3/` 폴더를 로컬에 보유 (팀 드라이브에서 받아야 함)

### 2. Backend DB `.env` 설정

`click/backend/.env.example`을 복사해 `.env` 생성:

```
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_DATABASE=click_backend_db
MYSQL_USER=click_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
DEEPL_API_KEY=your_deepl_api_key
```

> `DEEPL_API_KEY`는 없어도 됩니다. 없으면 한국어 원문 그대로 반환됩니다.

### 3. AI DB `.env` 설정

`click/ai/.env.example`을 복사해 `.env` 생성:

```
GEMINI_API_KEY=your_gemini_api_key
CBNUAI_API_KEY=your_cbnuai_api_key

MYSQL_DATABASE=click_db
MYSQL_USER=click_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

PILL_MYSQL_HOST=127.0.0.1
PILL_MYSQL_PORT=3307
PILL_MYSQL_DATABASE=click_backend_db
PILL_MYSQL_USER=click_user
PILL_MYSQL_PASSWORD=your_backend_password
```

### 4. Python 의존성 설치

각 레포 루트에서:

```powershell
# backend
cd click/backend
pip install -r requirements.txt

# ai
cd click/ai
pip install -r requirements.txt
```

---

## DB 구축 순서

### 1단계 — 컨테이너 실행

두 레포 각각에서 Docker DB를 실행합니다.

```powershell
# Backend DB (포트 3307)
cd click/backend
docker compose up -d db

# AI DB (포트 3306)
cd click/ai
docker compose up -d db
```

컨테이너가 처음 뜰 때 각각의 `init.sql`이 자동 실행되어 테이블이 생성됩니다.

- Backend DB 테이블 정의: `backend/db/init.sql`
- AI DB 테이블 정의: `ai/supplement_recognition/db/init.sql`

컨테이너 상태 확인:

```powershell
docker ps
```

아래 두 컨테이너가 `Up` 상태여야 합니다:

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

### 2단계 — Backend DB 데이터 적재 (5개 테이블)

```powershell
cd click/backend
python scripts/import_v3_data.py --csv-dir "C:\경로\drug-supplement schema v3"
```

> `C:\경로`를 `drug-supplement schema v3/` 폴더의 실제 경로로 바꿔서 실행하세요.

적재 순서 (FK 의존성 순):
1. `canonical_drug_entities` — 178행
2. `supplement_entities` — 33행
3. `source_claims` — 138행
4. `drug_aliases` — 378행
5. `standardized_interactions` — 475행

정상 완료 시 출력:

```
canonical_drug_entities import 중...
  178행 처리
supplement_entities import 중...
  33행 처리
source_claims import 중...
  138행 처리
drug_aliases import 중...
  378행 처리
standardized_interactions import 중...
  475행 처리
완료
```

---

### 3단계 — AI DB 데이터 적재 (4개 테이블)

AI DB는 두 단계로 나뉩니다. **supplement_info를 먼저 적재해야** 이후 `supplement_product_markers`의 FK 오류가 발생하지 않습니다.

#### 3-1. supplement_info 적재 (44,885행)

전용 스크립트가 없으므로 아래 명령어로 직접 적재합니다:

```powershell
cd click/ai
python -c "
import csv, os, mysql.connector
from dotenv import load_dotenv
from pathlib import Path

load_dotenv('.env')
conn = mysql.connector.connect(
    host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
    port=int(os.environ.get('MYSQL_PORT', 3306)),
    user=os.environ['MYSQL_USER'],
    password=os.environ['MYSQL_PASSWORD'],
    database=os.environ['MYSQL_DATABASE'],
)
cursor = conn.cursor()

csv_path = Path(r'C:\경로\drug-supplement schema v3\supplement_info.csv')
with open(csv_path, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

sql = '''INSERT INTO supplement_info
    (sttemnt_no, prduct, entrps, regist_dt, distb_pd, sungsang,
     srv_use, prsrv_pd, intake_hint1, main_fnctn, base_standard)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE prduct=VALUES(prduct), entrps=VALUES(entrps)'''

batch = 2000
data = [(r.get('sttemnt_no',''), r.get('prduct',''), r.get('entrps',''),
         r.get('regist_dt',''), r.get('distb_pd',''), r.get('sungsang',''),
         r.get('srv_use',''), r.get('prsrv_pd',''), r.get('intake_hint1',''),
         r.get('main_fnctn',''), r.get('base_standard','')) for r in rows]

for i in range(0, len(data), batch):
    cursor.executemany(sql, data[i:i+batch])

conn.commit()
print(f'supplement_info {len(data)}행 적재 완료')
cursor.close(); conn.close()
"
```

> `C:\경로`를 실제 경로로 바꿔서 실행하세요.

#### 3-2. pill_products / pill_product_ingredients / supplement_product_markers 적재

```powershell
cd click/ai
python scripts/import_v3_pill_data.py --csv-dir "C:\경로\drug-supplement schema v3"
```

적재 순서 (FK 의존성 순):
1. `pill_products` — 4,525행
2. `pill_product_ingredients` — 892행
3. `supplement_product_markers` — 69,845행 (supplement_info FK 참조)

정상 완료 시 출력:

```
pill_products import 중...
  4525행 처리
pill_product_ingredients import 중...
  892행 처리
supplement_product_markers 교체 중...
  69845행 처리
완료
```

---

## 데이터 확인

### Backend DB 접속 및 확인

```powershell
docker exec -it click_backend_db mysql -u click_user -p click_backend_db
```

비밀번호 입력 후:

```sql
-- 테이블 목록
SHOW TABLES;

-- 행 수 확인
SELECT 'canonical_drug_entities'  AS tbl, COUNT(*) AS cnt FROM canonical_drug_entities
UNION ALL SELECT 'drug_aliases',                     COUNT(*) FROM drug_aliases
UNION ALL SELECT 'supplement_entities',              COUNT(*) FROM supplement_entities
UNION ALL SELECT 'source_claims',                    COUNT(*) FROM source_claims
UNION ALL SELECT 'standardized_interactions',        COUNT(*) FROM standardized_interactions;
```

정상 결과:

| tbl | cnt |
|---|---:|
| canonical_drug_entities | 178 |
| drug_aliases | 378 |
| supplement_entities | 33 |
| source_claims | 138 |
| standardized_interactions | 475 |
| supplement_info | 44885 |
| supplement_product_markers | 70018 |

```sql
-- 상호작용 샘플 조회 (오메가-3 관련)
SELECT si.interaction_id, cde.canonical_drug_name_ko, se.supplement_name_ko
FROM standardized_interactions si
JOIN canonical_drug_entities cde ON cde.canonical_drug_id = si.canonical_drug_id
JOIN supplement_entities se ON se.supplement_id = si.supplement_id
WHERE se.supplement_name_ko LIKE '%오메가%'
LIMIT 5;

EXIT;
```

### AI DB 접속 및 확인

```powershell
docker exec -it click_supplement_db mysql -u click_user -p click_db
```

비밀번호 입력 후:

```sql
-- 테이블 목록
SHOW TABLES;

-- 행 수 확인
SELECT 'supplement_info'           AS tbl, COUNT(*) AS cnt FROM supplement_info
UNION ALL SELECT 'supplement_product_markers', COUNT(*) FROM supplement_product_markers
UNION ALL SELECT 'pill_products',              COUNT(*) FROM pill_products
UNION ALL SELECT 'pill_product_ingredients',   COUNT(*) FROM pill_product_ingredients;
```

정상 결과:

| tbl | cnt |
|---|---:|
| supplement_info | 44,885 |
| supplement_product_markers | 69,845 |
| pill_products | 4,525 |
| pill_product_ingredients | 892 |

```sql
-- pill_products → canonical_drug_id 연결 확인
SELECT pp.product_name, ppi.canonical_drug_id
FROM pill_products pp
JOIN pill_product_ingredients ppi ON ppi.pill_product_id = pp.pill_product_id
LIMIT 5;

-- supplement 브랜드 → supplement_id 연결 확인
SELECT si.prduct, spm.supplement_id
FROM supplement_info si
JOIN supplement_product_markers spm ON spm.supplement_info_id = si.id
WHERE si.prduct LIKE '%오메가3%'
LIMIT 5;

EXIT;
```

### phpMyAdmin으로 확인 (Backend DB 전용)

`backend/docker-compose.yml`에 phpMyAdmin이 포함되어 있습니다.

```
http://localhost:18089
```

- 서버: `db`
- 사용자: `.env`의 `MYSQL_USER`
- 비밀번호: `.env`의 `MYSQL_PASSWORD`

---

## 자주 겪는 문제

### 컨테이너 이름이 다를 때

`docker ps`로 실제 컨테이너 이름 확인 후 명령어 수정:

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

### supplement_product_markers 적재 시 FK 오류

`supplement_info`가 먼저 적재되지 않으면 발생합니다. **3-1 단계를 먼저 실행했는지 확인**하세요.

### DB 연결 안 될 때 (`2003: Can't connect`)

로컬에서 스크립트 직접 실행 시 `.env`의 `MYSQL_HOST`가 반드시 `127.0.0.1`이어야 합니다.

```
MYSQL_HOST=127.0.0.1   # 로컬 스크립트 실행 시
MYSQL_HOST=db          # Docker 컨테이너 내부(api 서비스) 실행 시
```

### DB를 완전히 초기화하고 싶을 때

```powershell
# Backend DB 초기화
cd click/backend
docker compose down -v
docker compose up -d db

# AI DB 초기화
cd click/ai
docker compose down -v
docker compose up -d db
```

초기화 후 **2단계 → 3단계 순서로 다시 적재**해야 합니다.

### 테이블은 있는데 데이터가 비어 있을 때

적재 스크립트를 실행하지 않았거나 `--csv-dir` 경로가 잘못된 경우입니다. 경로에 공백이 있으면 큰따옴표로 감싸야 합니다.

```powershell
python scripts/import_v3_data.py --csv-dir "C:\Users\이름\Documents\drug-supplement schema v3"
```
