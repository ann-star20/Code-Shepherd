import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

OUT = "D:/Code-Shepherd/presentation/neo4j_graph.png"

# Aura 자격증명
AURA_URL  = "617ab31b.databases.neo4j.io"
AURA_USER = "617ab31b"
AURA_PASS = "cDhnU6zLop-KBV0Amnz0iIOjAb9R8mpOKNcFe6IIdwk"
QUERY     = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:7474/browser/", timeout=10000)
    time.sleep(3)

    # Connect to instance 링크 클릭 (이미 모달이 없으면 직접 찾기)
    for sel in [
        "button:has-text('Connect to instance')",
        "a:has-text('Connect to instance')",
        "button:has-text('Connect')",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            btn.click()
            time.sleep(1.5)
            break

    # 연결 폼 작성 — Protocol을 neo4j+s로 변경
    proto = page.query_selector("select, [data-testid='protocol-selector']")
    if proto:
        proto.select_option("neo4j+s://")
        time.sleep(0.5)

    # URL 필드
    url_field = page.query_selector("input[placeholder*='localhost'], input[name*='url'], input[name*='host']")
    if url_field:
        url_field.triple_click()
        url_field.type(AURA_URL)
        print(f"URL 입력: {AURA_URL}")

    # Username
    user_field = page.query_selector("input[name='username'], input[placeholder*='neo4j'], input[aria-label*='user' i]")
    if user_field:
        user_field.triple_click()
        user_field.type(AURA_USER)

    # Password
    pass_field = page.query_selector("input[type='password']")
    if pass_field:
        pass_field.triple_click()
        pass_field.type(AURA_PASS)
        print("비밀번호 입력 완료")

    page.screenshot(path="D:/Code-Shepherd/presentation/neo4j_before_connect.png")

    # Connect 버튼
    connect_btn = page.query_selector("button:has-text('Connect')")
    if connect_btn:
        connect_btn.click()
        print("Connect 클릭")
        time.sleep(6)  # Aura 연결 대기

    page.screenshot(path="D:/Code-Shepherd/presentation/neo4j_after_connect.png")
    print("연결 후 스크린샷 저장")

    # 쿼리 실행
    editor = page.query_selector(".cm-content")
    if editor:
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(QUERY)
        page.keyboard.press("Control+Enter")
        print("쿼리 실행")
        time.sleep(8)

    # Graph 탭
    for sel in ["button:has-text('Graph')", "[aria-label='Graph']"]:
        b = page.query_selector(sel)
        if b and b.is_visible():
            b.click()
            time.sleep(2)
            break

    page.screenshot(path=OUT)
    print(f"최종 캡처: {OUT}")
    browser.close()
