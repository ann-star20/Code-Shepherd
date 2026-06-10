"""음성 라벨 케이스 — 진짜 깨끗한 코드(이슈 0이어야 정상).

루프·DB호출·open·전역누적 없음. 인자명(a·b·x·y)도 휴리스틱 키워드 아님.
→ 6탐지기 모두 0건이어야 한다. "깨끗한 코드엔 헛소리 안 한다"의 증거.
"""


def add(a, b):
    return a + b


def multiply(x, y):
    return x * y
