"""Phase 4 G15~G16 — LangSmith HITL 피드백 및 Dataset 환류 테스트.

T_ls_01: DEV 모드 → record_hitl_feedback no-op (None 반환)
T_ls_02: PROD 모드 → create_feedback 호출, 올바른 key/score 전달
T_ls_03: DEV 모드 → add_to_eval_dataset no-op (None 반환)
T_ls_04: PROD 모드 → create_example 호출, dataset_name 전달
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

BEFORE = {"concept_name": "XSS", "severity": "high", "description_ko": "원본"}
AFTER = {"concept_name": "XSS", "severity": "critical", "description_ko": "수정본"}


def _inject_mock_langsmith(client_instance: MagicMock) -> None:
    """langsmith 패키지를 sys.modules에 mock으로 주입한다."""
    mock_ls = ModuleType("langsmith")
    mock_ls.Client = MagicMock(return_value=client_instance)  # type: ignore[attr-defined]
    sys.modules["langsmith"] = mock_ls


def _remove_mock_langsmith() -> None:
    sys.modules.pop("langsmith", None)


# ── G15: record_hitl_feedback ─────────────────────────────────────────────────


def test_T_ls_01_dev_mode_noop():
    """Arrange: app_mode='development'.
    Act: record_hitl_feedback 호출.
    Assert: None 반환 (LangSmith 미호출).
    """
    from app.infrastructure.langsmith.feedback import record_hitl_feedback

    result = record_hitl_feedback("run-123", BEFORE, AFTER, app_mode="development")
    assert result is None


def test_T_ls_02_prod_mode_calls_create_feedback():
    """Arrange: app_mode='production', langsmith.Client mock 주입.
    Act: record_hitl_feedback 호출.
    Assert: create_feedback key='hitl_correction', score=0, comment에 diff_key 포함.
    """
    mock_feedback = MagicMock()
    mock_feedback.id = "fb-abc123"
    mock_client = MagicMock()
    mock_client.create_feedback.return_value = mock_feedback
    _inject_mock_langsmith(mock_client)

    try:
        import importlib

        from app.infrastructure.langsmith import feedback as fb_mod

        importlib.reload(fb_mod)
        result = fb_mod.record_hitl_feedback(
            "run-456", BEFORE, AFTER, app_mode="production"
        )
    finally:
        _remove_mock_langsmith()

    mock_client.create_feedback.assert_called_once()
    kwargs = mock_client.create_feedback.call_args.kwargs
    assert kwargs["key"] == "hitl_correction"
    assert kwargs["score"] == 0
    assert "severity" in kwargs["comment"]
    assert result == "fb-abc123"


# ── G16: add_to_eval_dataset ─────────────────────────────────────────────────


def test_T_ls_03_dev_mode_dataset_noop():
    """Arrange: app_mode='development'.
    Act: add_to_eval_dataset 호출.
    Assert: None 반환.
    """
    from app.infrastructure.langsmith.dataset import add_to_eval_dataset

    result = add_to_eval_dataset("dummy chunk", AFTER, app_mode="development")
    assert result is None


def test_T_ls_04_prod_mode_calls_create_example():
    """Arrange: app_mode='production', langsmith.Client mock 주입.
    Act: add_to_eval_dataset 호출.
    Assert: create_example inputs={'text':...}, outputs=AFTER.
    """
    mock_dataset = MagicMock()
    mock_dataset.id = "ds-001"
    mock_example = MagicMock()
    mock_example.id = "ex-xyz"
    mock_client = MagicMock()
    mock_client.read_dataset.return_value = mock_dataset
    mock_client.create_example.return_value = mock_example
    _inject_mock_langsmith(mock_client)

    try:
        import importlib

        from app.infrastructure.langsmith import dataset as ds_mod

        importlib.reload(ds_mod)
        result = ds_mod.add_to_eval_dataset(
            input_text="security chunk",
            corrected_output=AFTER,
            dataset_name="extractor_schema_eval",
            app_mode="production",
        )
    finally:
        _remove_mock_langsmith()

    mock_client.create_example.assert_called_once()
    kwargs = mock_client.create_example.call_args.kwargs
    assert kwargs["inputs"] == {"text": "security chunk"}
    assert kwargs["outputs"] == AFTER
    assert result == "ex-xyz"
