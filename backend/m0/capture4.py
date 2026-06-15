import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

AURA_URL  = "617ab31b.databases.neo4j.io"
AURA_USER = "617ab31b"
AURA_PASS = "cDhnU6zLop-KBV0Amnz0iIOjAb9R8mpOKNcFe6IIdwk"
QUERY = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500"
OUT = "D:/Code-Shepherd/presentation/neo4j_graph.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:7474/browser/", timeout=10000)
    time.sleep(2)
    page.screenshot(path="D:/Code-Shepherd/presentation/s1_initial.png")

    # Connect to instance 클릭 (모달 안의 버튼)
    page.locator("text=Connect to instance").last.click(force=True)
    time.sleep(1.5)
    page.screenshot(path="D:/Code-Shepherd/presentation/s2_form.png")
    print("폼 스크린샷 저장")

    # Protocol 드롭다운
    try:
        page.select_option("select", "neo4j+s://")
    except:
        # 드롭다운 클릭 방식
        page.locator("select").select_option(value="neo4j+s")
    time.sleep(0.3)

    # URL 필드 변경
    url_inputs = page.locator("input[type='text']").all()
    print(f"text inputs: {len(url_inputs)}")
    for inp in url_inputs:
        val = inp.input_value()
        print(f"  input val: {val!r}")
        if "localhost" in val or "7687" in val:
            inp.triple_click()
            inp.type(AURA_URL)
            print(f"  -> URL changed to {AURA_URL}")
            break

    # Username 필드
    all_inputs = page.locator("input").all()
    for inp in all_inputs:
        val = inp.input_value()
        tp = inp.get_attribute("type") or "text"
        print(f"  input type={tp} val={val!r}")

    page.screenshot(path="D:/Code-Shepherd/presentation/s3_filled.png")
    browser.close()
