"""Ollama + bge-m3 설치 여부 확인 스크립트 — 팀원 로컬 환경 점검용."""
import json
import subprocess
import sys
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434"
REQUIRED_MODEL = "bge-m3"


def check_ollama_process() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5
        )
        print(f"[OK] Ollama 설치됨: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("[FAIL] Ollama 미설치 — https://ollama.com 에서 설치 필요")
        return False
    except Exception as e:
        print(f"[FAIL] Ollama 확인 실패: {e}")
        return False


def check_ollama_running() -> bool:
    try:
        req = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        data = json.loads(req.read())
        models = [m["name"] for m in data.get("models", [])]
        print(f"[OK] Ollama 서버 실행 중 (포트 11434)")
        print(f"     설치된 모델: {models if models else '없음'}")
        return True, models
    except urllib.error.URLError:
        print("[FAIL] Ollama 서버 미실행 — 터미널에서 'ollama serve' 실행 필요")
        return False, []
    except Exception as e:
        print(f"[FAIL] Ollama API 응답 오류: {e}")
        return False, []


def check_bge_m3(models: list) -> bool:
    matched = [m for m in models if REQUIRED_MODEL in m]
    if matched:
        print(f"[OK] bge-m3 모델 있음: {matched}")
        return True
    else:
        print(f"[FAIL] bge-m3 없음 — 아래 명령 실행 필요:")
        print(f"       ollama pull bge-m3")
        return False


def check_embedding_works() -> bool:
    try:
        payload = json.dumps({"model": REQUIRED_MODEL, "prompt": "test"}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        emb = data.get("embedding", [])
        print(f"[OK] bge-m3 임베딩 정상 동작 (벡터 차원: {len(emb)})")
        return True
    except Exception as e:
        print(f"[FAIL] bge-m3 임베딩 호출 실패: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Ollama / bge-m3 환경 점검")
    print("=" * 50)

    ok1 = check_ollama_process()
    ok2, models = check_ollama_running()

    if not ok2:
        print("\n[결론] Ollama 서버가 꺼져있어서 m3 동작 불가")
        sys.exit(1)

    ok3 = check_bge_m3(models)

    if not ok3:
        print("\n[결론] bge-m3 미설치 — 위 명령 실행 후 재시도")
        sys.exit(1)

    ok4 = check_embedding_works()

    print("\n" + "=" * 50)
    if ok1 and ok2 and ok3 and ok4:
        print("[결론] 모든 항목 OK — m3 임베딩 정상 동작 가능")
    else:
        print("[결론] 일부 항목 실패 — 위 [FAIL] 항목 먼저 해결 필요")
    print("=" * 50)
