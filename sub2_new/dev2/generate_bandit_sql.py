import json
from pathlib import Path


BANDIT_RESULT_PATH = Path("bandit_result.json")
OUTPUT_SQL_PATH = Path("insert_bandit_result.sql")


def sql_quote(value):
    if value is None:
        return "NULL"

    text = str(value)
    text = text.replace("'", "''")
    return f"'{text}'"


def map_bandit_severity(bandit_severity):
    severity = (bandit_severity or "").upper()

    if severity == "HIGH":
        return "Critical"
    if severity == "MEDIUM":
        return "Major"
    return "Minor"


def main():
    if not BANDIT_RESULT_PATH.exists():
        raise FileNotFoundError("bandit_result.json 파일이 없습니다.")

    with BANDIT_RESULT_PATH.open("r", encoding="utf-8") as f:
        bandit_data = json.load(f)

    results = bandit_data.get("results", [])

    summary = {
        "Critical": 0,
        "Major": 0,
        "Minor": 0,
    }

    issue_values = []

    for item in results:
        severity = map_bandit_severity(item.get("issue_severity"))
        summary[severity] += 1

        rule_id = item.get("test_id", "UNKNOWN_RULE")
        file_path = item.get("filename")
        line_number = item.get("line_number")
        message = item.get("issue_text")
        test_name = item.get("test_name", "")
        more_info = item.get("more_info", "")

        suggestion = f"{test_name} / {more_info}".strip(" /")

        line_sql = "NULL" if line_number is None else str(line_number)

        issue_values.append(
            f"""(
    :scan_id,
    'bandit',
    {sql_quote(severity)},
    {sql_quote(rule_id)},
    {sql_quote(file_path)},
    {line_sql},
    {sql_quote(message)},
    {sql_quote(suggestion)},
    '[]'::jsonb,
    false
)"""
        )

    if issue_values:
        issues_insert_sql = f"""
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
VALUES
{",\n".join(issue_values)};
"""
    else:
        issues_insert_sql = "-- No Bandit issues found.\n"

    sql = f"""
BEGIN;

INSERT INTO scan_executions (
    task_id,
    trace_id,
    pr_id,
    developer_id,
    execution_ms
)
VALUES (
    'mock-security-scan-task',
    'local-trace-001',
    'local-pr-001',
    'dev2',
    NULL
)
RETURNING id AS scan_id \\gset

{issues_insert_sql}

INSERT INTO scan_summaries (
    scan_id,
    agent,
    critical,
    major,
    minor
)
VALUES (
    :scan_id,
    'bandit',
    {summary["Critical"]},
    {summary["Major"]},
    {summary["Minor"]}
);

COMMIT;

SELECT :scan_id AS saved_scan_id;
"""

    OUTPUT_SQL_PATH.write_text(sql, encoding="utf-8")

    print("[SUCCESS] SQL file generated")
    print(f"issue count: {len(results)}")
    print(f"summary: {summary}")
    print(f"output: {OUTPUT_SQL_PATH}")


if __name__ == "__main__":
    main()