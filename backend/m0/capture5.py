import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

AURA_URL  = "617ab31b.databases.neo4j.io"
AURA_USER = "617ab31b"
AURA_PASS = "cDhnU6zLop-KBV0Amnz0iIOjAb9R8mpOKNcFe6IIdwk"
OUT = "D:/Code-Shepherd/presentation/neo4j_graph.png"
QUERY = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:7474/browser/", timeout=10000)
    time.sleep(2)

    # 폼이 보이면 연결 시도
    # 1. Protocol 드롭다운 → neo4j+s
    page.evaluate("""
        const sel = document.querySelector('select');
        if (sel) {
            const opt = [...sel.options].find(o => o.value.includes('neo4j+s'));
            if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', {bubbles: true})); }
        }
    """)
    time.sleep(0.3)

    # 2. Connection URL 변경
    page.evaluate(f"""
        const inputs = [...document.querySelectorAll('input[type="text"]')];
        const urlInput = inputs.find(i => i.value.includes('localhost') || i.value.includes('7687'));
        if (urlInput) {{
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(urlInput, '{AURA_URL}');
            urlInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            urlInput.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
    """)
    time.sleep(0.3)

    # 3. Database user 변경
    page.evaluate(f"""
        const inputs = [...document.querySelectorAll('input[type="text"]')];
        const userInput = inputs.find(i => i.value === 'neo4j' || i.placeholder?.toLowerCase().includes('user'));
        if (userInput) {{
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(userInput, '{AURA_USER}');
            userInput.dispatchEvent(new Event('input', {{bubbles: true}}));
        }}
    """)
    time.sleep(0.3)

    # 4. Password 입력
    page.evaluate(f"""
        const pw = document.querySelector('input[type="password"]');
        if (pw) {{
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(pw, '{AURA_PASS}');
            pw.dispatchEvent(new Event('input', {{bubbles: true}}));
        }}
    """)
    time.sleep(0.3)

    page.screenshot(path="D:/Code-Shepherd/presentation/s4_before_submit.png")
    print("폼 입력 완료")

    # 5. Connect 버튼 클릭 (force)
    page.locator("button:has-text('Connect')").click(force=True)
    print("Connect 클릭됨")
    time.sleep(8)  # Aura 연결 대기

    page.screenshot(path="D:/Code-Shepherd/presentation/s5_connected.png")
    print("연결 후 스크린샷")

    # 쿼리 실행
    editor = page.query_selector(".cm-content")
    if editor:
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(QUERY)
        page.keyboard.press("Control+Enter")
        print("쿼리 실행됨")
        time.sleep(8)

    page.screenshot(path=OUT)
    print(f"최종: {OUT}")
    browser.close()
