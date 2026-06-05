---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md
  - docs/PRD-domain.md
---
## L6: 모니터링 알림 설정 — Slack + HITL 수정률 트리거

### SDD

**목표**: 프로덕션 운영 중 스키마 이탈 또는 HITL 수정률 급등을 감지하여 자동 알림을 발송한다.

**파일**: `backend/app/infrastructure/monitoring/alert_service.py`

```python
from dataclasses import dataclass
import httpx

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

@dataclass
class AlertPayload:
    level: str      # "warning" | "critical"
    message: str
    langsmith_run_url: str | None = None

async def send_slack_alert(payload: AlertPayload) -> bool:
    """Slack Incoming Webhook으로 알림 발송."""
    if not SLACK_WEBHOOK_URL:
        return False
    emoji = "🚨" if payload.level == "critical" else "⚠️"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"{emoji} *KG Pipeline Alert*\n{payload.message}"}},
    ]
    if payload.langsmith_run_url:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"🔍 <{payload.langsmith_run_url}|LangSmith Run 확인>"}})
    async with httpx.AsyncClient() as client:
        resp = await client.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})
        return resp.status_code == 200
```

**파일**: `backend/app/usecases/monitor_quality.py`

```python
from app.infrastructure.monitoring.alert_service import send_slack_alert, AlertPayload

SCHEMA_DRIFT_THRESHOLD  = 1    # 1건 이상 / 1시간
HITL_CORRECTION_RATE_THRESHOLD = 0.20  # 20% 이상

async def check_schema_drift(run_id: str, langsmith_run_url: str) -> None:
    """스키마 이탈 Run 감지 시 즉시 Slack 알림."""
    await send_slack_alert(AlertPayload(
        level="critical",
        message=f"스키마 이탈 Run 감지\nRun ID: {run_id}",
        langsmith_run_url=langsmith_run_url,
    ))

async def check_hitl_correction_rate(session_id: str, total: int, corrected: int) -> None:
    """HITL 수정률 계산 후 임계값 초과 시 알림 + Pre-Eval 재실행 트리거."""
    rate = corrected / total if total > 0 else 0.0
    if rate >= HITL_CORRECTION_RATE_THRESHOLD:
        await send_slack_alert(AlertPayload(
            level="warning",
            message=(
                f"HITL 수정률 {rate:.0%} — 임계값({HITL_CORRECTION_RATE_THRESHOLD:.0%}) 초과\n"
                f"세션: {session_id} ({corrected}/{total} 수정)\n"
                f"→ 프롬프트 재평가 트리거 권고"
            ),
        ))
        # Pre-Eval 재실행 트리거 (비동기 큐 적재)
        trigger_pre_eval_task.delay()
```

**`trigger_pre_eval_task`** (`infrastructure/queue/tasks/`):
```python
@celery_app.task(name="trigger_pre_eval")
def trigger_pre_eval_task():
    import subprocess
    subprocess.run(["python", "scripts/run_pre_eval.py", "--version", "auto"], check=True)
```

### TDD (AAA)

파일: `backend/tests/harness/test_monitoring.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L6_slack_sent | mock `httpx.AsyncClient.post` → 200 | `send_slack_alert(payload)` | `True` 반환, post 1회 호출 |
| T_L6_no_webhook | `SLACK_WEBHOOK_URL=""` | `send_slack_alert(payload)` | `False` 반환, post 0회 호출 |
| T_L6_slack_message | `level="critical"`, `message="테스트"` | `send_slack_alert(payload)` | post body에 "🚨" 포함 |
| T_L6_slack_run_url | `langsmith_run_url="https://smith.langchain.com/..."` | `send_slack_alert(payload)` | post body에 URL 포함 |
| T_L6_drift_alert | mock `send_slack_alert` | `check_schema_drift("run-id", url)` | `send_slack_alert` 1회, `level="critical"` |
| T_L6_hitl_below_threshold | `total=10, corrected=1` (10%) | `check_hitl_correction_rate(sid, 10, 1)` | `send_slack_alert` 0회 |
| T_L6_hitl_above_threshold | `total=10, corrected=3` (30%) | `check_hitl_correction_rate(sid, 10, 3)` | `send_slack_alert` 1회, `level="warning"` |
| T_L6_pre_eval_triggered | `total=10, corrected=3` | `check_hitl_correction_rate(...)` | `trigger_pre_eval_task.delay` 1회 호출 |

```python
# T_L6_hitl_above_threshold AAA 예시
@patch("app.usecases.monitor_quality.send_slack_alert")
@patch("app.usecases.monitor_quality.trigger_pre_eval_task")
async def test_hitl_rate_above_threshold_triggers_alert(mock_trigger, mock_alert):
    # Arrange
    session_id = "sid-001"
    total, corrected = 10, 3   # 30% > 20% 임계값

    # Act
    await check_hitl_correction_rate(session_id, total, corrected)

    # Assert
    mock_alert.assert_called_once()
    call_args = mock_alert.call_args[0][0]
    assert call_args.level == "warning"
    assert "30%" in call_args.message or "0.30" in call_args.message
    mock_trigger.delay.assert_called_once()
```

### COMMIT
```
test(extractor): add L6 Slack alert send HITL rate threshold pre-eval trigger tests
feat(extractor): implement alert_service.py Slack webhook and monitor_quality usecase
feat(extractor): add trigger_pre_eval_task Celery task for auto re-evaluation
chore(infra): add SLACK_WEBHOOK_URL to env.prod env.local docs
```