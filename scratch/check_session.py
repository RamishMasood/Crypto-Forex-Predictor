import time
import os
from playwright.sync_api import sync_playwright

p = sync_playwright().start()
ctx = p.chromium.launch_persistent_context(
    ".whatsapp_web_session",
    channel="chrome",
    headless=False,
    args=["--window-position=-3000,-3000", "--window-size=1280,850"]
)
page = ctx.pages[0]
page.goto("https://web.whatsapp.com")
print("Navigated. Waiting 12s...")
time.sleep(12)

has_chat = page.locator("div#pane-side").count()
has_qr = page.locator("canvas").count()
has_progress = page.locator("progress").count()
print(f"Results: has_chat={has_chat}, has_qr={has_qr}, has_progress={has_progress}")
page.screenshot(path="scratch/session_status.png")
ctx.close()
p.stop()
