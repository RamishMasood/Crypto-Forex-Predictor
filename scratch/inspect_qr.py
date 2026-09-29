from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 850},
        device_scale_factor=2
    )
    page = context.new_page()
    page.goto('https://web.whatsapp.com', wait_until='domcontentloaded', timeout=45000)
    canvas = page.wait_for_selector('canvas', timeout=35000)
    print(f"Canvas found: {bool(canvas)}")
    if canvas:
        # Take high-res screenshot
        canvas.screenshot(path='.whatsapp_qr.png')
        print("Initial QR screenshot saved to .whatsapp_qr.png")
    
    # Wait for reload overlay
    print("Waiting 25 seconds for QR expiration/reload overlay...")
    time.sleep(25)
    
    # Check elements around canvas or reload buttons
    reload_locators = [
        "button:has-text('Reload')",
        "button:has-text('reload')",
        "span[data-icon='reload']",
        "span[data-icon='refresh']",
        "div[role='button']",
        "div[data-ref]"
    ]
    for sel in reload_locators:
        cnt = page.locator(sel).count()
        print(f"Selector '{sel}': count={cnt}")
        if cnt > 0:
            for idx in range(min(cnt, 3)):
                elem = page.locator(sel).nth(idx)
                print(f"  [{idx}] visible={elem.is_visible()} text={repr(elem.inner_text()[:40])}")
                
    browser.close()
