from playwright.sync_api import sync_playwright
import time
import os

SESSION_DIR = ".whatsapp_web_session"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=SESSION_DIR,
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 850}
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print("Navigating to WhatsApp Web...")
    page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)
    
    # Wait for login
    time.sleep(10)
    logged_in = page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0
    print("Logged in:", logged_in)
    
    if logged_in:
        # Check navigation icons on left rail
        print("Checking navigation rail buttons...")
        nav_buttons = page.locator("header button, div[role='navigation'] button, div[aria-label] button").all()
        for i, b in enumerate(nav_buttons):
            try:
                label = b.get_attribute("aria-label") or b.get_attribute("title") or b.inner_text()
                print(f"  Button {i}: label={repr(label)}")
            except Exception:
                pass

        # Look specifically for channels / newsletter button or icon
        channel_btn = page.locator("button[aria-label*='Channel'], button[aria-label*='channel'], button[title*='Channel'], span[data-icon*='newsletter'], button[aria-label*='Newsletter']").first
        if channel_btn.count() > 0:
            print("Found Channels button! Clicking it...")
            channel_btn.click()
            time.sleep(3)
            
            # Read channels listed in sidebar
            print("Reading channels listed in pane...")
            items = page.locator("div[role='listitem'], div[data-testid='cell-frame-container'], div#pane-side span[title]").all()
            found_names = set()
            for it in items:
                try:
                    title_attr = it.get_attribute("title")
                    if title_attr and len(title_attr) > 2:
                        found_names.add(title_attr)
                    txt = it.inner_text().strip().split("\n")[0]
                    if txt and len(txt) > 2 and len(txt) < 80:
                        found_names.add(txt)
                except Exception:
                    pass
            print("Found channels/items:", found_names)
        else:
            print("Channels button not found by direct selector, checking all icons...")
            icons = page.locator("span[data-icon]").all()
            icon_names = [ic.get_attribute("data-icon") for ic in icons]
            print("All icons on page:", icon_names[:30])

    ctx.close()
