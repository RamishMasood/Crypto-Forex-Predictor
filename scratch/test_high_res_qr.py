import sys, os
sys.path.insert(0, os.path.abspath("."))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 850},
        device_scale_factor=2  # High-DPI for super-crisp, easily scannable QR code!
    )
    page = context.new_page()
    print("Navigating to web.whatsapp.com...")
    page.goto('https://web.whatsapp.com', wait_until='domcontentloaded', timeout=45000)
    print("Waiting for QR canvas to appear...")
    canvas = page.wait_for_selector('canvas', timeout=35000)
    if canvas:
        print("Canvas found! Taking high-DPI screenshot...")
        canvas.screenshot(path='.whatsapp_qr_high_res.png')
        print("Saved .whatsapp_qr_high_res.png successfully!")
    browser.close()
