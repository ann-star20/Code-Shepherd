# subprocess 공부 — 나중에 이어서

## 여기까지 한 것
- pylint_tool.py 파일 읽음
- subprocess가 "터미널 명령어를 Python 코드에서 실행하는 것" 이라는 것 파악 중

## 다음에 할 실습

터미널에서 이거 두 개 실행해서 결과 비교하기:

**1. 터미널에서 직접:**
```bash
python -m pylint dev2/tools/python/pylint_tool.py --output-format=json --score=no
```

**2. Python 코드로 똑같이 (test.py에 붙여넣고 실행):**
```python
import subprocess
r = subprocess.run(
    ["python", "-m", "pylint", "dev2/tools/python/pylint_tool.py", "--output-format=json", "--score=no"],
    capture_output=True, text=True
)
print(r.stdout)
```

결과가 똑같이 나오면 OK.

## 이어서 할 질문
- Q3: 모든 언어 도구를 subprocess로 통일했을 때 장점은?
- 핵심 질문 3개
- 백지 재작성 챌린지
- 면접 한 줄 답변 완성
