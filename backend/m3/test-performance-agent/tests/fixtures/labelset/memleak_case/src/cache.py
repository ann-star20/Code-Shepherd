"""양성 라벨 케이스 — 메모리 누수(PERF-003) 두 패턴.

1. 전역 list(EVENTS)에 함수 내부에서 append 누적 → 무한 증가
2. open()이 with/대입 없이 단독 호출 → 파일 핸들 누수

인자명(evt·target)은 휴리스틱 키워드가 아님 → TEST-003 미발생(PERF-003만 격리).
"""

EVENTS = []


def record(evt):
    EVENTS.append(evt)


def load_file(target):
    open(target)
