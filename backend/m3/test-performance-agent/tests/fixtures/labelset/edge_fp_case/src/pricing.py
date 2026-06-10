"""음성 라벨 케이스 — TEST-003 휴리스틱의 오탐(FP)을 정직하게 드러냄.

이 함수는 0·음수·범위초과를 *이미* 검증한다 → rule 정의상 누락 엣지케이스 없음(정답=0건).
그러나 휴리스틱은 인자명(price·rate)만 보고 TEST-003 을 쏜다 → FP.
→ rule별 표에서 TEST-003 precision 하락으로 이 약점이 정직하게 드러나야 한다.
"""


def apply_discount(price, rate):
    if price < 0 or rate < 0 or rate > 1:
        raise ValueError("invalid price or rate")
    return price * (1 - rate)
