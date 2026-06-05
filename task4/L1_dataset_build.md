---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md  
  - docs/PRD-domain.md
---
## L1: Pre-Eval 데이터셋 구축

### SDD

**목표**: LangSmith 데이터셋에 골든 입력/출력 쌍을 등록하여 프롬프트 품질 검증의 기준을 마련한다.

**디렉토리 구조**:
```
langsmith_datasets/
  extractor_schema_eval/
    golden_inputs/
      en_django_security.txt      # Django 보안 공식 문서 청크 (영문)
      en_spring_security.txt      # Spring Security 문서 청크 (영문)
      en_owasp_xss.txt            # OWASP XSS 가이드 청크 (영문)
      ko_django_security.txt      # Django 보안 한국어 문서
      ko_nplus1_orm.txt           # N+1 쿼리 한국어 문서
      # 영문 15개 + 한국어 5개 = 총 20개
    expected_outputs/
      en_django_security.json     # 기대 ConceptExtractionSchema JSON
      en_spring_security.json
      # 위 입력과 1:1 대응
  translation_eval/
    en_ko_pairs/
      pair_01.json   # {"en": "...", "ko": "...", "concept": "XSS"}
      # 번역 정합성 평가용 10쌍
```

**골든 출력 스키마 규칙**:
```python
# expected_outputs/*.json 형식
{
  "concept_name": "XSS",
  "concept_domain": "security",        # 필수: security|performance|both
  "concept_type": "vulnerability_root_cause",
  "cwe_id": "CWE-79",
  "severity": "HIGH",
  "description_ko": "크로스 사이트 스크립팅...",  # 반드시 한국어
  "aliases": ["Cross-Site Scripting"],
  "security_mechanisms": ["OutputEncoding", "CSP"],
  "affected_components": ["템플릿 렌더링"],
  "config_properties": [],
  "root_cause": "사용자 입력 이스케이프 미처리"
}
```

**LangSmith 데이터셋 업로드 스크립트**: `scripts/upload_eval_dataset.py`
```python
from langsmith import Client
import json
from pathlib import Path

def upload_dataset(dataset_name: str = "extractor_schema_eval_v1"):
    client = Client()
    dataset = client.create_dataset(dataset_name)

    inputs_dir  = Path("langsmith_datasets/extractor_schema_eval/golden_inputs")
    outputs_dir = Path("langsmith_datasets/extractor_schema_eval/expected_outputs")

    for input_file in sorted(inputs_dir.glob("*.txt")):
        output_file = outputs_dir / (input_file.stem + ".json")
        if not output_file.exists():
            continue
        client.create_example(
            inputs={"text_chunk": input_file.read_text(encoding="utf-8")},
            outputs={"concepts": [json.loads(output_file.read_text())]},
            dataset_id=dataset.id,
        )
    print(f"업로드 완료: {dataset_name}")
```

### TDD (AAA)

파일: `backend/tests/harness/test_eval_dataset.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L1_golden_files_exist | `langsmith_datasets/` 디렉토리 | `Path(...).exists()` | golden_inputs 20개, expected_outputs 20개 |
| T_L1_expected_schema_valid | `expected_outputs/en_django_security.json` 로드 | `ConceptExtractionSchema(**data)` | ValidationError 없이 파싱 성공 |
| T_L1_domain_coverage | 모든 expected_outputs 파싱 | `{e.concept_domain for e in examples}` | `"security"`, `"performance"`, `"both"` 모두 포함 |
| T_L1_ko_description | 모든 expected_outputs | `all(e.description_ko for e in examples)` | `True` (한국어 설명 누락 없음) |
| T_L1_upload_script | mock LangSmith Client | `upload_dataset()` 호출 | `create_example` 호출 횟수 == 파일 쌍 수 |

```python
# T_L1_expected_schema_valid AAA 예시
def test_expected_output_schema_valid():
    # Arrange
    output_file = Path("langsmith_datasets/extractor_schema_eval/expected_outputs/en_django_security.json")

    # Act
    data = json.loads(output_file.read_text())
    schema = ConceptExtractionSchema(**data)

    # Assert
    assert schema.concept_domain in {"security", "performance", "both"}
    assert len(schema.description_ko) > 0
    assert schema.concept_name != ""
```

### COMMIT
```
docs(extractor): add langsmith_datasets golden input output files 20 pairs
test(extractor): add L1 dataset file existence and schema validation tests
feat(extractor): add upload_eval_dataset.py langsmith dataset upload script
```