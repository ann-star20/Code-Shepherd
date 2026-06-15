import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:7474/browser/", timeout=10000)
    time.sleep(3)
    # 현재 HTML 구조 일부 출력
    html = page.content()
    print(html[:3000])
    page.screenshot(path="D:/Code-Shepherd/presentation/neo4j_debug.png")
    print("screenshot saved")
    browser.close()
