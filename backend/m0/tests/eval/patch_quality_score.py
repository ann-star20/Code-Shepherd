"""pipeline_output.json의 quality_score를 /kms/docs/{doc_id}/details에서 업데이트한다."""
import asyncio
import json
from pathlib import Path
import httpx

BASE_URL = "http://localhost:8002"
OUTPUT = Path(__file__).parent / "results" / "pipeline_output.json"


async def main():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    async with httpx.AsyncClient(timeout=30.0) as client:
        for entry in data:
            doc_id = entry.get("doc_id")
            if not doc_id:
                continue
            try:
                r = await client.get(f"{BASE_URL}/kms/docs/{doc_id}/details")
                if r.status_code == 200:
                    entry["quality_score"] = float(r.json().get("quality_score") or 0.0)
                    print(f"{entry['golden_id']} quality_score={entry['quality_score']:.2f}")
            except Exception as e:
                print(f"{entry['golden_id']} error: {e}")
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done.")


asyncio.run(main())
