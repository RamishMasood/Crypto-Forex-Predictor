import json
import MetaTrader5 as mt5
from src.engine.autonomous_manager import AutonomousTraderEngine

if mt5.initialize():
    with open('.autonomous_trader_state.json', 'r', encoding='utf-8') as f:
        st = json.load(f)
    cbs = st.get('closed_batches', [])
    modified = False
    for cb in cbs:
        tkts = cb.get('tickets', [])
        tp2_real = False
        tp2_p = float(cb.get('tp2_price', 0.0) or 0.0)
        is_buy_act = 'BUY' in str(cb.get('action', '')).upper()
        if len(tkts) >= 2:
            deals = mt5.history_deals_get(position=int(tkts[1]))
            if deals:
                for ed in [d for d in deals if d.entry == 1]:
                    comm = str(ed.comment).lower()
                    pr = float(ed.price)
                    if '[tp' in comm and '[sl' not in comm:
                        tp2_real = True
                    elif tp2_p > 0 and pr > 0:
                        tol = abs(tp2_p) * 0.001
                        if is_buy_act and pr >= (tp2_p - tol) and '[sl' not in comm:
                            tp2_real = True
                        elif not is_buy_act and pr <= (tp2_p + tol) and '[sl' not in comm:
                            tp2_real = True
        elif len(tkts) == 1:
            deals = mt5.history_deals_get(position=int(tkts[0]))
            if deals:
                for ed in [d for d in deals if d.entry == 1]:
                    comm = str(ed.comment).lower()
                    pr = float(ed.price)
                    if '[tp' in comm and '[sl' not in comm:
                        tp2_real = True
                    elif tp2_p > 0 and pr > 0:
                        tol = abs(tp2_p) * 0.001
                        if is_buy_act and pr >= (tp2_p - tol) and '[sl' not in comm:
                            tp2_real = True
                        elif not is_buy_act and pr <= (tp2_p + tol) and '[sl' not in comm:
                            tp2_real = True
        old_val = cb.get('tp2_hit')
        if old_val != tp2_real:
            print("Batch #" + str(cb.get('batch_id')) + ": tp2_hit updated from " + str(old_val) + " to " + str(tp2_real))
            cb['tp2_hit'] = tp2_real
            modified = True
            
    if modified:
        with open('.autonomous_trader_state.json', 'w', encoding='utf-8') as f:
            json.dump(st, f, indent=2)
        print('State file updated with real TP2 flags!')
    else:
        print('All batches already had accurate TP2 flags.')
    mt5.shutdown()

engine = AutonomousTraderEngine()
lb = engine.compute_strategy_leaderboard()
print('\nLeaderboard with REAL TP2 hits:')
for item in lb:
    if item['total_trades'] > 0:
        clean_name = item['name'][:35]
        print('%-35s | Tot: %2d | W: %2d | L: %2d | PnL: %+6.2f | Real TP2: %d' % (
            clean_name, item['total_trades'], item['wins'], item['losses'], item['net_pnl'], item.get('tp2_hits', 0)
        ))
