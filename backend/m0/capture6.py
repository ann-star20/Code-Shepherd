import sys, io, time, json
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
    time.sleep(3)

    page.screenshot(path="D:/Code-Shepherd/presentation/s6_start.png")

    # 프로토콜 드롭다운 옵션 확인
    opts = page.evaluate("""
        (() => {
            const sel = document.querySelector('select');
            if (!sel) return 'NO SELECT';
            return [...sel.options].map(o => o.value + '|' + o.text);
        })()
    """)
    print("Protocol options:", opts)

    # neo4j+s 옵션 선택
    page.evaluate("""
        const sel = document.querySelector('select');
        if (sel) {
            const opt = [...sel.options].find(o => o.value.includes('+s') || o.text.includes('+s'));
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', {bubbles: true}));
                console.log('Protocol set to:', opt.value);
            }
        }
    """)
    time.sleep(0.5)

    # URL 필드 - React controlled input이므로 nativeInputValueSetter 사용
    result = page.evaluate(f"""
        (() => {{
            const allInputs = [...document.querySelectorAll('input')];
            const info = allInputs.map(i => ({{type: i.type, value: i.value, ph: i.placeholder, name: i.name}}));
            
            // URL 필드 찾기
            const urlInput = allInputs.find(i => i.type === 'text' && (i.value.includes('localhost') || i.value.includes('7687') || i.placeholder?.includes('URI') || i.placeholder?.includes('URL')));
            
            if (urlInput) {{
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(urlInput, '{AURA_URL}');
                urlInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                urlInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
            
            return JSON.stringify(info);
        }})()
    """)
    print("Inputs:", result[:500])
    time.sleep(0.3)

    # User 필드
    page.evaluate(f"""
        (() => {{
            const allInputs = [...document.querySelectorAll('input')];
            const userInput = allInputs.find(i => i.type === 'text' && (i.value === 'neo4j' || i.name === 'username' || i.placeholder?.toLowerCase().includes('user')));
            if (userInput) {{
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(userInput, '{AURA_USER}');
                userInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        }})()
    """)
    time.sleep(0.3)

    # Password
    page.evaluate(f"""
        (() => {{
            const pw = document.querySelector('input[type="password"]');
            if (pw) {{
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(pw, '{AURA_PASS}');
                pw.dispatchEvent(new Event('input', {{bubbles: true}}));
                pw.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }})()
    """)
    time.sleep(0.3)

    page.screenshot(path="D:/Code-Shepherd/presentation/s7_filled.png")
    print("폼 입력 완료 — 스크린샷 저장")

    # data-testid로 정확히 클릭
    btn = page.locator('[data-testid="connection-form-submit"]')
    btn.click(force=True)
    print("Submit 클릭됨")
    time.sleep(10)  # Aura 연결 대기

    page.screenshot(path="D:/Code-Shepherd/presentation/s8_after_connect.png")
    print("연결 후 스크린샷")

    # 쿼리 에디터 찾기
    editor = page.query_selector(".cm-content, .CodeMirror, [contenteditable='true']")
    if editor:
        editor.click()
        time.sleep(0.3)
        page.keyboard.press("Control+A")
        page.keyboard.type(QUERY)
        time.sleep(0.3)
        page.keyboard.press("Control+Enter")
        print("쿼리 실행됨")
        time.sleep(10)
        page.screenshot(path=OUT)
        print(f"최종 저장: {OUT}")
    else:
        print("에디터 없음")
        page.screenshot(path=OUT)

    browser.close()
print("완료")
