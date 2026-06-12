"""
dev2/dags/daily_etl.py
매일 새벽 2시: PostgreSQL scan_issues → BigQuery 적재
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

import asyncpg
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from google.cloud import bigquery


async def _fetch_yesterday() -> tuple[list[dict], str]:
    yesterday = (datetime.now() - timedelta(days=1)).date()
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    rows = await conn.fetch(
        """
        SELECT se.developer_id, se.pr_id, si.agent, si.severity,
               si.rule_id, si.file, si.message
        FROM scan_issues si
        JOIN scan_executions se ON si.scan_id = se.id
        WHERE se.scanned_at::date = $1
        """,
        yesterday,
    )
    await conn.close()
    return [dict(r) for r in rows], str(yesterday)


def extract(**ctx) -> None:
    rows, date = asyncio.run(_fetch_yesterday())
    ctx["ti"].xcom_push(key="rows", value=rows)
    ctx["ti"].xcom_push(key="date", value=date)


def load(**ctx) -> None:
    rows: list[dict] = ctx["ti"].xcom_pull(key="rows")
    date: str = ctx["ti"].xcom_pull(key="date")
    if not rows:
        return
    bq = bigquery.Client()
    table = f"{os.getenv('BIGQUERY_PROJECT_ID')}.dev2_dataset.scan_issues_daily"
    bq.insert_rows_json(table, [{**r, "scan_date": date} for r in rows])


with DAG(
    "dev2_daily_etl",
    schedule="0 2 * * *",
    start_date=datetime(2026, 5, 22),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
) as dag:
    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    load_task = PythonOperator(task_id="load", python_callable=load)
    extract_task >> load_task
