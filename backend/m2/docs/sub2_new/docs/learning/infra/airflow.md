# Apache Airflow DAG 학습 노트

**날짜**: 2026-05-22
**복습 예정**: D+1, D+3, D+7

---

## 한 줄 요약
"매일 새벽 2시에 이 작업 순서대로 실행해줘"를 코드로 정의하는 도구.

---

## 1. 비유
알람 + 할 일 목록에 비유:
- **알람(schedule)**: 매일 새벽 2시에 울림
- **할 일 목록(DAG)**: 알람 울리면 이 순서대로 실행
  1. PostgreSQL에서 어제 데이터 꺼내기
  2. BigQuery에 올리기
  3. 완료 알림

Airflow = 이 알람과 할 일 목록을 관리하는 시스템.

---

## 2. 개념
> **DAG (Directed Acyclic Graph)**: 방향이 있고 순환이 없는 그래프.
> 쉽게 말해 **"순서가 있는 작업 흐름"**을 코드로 표현한 것.

**핵심 용어:**

| 용어 | 설명 | 예시 |
|------|------|------|
| DAG | 작업 흐름 전체 | `dev2_daily_etl` |
| Task | DAG 안의 개별 작업 | `extract`, `load` |
| schedule_interval | 실행 주기 | `"0 2 * * *"` = 매일 새벽 2시 |
| `>>` 연산자 | 작업 순서 정의 | `extract >> load` |

**cron 표현식 읽는 법:**
```
"0 2 * * *"
 │ │ │ │ └── 요일 (모든 요일)
 │ │ │ └──── 월 (모든 달)
 │ │ └────── 일 (모든 날)
 │ └──────── 시 (2시)
 └────────── 분 (0분)
= 매일 새벽 2시 0분에 실행
```

---

## 3. 왜 쓰나
- **없으면**: PostgreSQL → BigQuery ETL을 수동으로 실행하거나, 서버에 cron 직접 설정
- **있으면**: 코드로 스케줄 관리, 실패 시 자동 재시도, UI에서 실행 현황 확인

---

## 4. 코드 (Dev 2)

```python
# dags/daily_etl.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

# Task 함수 정의
def extract(**context):
    # PostgreSQL에서 어제 데이터 읽기
    rows = fetch_yesterday_scans()
    context["ti"].xcom_push(key="rows", value=rows)  # 다음 Task에 데이터 전달

def load(**context):
    # 이전 Task에서 데이터 받기
    rows = context["ti"].xcom_pull(key="rows")
    # BigQuery에 적재
    load_to_bigquery(rows)

# DAG 정의
with DAG(
    "dev2_daily_etl",
    schedule_interval="0 2 * * *",      # 매일 새벽 2시
    start_date=datetime(2026, 5, 22),
    catchup=False,                        # 과거 실행 안 함
    default_args={
        "retries": 1,                     # 실패 시 1회 재시도
        "retry_delay": timedelta(minutes=5)
    },
) as dag:

    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    load_task = PythonOperator(task_id="load", python_callable=load)

    extract_task >> load_task  # extract 끝나면 load 실행
```

**XCom**: Task 간 데이터 전달 방법
```python
# Task A: 데이터 저장
context["ti"].xcom_push(key="rows", value=rows)

# Task B: 데이터 받기
rows = context["ti"].xcom_pull(key="rows")
```

---

## 복습 퀴즈

1. Q: DAG에서 `>>` 연산자의 역할은?
   A: (Task 실행 순서 정의. `A >> B` = A 끝나면 B 실행)

2. Q: `"0 2 * * *"` cron 표현식의 의미는?
   A: (매일 새벽 2시 0분에 실행)

3. Q: Dev 2에서 Airflow를 쓰는 이유는?
   A: (매일 PostgreSQL → BigQuery ETL 자동화 + 주간 인사이트 리포트 자동 생성)
