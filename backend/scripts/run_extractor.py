#!/usr/bin/env python3
"""URL → 크롤 → 프롬프트 빌드 → LLM 추출 파이프라인 단독 실행.

Celery/Docker 없이 직접 실행하여 프롬프트 구조 확인 및 mock 데이터셋 생성.

Usage:
  # mock 모드 (기본) — 크롤 + 프롬프트 빌드 + 고정 응답
  python scripts/run_extractor.py --url "https://docs.djangoproject.com/en/6.0/ref/csrf/"

  # 프롬프트 + 응답 파일 저장
  python scripts/run_extractor.py --url "..." --request-file prompt.txt --response-file response.json

  # 모든 출력을 파일로 (터미널 잘림 방지)
  python scripts/run_extractor.py --url "..." --dump-prompt --out-file full_output.txt

  # production 모드 — 실제 Gemini 호출 + 요청/응답 저장
  python scripts/run_extractor.py --url "..." --mode production --api-key AIza... \\
      --request-file req.txt --response-file res.json

  # 추출 결과를 mock 데이터셋으로 저장 (production 모드에서만 의미 있음)
  python scripts/run_extractor.py --url "..." --mode production --api-key AIza... --save-mock
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def _section(title: str) -> None:
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


async def run(args: argparse.Namespace) -> None:
    from app.infrastructure.crawler.http_crawler import fetch, smart_chunk
    from app.infrastructure.llm.gemini_client import _build_prompt, DEFAULT_DOMAINS

    # ── STEP 1: 크롤 ─────────────────────────────────────────────
    _section("STEP 1 — 크롤링")
    print(f"  URL: {args.url}")
    async with aiohttp.ClientSession() as http:
        result = await fetch(args.url, http)
    chunks = smart_chunk(result)
    print(f"  텍스트 길이: {len(result.content):,}자  →  {len(chunks)}개 청크")
    for i, c in enumerate(chunks):
        print(f"  청크[{i}]: {len(c):,}자  |  미리보기: {c[:80].replace(chr(10), ' ')!r}")

    # ── STEP 2: 메타 (Pre-scan 모의) ─────────────────────────────
    metadata: dict = {
        "framework": args.framework or "Unknown",
        "lang": args.lang,
        "allowed_domains": DEFAULT_DOMAINS,
    }

    # ── STEP 3: 프롬프트 빌드 ────────────────────────────────────
    _section("STEP 2 — 프롬프트 빌드")
    print(
        "  [구조 안내] Gemini는 단일 user turn으로 호출됩니다.\n"
        "  system message / user message 분리 없이 하나의 문자열로 전송.\n"
        "  구성: [역할·지시(system 역할)] + [스키마 명세] + [--- 문서 청크 ---]"
    )
    prompts: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = _build_prompt(chunk, metadata, DEFAULT_DOMAINS)
        prompts.append(prompt)
        print(f"\n  [청크 {i}] 프롬프트 길이: {len(prompt):,}자")
        if args.dump_prompt:
            print("─" * 60)
            print(prompt)
            print("─" * 60)
        else:
            preview = prompt[:200].replace("\n", " ")
            print(f"  미리보기: {preview!r}...")

    # ── STEP 3-a: --request-file 저장 ────────────────────────────
    if args.request_file:
        req_path = Path(args.request_file)
        req_path.parent.mkdir(parents=True, exist_ok=True)
        with req_path.open("w", encoding="utf-8") as f:
            f.write(f"# Request Prompt — {args.url}\n")
            f.write(f"# framework={metadata['framework']}  lang={metadata['lang']}\n")
            f.write(f"# chunks={len(prompts)}\n\n")
            f.write(
                "# [구조] Gemini 단일 user turn — system message/user message 분리 없음\n"
                "# 구성: 역할·지시 + 스키마 명세 + --- 문서 청크 ---\n\n"
            )
            for i, prompt in enumerate(prompts):
                f.write(f"{'='*60}\n")
                f.write(f"=== CHUNK {i}  (len={len(prompt):,}자) ===\n")
                f.write(f"{'='*60}\n\n")
                f.write(prompt)
                f.write("\n\n")
        print(f"\n  [저장] 요청 프롬프트 → {req_path.resolve()}")

    if args.dump_prompt:
        print("\n  --dump-prompt 모드 종료")
        return

    # ── STEP 4: LLM 추출 ─────────────────────────────────────────
    _section("STEP 3 — LLM 추출")
    all_concepts = []
    client = None

    if args.mode == "mock":
        from app.infrastructure.llm.mock_client import MockClient, _MOCK_CONCEPTS
        print(f"  MODE: mock — API 호출 없음, {len(_MOCK_CONCEPTS)}개 고정 데이터 반환")
        client = MockClient()
        # mock은 청크마다 같은 데이터를 반환하므로 첫 번째 청크만 처리
        concepts = await client.extract_concepts(chunks[0], "local-run", metadata)
        all_concepts = concepts
        print(f"  → {len(all_concepts)}개 컨셉 (mock 고정값, 청크 1개만 처리)")

    else:
        if not args.api_key:
            print("  ERROR: production 모드는 --api-key 필요", file=sys.stderr)
            sys.exit(1)
        from app.infrastructure.llm.gemini_client import GeminiClient
        client = GeminiClient(api_key=args.api_key, model=args.model)
        for i, chunk in enumerate(chunks):
            if i > 0:
                print(f"  [청크 {i}] 대기 4초 (무료 티어 rate limit)...")
                await asyncio.sleep(4)
            print(f"  [청크 {i}] Gemini 호출 중...")
            concepts = await client.extract_concepts(chunk, "local-run", metadata)
            print(f"  [청크 {i}] → {len(concepts)}개")
            all_concepts.extend(concepts)

    # ── STEP 5: 결과 출력 ─────────────────────────────────────────
    _section("STEP 4 — 추출 결과")
    for c in all_concepts:
        d = c.model_dump()
        print(
            f"  · {d.get('concept_name', '?'):<30s}"
            f"  type={d.get('concept_type', '?'):<30s}"
            f"  severity={d.get('severity', '?'):<8s}"
            f"  domains={d.get('domains', [])}"
        )

    # ── STEP 5-a: --response-file 저장 ───────────────────────────
    if args.response_file:
        resp_path = Path(args.response_file)
        resp_path.parent.mkdir(parents=True, exist_ok=True)

        # 파싱된 컨셉 JSON
        parsed_data = [c.model_dump() for c in all_concepts]
        resp_path.write_text(json.dumps(parsed_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  [저장] 응답(parsed JSON) → {resp_path.resolve()}")

        # production 모드: LLM 원문 응답도 별도 저장
        if args.mode == "production" and client is not None and hasattr(client, "raw_responses"):
            raw_path = resp_path.with_suffix(".raw.txt")
            with raw_path.open("w", encoding="utf-8") as f:
                for i, raw in enumerate(client.raw_responses):
                    f.write(f"{'='*60}\n=== CHUNK {i} RAW RESPONSE ===\n{'='*60}\n\n")
                    f.write(raw)
                    f.write("\n\n")
            print(f"  [저장] 응답(LLM 원문)  → {raw_path.resolve()}")
        elif args.mode == "mock":
            mock_note_path = resp_path.with_suffix(".raw.txt")
            mock_note_path.write_text(
                "# Mock 모드 — LLM 원문 응답 없음\n"
                "# mock_client.py의 _MOCK_CONCEPTS 고정값이 반환됩니다.\n",
                encoding="utf-8",
            )
            print(f"  [저장] 응답(mock 안내) → {mock_note_path.resolve()}")

    # ── STEP 6: mock 데이터셋 저장 ───────────────────────────────
    if args.save_mock:
        _section("STEP 5 — mock 데이터셋 저장")
        out_dir = Path(__file__).parent / "seed" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        slug = urlparse(args.url).path.strip("/").replace("/", "_") or "root"
        out_path = out_dir / f"mock_{slug}.json"

        data = [c.model_dump() for c in all_concepts]
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  저장 완료: {out_path}")
        print(f"  항목 수: {len(data)}개")
        print(f"\n  MockClient에서 사용하려면 mock_client.py의 _MOCK_CONCEPTS를:")
        print(f"    json.loads(Path('scripts/seed/generated/mock_{slug}.json').read_text())")
        print(f"  로 교체하세요.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="URL → 크롤 → 프롬프트 → LLM 추출 파이프라인 단독 실행"
    )
    parser.add_argument("--url", required=True, help="분석할 문서 URL")
    parser.add_argument("--mode", default="mock", choices=["mock", "production"])
    parser.add_argument("--api-key", default="", help="Gemini API 키 (production 모드)")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--framework", default="", help="프레임워크 힌트 (예: Django)")
    parser.add_argument("--lang", default="KO", help="문서 언어")
    parser.add_argument(
        "--dump-prompt",
        action="store_true",
        help="구성된 LLM 프롬프트 전체를 출력하고 종료 (--request-file 과 함께 사용 권장)",
    )
    parser.add_argument(
        "--out-file",
        metavar="PATH",
        default="",
        help="모든 출력을 파일로 저장 (터미널 잘림 방지)",
    )
    parser.add_argument(
        "--request-file",
        metavar="PATH",
        default="",
        help="LLM 요청 프롬프트 전체를 파일로 저장",
    )
    parser.add_argument(
        "--response-file",
        metavar="PATH",
        default="",
        help="LLM 응답(parsed JSON + raw .txt)을 파일로 저장",
    )
    parser.add_argument(
        "--save-mock",
        action="store_true",
        help="추출 결과를 scripts/seed/generated/ 에 mock JSON으로 저장",
    )
    args = parser.parse_args()

    # --out-file: stdout을 파일로 교체
    _out_fp = None
    if args.out_file:
        _out_fp = open(args.out_file, "w", encoding="utf-8")
        sys.stdout = _out_fp
        print(f"[out-file] 출력 저장 중: {Path(args.out_file).resolve()}", file=sys.stderr)

    try:
        print("\n=== Extractor 단독 실행 ===")
        print(f"    URL          : {args.url}")
        print(f"    mode         : {args.mode}")
        if args.request_file:
            print(f"    request-file : {args.request_file}")
        if args.response_file:
            print(f"    response-file: {args.response_file}")
        if args.out_file:
            print(f"    out-file     : {args.out_file}")
        if args.dump_prompt:
            print("    --dump-prompt: 프롬프트 전체 출력 후 종료")
        if args.save_mock and args.mode == "mock":
            print("    WARN: --save-mock은 production 모드 결과를 저장할 때 의미 있습니다.")

        asyncio.run(run(args))
        print("\n=== 완료 ===")
    finally:
        if _out_fp is not None:
            _out_fp.close()
            sys.stdout = sys.__stdout__


if __name__ == "__main__":
    main()
