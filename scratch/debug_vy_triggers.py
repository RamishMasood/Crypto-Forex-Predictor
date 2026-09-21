import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
import pandas as pd
from src.engine.backtest_engine import get_backtest_engine
from src.strategies.streamer_playbook import MasterStreamerPlaybook
from src.engine.session_manager import SessionManager

bt = get_backtest_engine()
now = datetime.now(timezone.utc)
d_from = now - timedelta(days=14)
d_to = now

for sym in ["BTC/USD", "XAU/USD"]:
    asset_type = 'crypto' if 'BTC' in sym else 'forex'
    for tf in ["15m", "1h"]:
        df, broker_sym, sp = bt.fetch_mt5_data(sym, tf, d_from, d_to)
        if df is None or len(df) == 0:
            continue
        print(f"\nChecking {sym} {tf} (bars: {len(df)})...")
        strat_cls = MasterStreamerPlaybook.STRATEGY_MAP['VIVEK_YADAV']
        for i in range(50, len(df)):
            sub = df.iloc[max(0, i-250):i+1].copy()
            cur_time = sub['timestamp'].iloc[-1]
            cur_atr = float(sub['atr'].iloc[-1]) if 'atr' in sub.columns else 0.0
            st_res = strat_cls.evaluate(sub, atr=cur_atr, timeframe=tf)
            if st_res.get('action') in ['BUY', 'SELL']:
                is_sess_ok, sess_desc = SessionManager.is_strategy_session_allowed('VIVEK_YADAV', dt=cur_time, asset_type=asset_type)
                conf = float(st_res.get('confidence', 0))
                print(f"  Bar {i} ({cur_time}): action={st_res.get('action')}, conf={conf}, sess_ok={is_sess_ok} ({sess_desc})")
