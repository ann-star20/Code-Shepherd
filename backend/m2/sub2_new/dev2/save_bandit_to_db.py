import json
import os
from pathlib import Path

os.environ["PGCLIENTENCODING"] = "UTF8"
os.environ["LC_MESSAGES"] = "C"

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv


load_dotenv()


BANDIT_RESULT_PATH = Path("bandit_result.json")


def get_db_connection():
    """
    .env의 DATABASE_URL은 asyncpg 형식이라 psycopg2에서 바로 못 쓴다.
    그래서 POSTGRES_* 값을 사용해서 접속한다.
    """
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "dev2_db"),
        user=os.getenv("POSTGRES_USER", "dev2"),
        password=os.getenv("POSTGRES_PASSWORD", "dev2"),
    )


def map_bandit_severity(bandit_severity: str) -> str:
    """
    Bandit severity를 우리 DB 기준으로 변환한다.
    HIGH   -> Critical
    MEDIUM -> Major
    LOW    -> Minor
    """
    severity = (bandit_severity or "").upper()

    if severity == "HIGH":
        return "Critical"
    if severity == "MEDIUM":
        return "Major"
    return "Minor"


def load_bandit_result():
    if not BANDIT_RESULT_PATH.exists():
        raise FileNotFoundError("bandit_result.json 파일이 없습니다.")

    with BANDIT_RESULT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def insert_scan_execution(cursor):
    """
    scan_executions에 먼저 실행 기록을 넣고,
    생성된 id를 반환한다.
    """
    cursor.execute(
        """
        INSERT INTO scan_executions (
            task_id,
            trace_id,
            pr_id,
            developer_id,
            execution_ms
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            "mock-security-scan-task",
            "local-trace-001",
            "local-pr-001",
            "dev2",
            None,
        ),
    )

    scan_id = cursor.fetchone()[0]
    return scan_id


def insert_scan_issues(cursor, scan_id, results):
    """
    Bandit results 배열을 scan_issues에 저장한다.
    """
    issue_count = 0

    for item in results:
        severity = map_bandit_severity(item.get("issue_severity"))
        rule_id = item.get("test_id", "UNKNOWN_RULE")
        file_path = item.get("filename")
        line_number = item.get("line_number")
        message = item.get("issue_text")
        test_name = item.get("test_name", "")
        more_info = item.get("more_info", "")

        suggestion = f"{test_name} / {more_info}".strip(" /")

        cursor.execute(
            """
            INSERT INTO scan_issues (
                scan_id,
                agent,
                severity,
                rule_id,
                file,
                line,
                message,
                suggestion,
                similar_issues,
                is_false_positive
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                scan_id,
                "bandit",
                severity,
                rule_id,
                file_path,
                line_number,
                message,
                suggestion,
                Json([]),
                False,
            ),
        )

        issue_count += 1

    return issue_count


def insert_scan_summary(cursor, scan_id, results):
    """
    scan_summaries에 Critical/Major/Minor 개수를 저장한다.
    """
    summary = {
        "Critical": 0,
        "Major": 0,
        "Minor": 0,
    }

    for item in results:
        severity = map_bandit_severity(item.get("issue_severity"))
        summary[severity] += 1

    cursor.execute(
        """
        INSERT INTO scan_summaries (
            scan_id,
            agent,
            critical,
            major,
            minor
        )
        VALUES (%s, %s, %s, %s, %s);
        """,
        (
            scan_id,
            "bandit",
            summary["Critical"],
            summary["Major"],
            summary["Minor"],
        ),
    )

    return summary


def main():
    bandit_data = load_bandit_result()
    results = bandit_data.get("results", [])

    print(f"[INFO] Bandit issue count: {len(results)}")

    conn = get_db_connection()

    try:
        with conn:
            with conn.cursor() as cursor:
                scan_id = insert_scan_execution(cursor)
                issue_count = insert_scan_issues(cursor, scan_id, results)
                summary = insert_scan_summary(cursor, scan_id, results)

        print("[SUCCESS] Bandit result saved to DB")
        print(f"scan_id: {scan_id}")
        print(f"inserted issues: {issue_count}")
        print(f"summary: {summary}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
