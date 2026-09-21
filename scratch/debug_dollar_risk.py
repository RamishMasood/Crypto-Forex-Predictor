import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
from src.engine.backtest_engine import get_backtest_engine

bt = get_backtest_engine()
now = datetime.now(timezone.utc)
d_from = now - timedelta(days=14)
d_to = now

df, broker_sym, sp = bt.fetch_mt5_data("XAU/USD", "1h", d_from, d_to)
print("XAU/USD 1h bars:", len(df) if df is not None else 0)
contract_size = bt.compute_contract_size("XAU/USD")
lot_p1, lot_p2, lot_p3 = bt.compute_batch_lot_split(0.03)
tot_lots = round(lot_p1 + lot_p2 + lot_p3, 4)
print(f"Contract size: {contract_size}, tot_lots: {tot_lots}")

from src.strategies.streamer_playbook import MasterStreamerPlaybook
strat_cls = MasterStreamerPlaybook.STRATEGY_MAP['VIVEK_YADAV']

for i in [151, 157]:
    sub = df.iloc[max(0, i-250):i+1].copy()
    cur_atr = float(sub['atr'].iloc[-1])
    cur_close = float(sub['close'].iloc[-1])
    st_res = strat_cls.evaluate(sub, atr=cur_atr, timeframe='1h')
    setup = st_res.get('trade_setup', {})
    setup_sl = float(setup.get('stop_loss', 0.0))
    sl_dist = abs(cur_close - setup_sl)
    dollar_risk = tot_lots * sl_dist * contract_size
    print(f"Bar {i}: close={cur_close}, sl={setup_sl}, sl_dist={sl_dist:.2f}, dollar_risk=${dollar_risk:.2f} (max allowed: $50)")
