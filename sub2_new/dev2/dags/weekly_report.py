"""
dev2/dags/weekly_report.py
매주 월요일 오전 9시:
  t1. BigQuery 주간 인사이트 집계
  t2. 오탐률 20% 초과 rule → Slack 알림
  t3. Bandit/Semgrep 최신 버전 비교 → 구버전이면 Slack 알림
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime, timedelta

import asyncpg
import requests
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from google.cloud import bigquery


# ── Task 1: 주간 인사이트 집계 ────────────────────────────────────────────────

def generate_report(**ctx) -> None:
    bq = bigquery.Client()
    query = f"""
        SELECT developer_id, severity, COUNT(*) as count
        FROM `{os.getenv('BIGQUERY_PROJECT_ID')}.dev2_dataset.scan_issues_daily`
        WHERE scan_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        GROUP BY developer_id, severity
        ORDER BY count DESC
    """
    results = [dict(r) for r in bq.query(query).result()]
    print(f"주간 인사이트: {results}")


# ── Task 2: 오탐률 집계 + Slack 알림 ─────────────────────────────────────────

async def _fetch_false_positive_rates() -> list:
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    rows = await conn.fetch(
        """
        SELECT
            si.rule_id,
            COUNT(*) FILTER (WHERE si.is_false_positive = true) AS fp_count,
            COUNT(*)                                             AS total,
            ROUND(
                COUNT(*) FILTER (WHERE si.is_false_positive = true) * 100.0
                / NULLIF(COUNT(*), 0), 1
            ) AS fp_rate
        FROM scan_issues si
        JOIN scan_executions se ON se.id = si.scan_id
        WHERE se.scanned_at >= now() - interval '7 days'
        GROUP BY si.rule_id
        ORDER BY fp_rate DESC NULLS LAST
        """
    )
    await conn.close()
    return list(rows)


def aggregate_false_positive_rate(**ctx) -> None:
    rows = asyncio.run(_fetch_false_positive_rates())
    high_fp = [r for r in rows if r["fp_rate"] and r["fp_rate"] > 20]

    if not high_fp:
        return

    msg = "\n".join(
        f"- {r['rule_id']}: 오탐률 {r['fp_rate']}% ({r['fp_count']}/{r['total']}건)"
        for r in high_fp
    )
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        requests.post(
            slack_url,
            json={"text": f"오탐률 20% 초과 룰 발견\n{msg}"},
            timeout=5,
        )


# ── Task 3: 보안 룰셋 최신화 확인 ────────────────────────────────────────────

_TOOLS = {
    "bandit":  {"cmd": ["bandit", "--version"], "github": "PyCQA/bandit"},
    "semgrep": {"cmd": ["semgrep", "--version"], "github": "semgrep/semgrep"},
}


def check_ruleset_versions(**ctx) -> None:
    outdated: list[str] = []

    for name, cfg in _TOOLS.items():
        try:
            result = subprocess.run(
                cfg["cmd"], capture_output=True, text=True, timeout=10
            )
            current = result.stdout.strip().split()[-1]
            resp = requests.get(
                f"https://api.github.com/repos/{cfg['github']}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=10,
            )
            latest = resp.json()["tag_name"].lstrip("v")
            if current != latest:
                outdated.append(f"{name}: 현재 {current} → 최신 {latest}")
        except Exception as e:
            print(f"{name} 버전 체크 실패: {e}")

    if not outdated:
        return

    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        requests.post(
            slack_url,
            json={"text": "보안 룰셋 업데이트 필요\n" + "\n".join(outdated)},
            timeout=5,
        )


# ── DAG 정의 ──────────────────────────────────────────────────────────────────

with DAG(
    "dev2_weekly_report",
    schedule="0 9 * * MON",
    start_date=datetime(2026, 5, 22),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
) as dag:
    t1 = PythonOperator(task_id="generate_weekly_insights", python_callable=generate_report)
    t2 = PythonOperator(task_id="aggregate_false_positive", python_callable=aggregate_false_positive_rate)
    t3 = PythonOperator(task_id="check_ruleset_versions",   python_callable=check_ruleset_versions)

    t1 >> t2 >> t3
