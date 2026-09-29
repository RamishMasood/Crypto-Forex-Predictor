import sys
import asyncio
import os
import time

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir='.whatsapp_web_session',
        channel='chrome',
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--window-position=-3000,-3000', '--window-size=1280,850']
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://web.whatsapp.com', wait_until='domcontentloaded')
    print('DOM content loaded! Waiting for splash to finish and QR canvas to appear...')
    for i in range(30):
        time.sleep(1)
        c = page.locator('canvas').first
        if c.count() > 0 and c.is_visible():
            c.screenshot(path='.whatsapp_qr.png')
            print(f'SUCCESS! Live QR code canvas captured at second {i+1} and saved to .whatsapp_qr.png!')
            break
        if page.locator('div#pane-side').count() > 0:
            print(f'Already logged in at second {i+1}!')
            break
    page.screenshot(path='scratch/whatsapp_landing_after_wait.png')
    ctx.close()
