"""
Task 7: Airflow DAG 단위 테스트 (TDD — Red 단계)
실제 Airflow/DB/BigQuery 없이 Mock으로 테스트한다.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, timedelta


# ──────────────────────────────────────────────
# daily_etl.py 테스트
# ──────────────────────────────────────────────

class TestDailyEtlExtract:
    """extract Task: PostgreSQL에서 어제 데이터를 가져와 XCom에 push"""

    @patch("dev2.dags.daily_etl.asyncpg.connect")
    def test_extract_pushes_rows_to_xcom(self, mock_connect):
        """어제 날짜 데이터가 있으면 xcom_push(rows)가 호출된다"""
        from dev2.dags.daily_etl import extract

        # Mock DB 연결 + 쿼리 결과
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"developer_id": "dev-001", "pr_id": "1", "agent": "static_analysis",
             "severity": "Major", "rule_id": "PERF-001", "file": "auth.py", "message": "N+1 쿼리"},
        ]
        mock_connect.return_value = mock_conn

        # Mock XCom
        mock_ti = MagicMock()
        extract(ti=mock_ti)

        mock_ti.xcom_push.assert_any_call(key="rows", value=[
            {"developer_id": "dev-001", "pr_id": "1", "agent": "static_analysis",
             "severity": "Major", "rule_id": "PERF-001", "file": "auth.py", "message": "N+1 쿼리"},
        ])
        mock_ti.xcom_push.assert_any_call(key="date", value=str((datetime.now() - timedelta(days=1)).date()))

    @patch("dev2.dags.daily_etl.asyncpg.connect")
    def test_extract_pushes_empty_rows_when_no_data(self, mock_connect):
        """어제 데이터가 없으면 빈 리스트를 push한다 (예외 없이)"""
        from dev2.dags.daily_etl import extract

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_connect.return_value = mock_conn

        mock_ti = MagicMock()
        extract(ti=mock_ti)

        mock_ti.xcom_push.assert_any_call(key="rows", value=[])


class TestDailyEtlLoad:
    """load Task: XCom에서 rows를 꺼내 BigQuery에 적재"""

    @patch("dev2.dags.daily_etl.bigquery.Client")
    def test_load_inserts_rows_to_bigquery(self, mock_bq_client):
        """rows가 있으면 BigQuery insert_rows_json이 호출된다"""
        from dev2.dags.daily_etl import load

        mock_ti = MagicMock()
        mock_ti.xcom_pull.side_effect = lambda key: (
            [{"developer_id": "dev-001", "severity": "Major"}] if key == "rows"
            else "2026-05-25"
        )

        mock_client = MagicMock()
        mock_bq_client.return_value = mock_client

        load(ti=mock_ti)

        mock_client.insert_rows_json.assert_called_once()

    @patch("dev2.dags.daily_etl.bigquery.Client")
    def test_load_skips_bigquery_when_rows_empty(self, mock_bq_client):
        """rows가 비어있으면 BigQuery insert를 호출하지 않는다"""
        from dev2.dags.daily_etl import load

        mock_ti = MagicMock()
        mock_ti.xcom_pull.side_effect = lambda key: [] if key == "rows" else "2026-05-25"

        mock_client = MagicMock()
        mock_bq_client.return_value = mock_client

        load(ti=mock_ti)

        mock_client.insert_rows_json.assert_not_called()


class TestDailyEtlDagStructure:
    """DAG 구조: task 의존성 확인"""

    def test_dag_has_extract_and_load_tasks(self):
        """DAG에 extract, load task가 존재한다"""
        from dev2.dags.daily_etl import dag

        task_ids = [t.task_id for t in dag.tasks]
        assert "extract" in task_ids
        assert "load" in task_ids

    def test_dag_task_order_extract_before_load(self):
        """extract가 load보다 먼저 실행된다"""
        from dev2.dags.daily_etl import dag

        extract_task = dag.get_task("extract")
        load_task = dag.get_task("load")

        assert load_task in extract_task.downstream_list


# ──────────────────────────────────────────────
# weekly_report.py 테스트
# ──────────────────────────────────────────────

class TestWeeklyReportGenerateReport:
    """generate_report Task: BigQuery에서 주간 인사이트 집계"""

    @patch("dev2.dags.weekly_report.bigquery.Client")
    def test_generate_report_queries_bigquery(self, mock_bq_client):
        """BigQuery 쿼리가 실행된다"""
        from dev2.dags.weekly_report import generate_report

        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = [
            {"developer_id": "dev-001", "severity": "Major", "count": 3},
        ]
        mock_bq_client.return_value = mock_client

        generate_report(ti=MagicMock())

        mock_client.query.assert_called_once()


class TestWeeklyReportFalsePositive:
    """aggregate_false_positive_rate Task: 오탐률 20% 초과 시 Slack 알림"""

    @patch("dev2.dags.weekly_report.requests.post")
    @patch("dev2.dags.weekly_report.asyncpg.connect")
    def test_slack_alert_sent_when_fp_rate_exceeds_20(self, mock_connect, mock_post):
        """오탐률이 20% 초과인 rule이 있으면 Slack 알림이 전송된다"""
        from dev2.dags.weekly_report import aggregate_false_positive_rate
        import os
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            MagicMock(**{"__getitem__": lambda s, k: {"rule_id": "SEC-001", "fp_rate": 25.0,
                                                       "fp_count": 5, "total": 20}[k]})
        ]
        mock_connect.return_value = mock_conn

        aggregate_false_positive_rate(ti=MagicMock())

        mock_post.assert_called_once()

    @patch("dev2.dags.weekly_report.requests.post")
    @patch("dev2.dags.weekly_report.asyncpg.connect")
    def test_no_slack_alert_when_fp_rate_below_20(self, mock_connect, mock_post):
        """오탐률이 20% 이하면 Slack 알림을 보내지 않는다"""
        from dev2.dags.weekly_report import aggregate_false_positive_rate

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            MagicMock(**{"__getitem__": lambda s, k: {"rule_id": "SEC-001", "fp_rate": 10.0,
                                                       "fp_count": 1, "total": 10}[k]})
        ]
        mock_connect.return_value = mock_conn

        aggregate_false_positive_rate(ti=MagicMock())

        mock_post.assert_not_called()


class TestWeeklyReportRulesetCheck:
    """check_ruleset_versions Task: 구버전 툴 감지 시 Slack 알림"""

    @patch("dev2.dags.weekly_report.requests.post")
    @patch("dev2.dags.weekly_report.requests.get")
    @patch("dev2.dags.weekly_report.subprocess.run")
    def test_slack_alert_sent_when_tool_outdated(self, mock_run, mock_get, mock_post):
        """설치된 버전이 최신 버전과 다르면 Slack 알림이 전송된다"""
        from dev2.dags.weekly_report import check_ruleset_versions
        import os
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"

        mock_run.return_value = MagicMock(stdout="bandit 1.7.0", returncode=0)
        mock_get.return_value = MagicMock(json=lambda: {"tag_name": "v1.7.8"})

        check_ruleset_versions(ti=MagicMock())

        mock_post.assert_called_once()

    @patch("dev2.dags.weekly_report.requests.post")
    @patch("dev2.dags.weekly_report.requests.get")
    @patch("dev2.dags.weekly_report.subprocess.run")
    def test_no_slack_alert_when_tool_up_to_date(self, mock_run, mock_get, mock_post):
        """설치된 버전이 최신이면 Slack 알림을 보내지 않는다"""
        from dev2.dags.weekly_report import check_ruleset_versions

        mock_run.return_value = MagicMock(stdout="bandit 1.7.8", returncode=0)
        mock_get.return_value = MagicMock(json=lambda: {"tag_name": "v1.7.8"})

        check_ruleset_versions(ti=MagicMock())

        mock_post.assert_not_called()


class TestWeeklyReportDagStructure:
    """DAG 구조: task 의존성 확인"""

    def test_dag_has_three_tasks(self):
        """DAG에 3개 task가 존재한다"""
        from dev2.dags.weekly_report import dag

        task_ids = [t.task_id for t in dag.tasks]
        assert "generate_weekly_insights" in task_ids
        assert "aggregate_false_positive" in task_ids
        assert "check_ruleset_versions" in task_ids

    def test_dag_task_order(self):
        """t1 → t2 → t3 순서로 실행된다"""
        from dev2.dags.weekly_report import dag

        t1 = dag.get_task("generate_weekly_insights")
        t2 = dag.get_task("aggregate_false_positive")
        t3 = dag.get_task("check_ruleset_versions")

        assert t2 in t1.downstream_list
        assert t3 in t2.downstream_list


class TestWeeklyReportRulesetCheckException:
    """check_ruleset_versions: subprocess 예외 발생 시 로그 출력 후 계속 진행"""

    @patch("dev2.dags.weekly_report.requests.post")
    @patch("dev2.dags.weekly_report.requests.get")
    @patch("dev2.dags.weekly_report.subprocess.run")
    def test_no_slack_alert_when_subprocess_raises(self, mock_run, mock_get, mock_post):
        """subprocess 실행 실패 시 예외 삼키고 Slack 알림 없음."""
        from dev2.dags.weekly_report import check_ruleset_versions

        mock_run.side_effect = Exception("bandit not found")

        check_ruleset_versions(ti=MagicMock())

        mock_post.assert_not_called()
