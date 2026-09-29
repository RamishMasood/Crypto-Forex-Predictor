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
    page.wait_for_selector('canvas', timeout=35000)
    
    # Check data-ref
    ref_div = page.locator("div[data-ref]").first
    if ref_div.count() > 0:
        print("data-ref attribute exists! length:", len(ref_div.get_attribute("data-ref") or ""))
        
    print("Waiting 60 seconds to see expiration...")
    time.sleep(60)
    
    # Check if data-ref still exists or changed or if button appeared
    buttons_in_ref = page.locator("div[data-ref] button, div[data-ref] [role='button'], div[data-ref] span").all()
    print("Elements inside data-ref after 60s:", len(buttons_in_ref))
    for idx, b in enumerate(buttons_in_ref[:5]):
        print(f"  [{idx}] tag={b.evaluate('el => el.tagName')} text={repr(b.inner_text()[:30])} html={repr(b.evaluate('el => el.outerHTML[:80]'))}")
        
    browser.close()
