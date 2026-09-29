import sys, os
sys.path.insert(0, os.path.abspath("."))
import logging, time
logging.basicConfig(level=logging.INFO)
from src.engine.whatsapp_listener import WhatsAppListenerEngine

engine = WhatsAppListenerEngine()
print("Starting engine...")
engine.start()
for i in range(15):
    time.sleep(2)
    st = engine.get_status()
    print(f"T+{(i+1)*2}s: running={engine.is_running}, status={st.get('status')}")
    if not engine.is_running:
        break
engine.stop()
