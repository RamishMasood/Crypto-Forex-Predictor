import sys, os
sys.path.insert(0, os.path.abspath("."))
from src.engine.whatsapp_listener import WhatsAppListenerEngine

engine = WhatsAppListenerEngine()
print("Triggering channel discovery...")
res = engine._discover_channels_standalone()
print("Discovered channels result:", res)
state = engine.executor.load_state()
print("Followed channels in state:", state.get("followed_channels"))
