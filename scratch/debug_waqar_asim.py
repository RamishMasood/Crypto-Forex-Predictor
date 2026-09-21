import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
from src.engine.backtest_engine import get_backtest_engine
from src.strategies.streamer_playbook import MasterStreamerPlaybook
from src.engine.session_manager import SessionManager

bt = get_backtest_engine()
now = datetime.now(timezone.utc)
d_from = now - timedelta(days=14)
d_to = now

strat_cls = MasterStreamerPlaybook.STRATEGY_MAP['WAQAR_ASIM']

for sym in ["EUR/USD", "GBP/USD"]:
    for tf in ["15m"]:
        df, broker_sym, sp = bt.fetch_mt5_data(sym, tf, d_from, d_to)
        print(f"=== {sym} {tf} ({len(df) if df is not None else 0} bars) ===")
        if df is None or len(df) == 0:
            continue
        triggers = 0
        for i in range(50, len(df)):
            sub = df.iloc[max(0, i-250):i+1].copy()
            cur_time = sub['timestamp'].iloc[-1]
            cur_atr = float(sub['atr'].iloc[-1]) if 'atr' in sub.columns else 0.0
            res = strat_cls.evaluate(sub, atr=cur_atr, timeframe=tf)
            if res.get('action') in ['BUY', 'SELL']:
                is_sess_ok, sess_desc = SessionManager.is_strategy_session_allowed('WAQAR_ASIM', dt=cur_time, asset_type='forex')
                triggers += 1
                print(f"  Bar {i} ({cur_time}): {res.get('action')} @ {sub['close'].iloc[-1]} | Sess: {is_sess_ok} ({sess_desc})")
        print(f"Total triggers: {triggers}")
