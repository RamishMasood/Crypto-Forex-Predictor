import json
import MetaTrader5 as mt5

def check_tp2_real_hit(cb, mt5_conn):
    tkts = cb.get('tickets', [])
    tp2_p = float(cb.get('tp2_price', 0.0) or 0.0)
    action = str(cb.get('action', '')).upper()
    is_buy = 'BUY' in action
    
    if not tkts:
        return False, "No tickets"
        
    # If 2 or more tickets (standard multi-target split)
    if len(tkts) >= 2:
        tp2_ticket = tkts[1]
        deals = mt5_conn.history_deals_get(position=int(tp2_ticket))
        if deals:
            exit_deals = [d for d in deals if d.entry == 1]
            for ed in exit_deals:
                comm = str(ed.comment).lower()
                price = float(ed.price)
                pnl = float(ed.profit)
                # If comment has [tp] and not [sl]
                if '[tp' in comm:
                    return True, f"Ticket #{tp2_ticket} hit TP deal with comment '{ed.comment}'"
                # Price check: reached tp2 price within tolerance
                if tp2_p > 0:
                    tol = abs(tp2_p) * 0.001
                    if is_buy and price >= (tp2_p - tol):
                        return True, f"Ticket #{tp2_ticket} reached TP2 price {price} >= {tp2_p}"
                    elif not is_buy and price <= (tp2_p + tol):
                        return True, f"Ticket #{tp2_ticket} reached TP2 price {price} <= {tp2_p}"
            return False, f"Ticket #{tp2_ticket} exited at BE/SL (comment: '{exit_deals[0].comment if exit_deals else ''}')"
        return False, f"Ticket #{tp2_ticket} deals not found"
        
    # If single order mode (only 1 ticket)
    if len(tkts) == 1:
        tkt = tkts[0]
        deals = mt5_conn.history_deals_get(position=int(tkt))
        if deals:
            exit_deals = [d for d in deals if d.entry == 1]
            for ed in exit_deals:
                comm = str(ed.comment).lower()
                price = float(ed.price)
                if '[tp' in comm:
                    return True, f"Single ticket #{tkt} hit TP deal"
                if tp2_p > 0:
                    tol = abs(tp2_p) * 0.001
                    if is_buy and price >= (tp2_p - tol):
                        return True, f"Single ticket #{tkt} reached TP2 price"
                    elif not is_buy and price <= (tp2_p + tol):
                        return True, f"Single ticket #{tkt} reached TP2 price"
            return False, "Single ticket exited at BE/SL"
            
    return False, "Unknown"

if mt5.initialize():
    with open('.autonomous_trader_state.json', 'r', encoding='utf-8') as f:
        st = json.load(f)
    cbs = st.get('closed_batches', [])
    print(f"Auditing {len(cbs)} batches for REAL TP2 hits:")
    real_tp2_count = 0
    for cb in cbs:
        bid = cb.get('batch_id')
        strat = cb.get('strategy_used')
        pnl = cb.get('profit')
        is_tp2, reason = check_tp2_real_hit(cb, mt5)
        if is_tp2:
            real_tp2_count += 1
            print(f"Batch #{bid:6} ({strat:15}): REAL TP2 HIT! Reason: {reason} | PnL: ${pnl}")
        else:
            print(f"Batch #{bid:6} ({strat:15}): NO TP2 (Stopped at BE / SL). Detail: {reason} | PnL: ${pnl}")
    print(f"\nFinal Audit Result: Exactly {real_tp2_count} out of {len(cbs)} batches hit REAL TP2!")
    mt5.shutdown()
