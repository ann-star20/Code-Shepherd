import asyncio
import json
from pathlib import Path

import asyncpg


BANDIT_RESULT_PATH = Path("bandit_result.json")


def map_bandit_severity(bandit_severity: str) -> str:
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


async def get_db_connection():
    return await asyncpg.connect(
        host="127.0.0.1",
        port=5432,
        database="dev2_db",
        user="dev2",
        password="dev2",
    )


async def insert_scan_execution(conn):
    scan_id = await conn.fetchval(
        """
        INSERT INTO scan_executions (
            task_id,
            trace_id,
            pr_id,
            developer_id,
            execution_ms
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id;
        """,
        "mock-security-scan-task",
        "local-trace-001",
        "local-pr-001",
        "dev2",
        None,
    )

    return scan_id


async def insert_scan_issues(conn, scan_id, results):
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

        await conn.execute(
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
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10);
            """,
            scan_id,
            "bandit",
            severity,
            rule_id,
            file_path,
            line_number,
            message,
            suggestion,
            json.dumps([]),
            False,
        )

        issue_count += 1

    return issue_count


async def insert_scan_summary(conn, scan_id, results):
    summary = {
        "Critical": 0,
        "Major": 0,
        "Minor": 0,
    }

    for item in results:
        severity = map_bandit_severity(item.get("issue_severity"))
        summary[severity] += 1

    await conn.execute(
        """
        INSERT INTO scan_summaries (
            scan_id,
            agent,
            critical,
            major,
            minor
        )
        VALUES ($1, $2, $3, $4, $5);
        """,
        scan_id,
        "bandit",
        summary["Critical"],
        summary["Major"],
        summary["Minor"],
    )

    return summary


async def main():
    bandit_data = load_bandit_result()
    results = bandit_data.get("results", [])

    print(f"[INFO] Bandit issue count: {len(results)}")

    conn = await get_db_connection()

    try:
        async with conn.transaction():
            scan_id = await insert_scan_execution(conn)
            issue_count = await insert_scan_issues(conn, scan_id, results)
            summary = await insert_scan_summary(conn, scan_id, results)

        print("[SUCCESS] Bandit result saved to DB")
        print(f"scan_id: {scan_id}")
        print(f"inserted issues: {issue_count}")
        print(f"summary: {summary}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())