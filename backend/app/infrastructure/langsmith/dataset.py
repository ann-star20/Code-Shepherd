"""피드백 환류 → extractor_schema_eval LangSmith 데이터셋 추가. PRD §23."""
from __future__ import annotations

import os
from typing import Optional


def add_to_eval_dataset(
    input_text: str,
    corrected_output: dict,
    dataset_name: str = "extractor_schema_eval",
    app_mode: str | None = None,
) -> Optional[str]:
    """HITL 수정 사례를 LangSmith 평가 데이터셋에 추가한다.

    PROD: 데이터셋 조회(없으면 생성) → create_example 호출.
    DEV: no-op — None 반환.

    Returns: example ID str (PROD) or None (DEV/오류).
    """
    mode = app_mode or os.getenv("APP_MODE", "development")
    if mode != "production":
        return None

    try:
        from langsmith import Client

        client = Client()
        try:
            dataset = client.read_dataset(dataset_name=dataset_name)
        except Exception:
            dataset = client.create_dataset(dataset_name=dataset_name)

        example = client.create_example(
            inputs={"text": input_text},
            outputs=corrected_output,
            dataset_id=dataset.id,
        )
        return str(example.id)
    except Exception:
        return None
