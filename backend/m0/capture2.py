import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

OUT_CANCEL = "D:/Code-Shepherd/presentation/neo4j_cancel.png"
OUT_CONN   = "D:/Code-Shepherd/presentation/neo4j_connected.png"
OUT_GRAPH  = "D:/Code-Shepherd/presentation/neo4j_graph.png"

PASSWORDS = ["codeshepherd", "shepherd", "neo4j", "password", "1234", "admin", "test123"]
QUERY = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:7474/browser/", timeout=10000)
    time.sleep(3)

    # Cancel 눌러서 백그라운드 세션 확인
    cancel_btn = page.query_selector("button:has-text('Cancel')")
    if cancel_btn:
        cancel_btn.click()
        time.sleep(2)
        page.screenshot(path=OUT_CANCEL)
        print("Cancel 후 화면 저장:", OUT_CANCEL)

    # 비밀번호 시도
    for pwd in PASSWORDS:
        # 연결 폼이 없으면 이미 접속된 것
        modal = page.query_selector("input[type='password']")
        if not modal:
            print("이미 접속 상태 — 쿼리 실행")
            break

        print(f"  패스워드 시도: {pwd}")
        page.fill("input[type='password']", pwd)
        page.click("button:has-text('Connect')")
        time.sleep(2.5)

        # 연결 성공 확인 (모달이 사라졌으면 성공)
        modal2 = page.query_selector("input[type='password']")
        if not modal2 or not modal2.is_visible():
            print(f"  연결 성공: {pwd}")
            page.screenshot(path=OUT_CONN)
            break
        # 실패 시 비밀번호 필드 클리어
        page.fill("input[type='password']", "")

    # 쿼리 실행
    time.sleep(1)
    page.screenshot(path=OUT_CONN)
    
    # CodeMirror 에디터 찾기
    editor = page.query_selector(".CodeMirror-code, [data-testid='cypher-editor'] .cm-content, .cm-content")
    if editor:
        editor.click()
        time.sleep(0.3)
        # 기존 내용 지우고 쿼리 입력
        page.keyboard.press("Control+A")
        page.keyboard.type(QUERY)
        time.sleep(0.5)
        page.keyboard.press("Control+Enter")
        print("쿼리 실행됨")
        time.sleep(5)

    # Graph 탭 클릭 (있으면)
    for sel in ["button:has-text('Graph')", "[data-testid='cypherResultGraph']", ".graph-tab"]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            btn.click()
            time.sleep(1.5)
            break

    page.screenshot(path=OUT_GRAPH)
    print(f"그래프 캡처: {OUT_GRAPH}")

    browser.close()
