"""
run_mixed.py — mixed_case_01~06 순차 개별 실행

사용법:
    cd sub2_new
    python run_mixed.py
    python run_mixed.py > result_mixed.txt 2>&1
"""
import asyncio
import pathlib
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / "dev2" / ".env")

from run_case import main as run_case_main

CASES_ROOT = (
    pathlib.Path(__file__).parent.parent
    / "pj3_data/datasets/JH_PJ3/m2_mixed_case"
)


async def main() -> None:
    for i in range(1, 7):
        case_name = f"mixed_case_0{i}"
        case_dir = CASES_ROOT / case_name
        print(f"\n{'=' * 60}")
        print(f"[ {i}/6 ]  {case_name}")
        print("=" * 60)
        await run_case_main(case_dir)


if __name__ == "__main__":
    asyncio.run(main())
